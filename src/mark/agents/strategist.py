"""Strategist agent — decides WHAT to post (topic, format, angle, hook, tone).

Takes the product, the target platform, and (optionally) current trends, past
winners, and bandit recommendations, and returns a single :class:`ContentPlan`.
"""

from __future__ import annotations

from typing import Optional

from .. import db as db_module
from .. import prompts
from ..app import App
from ..constants import HOOK_STYLES, TONES
from ..llm import LLM
from ..schemas import ContentPlan


def plan_content(
    app: App,
    llm: LLM,
    product: dict,
    platform: str,
    *,
    trends: Optional[list[dict]] = None,
    winners: Optional[list[dict]] = None,
    bandit_picks: Optional[dict] = None,
    strategy=None,
    episode: int = 1,
    forced_trend: Optional[dict] = None,
    character_comments: Optional[list[str]] = None,
) -> ContentPlan:
    trends = trends or []
    winners = winners or []
    bandit_picks = bandit_picks or {}
    allowed = app.settings.platform(platform).content_types or ["text"]
    if strategy is not None:
        # Narrow to the strategy's preferred types when they're allowed here.
        preferred = [t for t in strategy.content_types if t in allowed]
        if preferred:
            allowed = preferred

    system = prompts.strategist_system(product, platform, trends, winners, bandit_picks,
                                       allowed, strategy=strategy, episode=episode,
                                       forced_trend=forced_trend,
                                       character_comments=character_comments)
    user = prompts.strategist_user(platform)

    plan = llm.parse(
        system, user, ContentPlan,
        model=app.settings.llm.text_model,
        temperature=0.95,
        product_id=product["id"],
        mock_factory=lambda: _mock_plan(app, product, platform, allowed, bandit_picks, trends),
    )

    # Guardrails: keep the chosen type within what the platform allows, and force
    # the platform to match what we asked for.
    if plan.content_type not in allowed:
        plan.content_type = bandit_picks.get("content_type", allowed[0])
        if plan.content_type not in allowed:
            plan.content_type = allowed[0]
    plan.platform = platform
    # The bandit's sampled hook/tone override the strategist only half the time.
    # 100% override destroyed context-sensitivity (the strategist may know THIS
    # topic wants a story hook); 0% would starve the arms of on-policy pulls.
    # Either way the used values are what get credited when metrics arrive.
    import random

    row = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM content WHERE product_id = ? AND platform = ?",
        (product["id"], platform))
    rng = random.Random(f"{product['id']}:{platform}:{row['n'] if row else 0}:override")
    if bandit_picks.get("hook_style") and rng.random() < 0.5:
        plan.hook_style = bandit_picks["hook_style"]
    if bandit_picks.get("tone") and rng.random() < 0.5:
        plan.tone = bandit_picks["tone"]
    # One primary emotion per post. The strategy's target is the default; the
    # strategist may pick another valid one; the bandit fills any gap.
    from ..constants import EMOTIONAL_TARGETS

    if plan.emotional_target not in EMOTIONAL_TARGETS:
        plan.emotional_target = (
            getattr(strategy, "emotional_target", "") if strategy else "")
    if plan.emotional_target not in EMOTIONAL_TARGETS:
        plan.emotional_target = bandit_picks.get("emotional_target") or "recognition"
    return plan


def _mock_plan(app: App, product: dict, platform: str, allowed: list[str],
               bandit_picks: dict, trends: list[dict]) -> ContentPlan:
    """Deterministic offline plan that still rotates choices for variety."""
    # Rotate using how much content already exists for this product/platform.
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? AND platform = ?",
        (product["id"], platform),
    )
    n = row["n"] if row else 0

    content_type = bandit_picks.get("content_type") or allowed[n % len(allowed)]
    if content_type not in allowed:
        content_type = allowed[0]
    hook_style = bandit_picks.get("hook_style") or HOOK_STYLES[n % len(HOOK_STYLES)]
    tone = bandit_picks.get("tone") or TONES[n % len(TONES)]

    trend = trends[0]["topic"] if trends else None
    name = product["name"]
    # Short noun-phrase topics so downstream copy templating reads naturally.
    topics = [
        "the daily grind this product kills",
        "the manual busywork no one misses",
        "the part of the job everyone hates",
        "doing it the slow, old-fashioned way",
        "the hours you get back",
    ]
    angles = [
        "a relatable day-in-the-life",
        "a bold before/after",
        "a contrarian hot take",
        "a quick practical tip",
        "a short success story",
    ]
    topic = topics[n % len(topics)]
    angle = angles[n % len(angles)]
    if trend:
        angle = f"{angle}, tied to the trend '{trend}'"
    return ContentPlan(
        platform=platform,
        content_type=content_type,
        topic=topic,
        angle=angle,
        hook_style=hook_style,
        tone=tone,
        trend_tie_in=trend,
        reasoning="offline strategist: rotated content_type/hook/tone for variety"
                  + (f", tied to trend '{trend}'" if trend else ""),
    )
