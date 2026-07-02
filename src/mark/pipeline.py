"""The core content-generation loop.

generate_one():  strategist → writer → novelty guard → media → save (draft)
generate_all():  one piece per enabled platform (or a target count)

This is what `mark generate` and the scheduler both call. Context (trends,
winners, bandit picks) is gathered in one place (`gather_context`) so wiring the
self-improvement loop in later phases touches a single function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from . import store
from .agents import media as media_orch
from .agents import strategist, writer
from .app import App
from .llm import LLM
from .vectors import cosine_to_matrix


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Context gathering (trends / winners / bandit). Filled out in later phases.
# --------------------------------------------------------------------------- #
def gather_context(app: App, llm: LLM, product: dict, platform: str) -> dict:
    """Collect the inputs the strategist & writer use. Degrades to empty context
    when the trends/learning subsystems have no data yet."""
    trends: list[dict] = []
    winners: list[dict] = []
    bandit_picks: dict = {}

    # Trends — recent cached trends for this platform/source.
    try:
        from .trends import aggregator

        trends = aggregator.recent_trends(app, platform=platform, limit=10)
    except Exception:
        trends = []

    # Past winners — so the strategist sees what has actually worked before it
    # picks a topic/angle (the writer separately gets plan-similar few-shots).
    try:
        from .learning import winners as winners_mod

        winners = winners_mod.retrieve(
            app, llm, platform, f"{product['name']} {product['description'][:200]}", k=3)
    except Exception:
        winners = []

    # Bandit recommendations.
    try:
        from .learning import bandit

        bandit_picks = bandit.recommend(app, product["id"], platform)
    except Exception:
        bandit_picks = {}

    return {"trends": trends, "winners": winners, "bandit_picks": bandit_picks}


def recent_rejection_feedback(app: App, product: dict, platform: str, limit: int = 5) -> list[str]:
    """The user's recent rejection notes for this product+platform — fed back to
    the writer so it stops repeating the same mistakes."""
    from . import db as db_module

    rows = db_module.query(
        app.conn,
        "SELECT rejection_feedback FROM content "
        "WHERE product_id = ? AND platform = ? AND status = 'rejected' "
        "AND rejection_feedback IS NOT NULL AND rejection_feedback != '' "
        "ORDER BY created_at DESC LIMIT ?",
        (product["id"], platform, limit),
    )
    return [r["rejection_feedback"] for r in rows]


def winner_examples(app: App, llm: LLM, product: dict, platform: str, plan) -> list[dict]:
    """Top similar past winners for the writer's few-shot examples (Phase 6)."""
    try:
        from .learning import winners as winners_mod

        return winners_mod.retrieve(app, llm, platform, f"{plan.topic} {plan.angle}", k=4)
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Novelty guard
# --------------------------------------------------------------------------- #
@dataclass
class Novelty:
    ok: bool
    max_sim: float
    similar_caption: Optional[str] = None


def check_novelty(app: App, llm: LLM, product: dict, platform: str, draft) -> Novelty:
    """Reject content that's too similar to recent posts (audience fatigue).

    Checked across ALL campaigns on this platform, not just this product's own
    history — concurrent campaigns must each produce unique content, never the
    same post with a different logo.
    """
    lookback = app.settings.llm.novelty_lookback
    threshold = app.settings.llm.novelty_threshold
    recent = store.list_content(app.conn, limit=lookback * 2)
    recent = [r for r in recent if r["platform"] == platform and (r["caption"] or "").strip()]
    # Keep this product's own history first (most relevant), then other campaigns.
    own = [r for r in recent if r["product_id"] == product["id"]][:lookback]
    others = [r for r in recent if r["product_id"] != product["id"]][:lookback]
    recent = own + others
    if not recent:
        return Novelty(ok=True, max_sim=0.0)

    new_text = f"{draft.hook}\n{draft.caption}"
    texts = [new_text] + [f"{r['hook'] or ''}\n{r['caption']}" for r in recent]
    vecs = llm.embed(texts, product_id=product["id"])
    sims = cosine_to_matrix(vecs[0], vecs[1:])
    if sims.size == 0:
        return Novelty(ok=True, max_sim=0.0)
    i = int(np.argmax(sims))
    max_sim = float(sims[i])
    if max_sim >= threshold:
        return Novelty(ok=False, max_sim=max_sim, similar_caption=recent[i]["caption"])
    return Novelty(ok=True, max_sim=max_sim)


# --------------------------------------------------------------------------- #
# Generate
# --------------------------------------------------------------------------- #
def generate_one(app: App, llm: LLM, product: dict, platform: str) -> dict:
    ctx = gather_context(app, llm, product, platform)
    plan = strategist.plan_content(
        app, llm, product, platform,
        trends=ctx["trends"], winners=ctx["winners"], bandit_picks=ctx["bandit_picks"],
    )

    examples = winner_examples(app, llm, product, platform, plan)
    feedback = recent_rejection_feedback(app, product, platform)
    draft = writer.write_content(app, llm, product, platform, plan,
                                 winner_examples=examples, user_feedback=feedback)

    # Novelty guard — one regeneration attempt with a "make it different" nudge.
    novelty = check_novelty(app, llm, product, platform, draft)
    if not novelty.ok:
        draft = writer.write_content(app, llm, product, platform, plan,
                                     winner_examples=examples, user_feedback=feedback,
                                     novelty_similar=novelty.similar_caption)
        novelty = check_novelty(app, llm, product, platform, draft)

    strategy_context = {
        "topic": plan.topic, "angle": plan.angle, "hook_style": plan.hook_style,
        "tone": plan.tone, "trend_tie_in": plan.trend_tie_in, "reasoning": plan.reasoning,
        "novelty_max_sim": round(novelty.max_sim, 4),
        "bandit_picks": ctx["bandit_picks"],
    }

    # Save the draft FIRST (spec: content is always reviewable; also gives us an id
    # to namespace media files under). The full ContentDraft is persisted so the
    # web app can edit scripts/prompts/slides and regenerate media later.
    content_id = store.insert_content(
        app.conn,
        product_id=product["id"], platform=platform, content_type=plan.content_type,
        caption=draft.caption, hashtags=draft.hashtags, hook=draft.hook,
        media_paths=[], media_urls=[], strategy_context=strategy_context, status="draft",
        draft=draft.model_dump(),
    )

    # Media generation with the spec-mandated fallback (video fails → try image).
    media = _produce_media_with_fallback(app, llm, product, content_id, plan, draft)
    store.set_content_status(
        app.conn, content_id, "draft",
        content_type=plan.content_type, media_paths=media["media_paths"],
        media_urls=media["media_urls"],
    )

    from . import db as db_module

    db_module.log_activity(app.conn, "generate",
                           f"Drafted {plan.content_type} for {platform}: “{draft.hook}”",
                           product_id=product["id"], content_id=content_id)
    _maybe_auto_approve(app, content_id, plan.content_type)
    return store.get_content(app.conn, content_id)


# --------------------------------------------------------------------------- #
# Editing / regeneration (used by the web app)
# --------------------------------------------------------------------------- #
def _plan_from_content(content: dict):
    """Reconstruct a ContentPlan from a stored content row."""
    from . import db as db_module
    from .schemas import ContentPlan

    sc = db_module.loads(content.get("strategy_context"), {}) or {}
    return ContentPlan(
        platform=content["platform"], content_type=content["content_type"],
        topic=sc.get("topic", ""), angle=sc.get("angle", ""),
        hook_style=sc.get("hook_style", "question"), tone=sc.get("tone", "relatable"),
        trend_tie_in=sc.get("trend_tie_in"), reasoning=sc.get("reasoning", ""),
    )


def _draft_from_content(content: dict):
    """Rebuild the ContentDraft from a stored row (draft JSON + edited columns)."""
    from . import db as db_module
    from .schemas import ContentDraft

    raw = db_module.loads(content.get("draft"), {}) or {}
    draft = ContentDraft.model_validate(raw) if raw else ContentDraft(
        caption=content["caption"] or "", hashtags=[], hook=content["hook"] or "")
    # The caption/hook/hashtags columns are the source of truth (user-editable).
    draft.caption = content["caption"] or draft.caption
    draft.hook = content["hook"] or draft.hook
    draft.hashtags = db_module.loads(content.get("hashtags"), draft.hashtags) or []
    return draft


def regenerate_media(app: App, llm: LLM, content_id: int) -> dict:
    """Re-run media generation for a content row using its (possibly edited)
    stored draft — e.g. after the user tweaks the image prompt or script."""
    content = store.get_content(app.conn, content_id)
    if not content:
        raise ValueError(f"content {content_id} not found")
    product = store.get_product(app.conn, content["product_id"])
    plan = _plan_from_content(content)
    draft = _draft_from_content(content)

    media = _produce_media_with_fallback(app, llm, product, content_id, plan, draft)
    store.update_content(app.conn, content_id,
                         content_type=plan.content_type,
                         media_paths=media["media_paths"], media_urls=media["media_urls"],
                         error=None)
    from . import db as db_module

    db_module.log_activity(app.conn, "media",
                           f"Regenerated media for content #{content_id}",
                           product_id=product["id"], content_id=content_id)
    return store.get_content(app.conn, content_id)


def rewrite_content(app: App, llm: LLM, content_id: int,
                    instruction: Optional[str] = None) -> dict:
    """Rewrite a draft's copy (optionally steered by a user instruction), keeping
    the same plan. Media is NOT regenerated automatically — the caller decides."""
    content = store.get_content(app.conn, content_id)
    if not content:
        raise ValueError(f"content {content_id} not found")
    product = store.get_product(app.conn, content["product_id"])
    platform = content["platform"]
    plan = _plan_from_content(content)

    examples = winner_examples(app, llm, product, platform, plan)
    feedback = recent_rejection_feedback(app, product, platform)
    if instruction:
        feedback = [instruction] + feedback
    draft = writer.write_content(app, llm, product, platform, plan,
                                 winner_examples=examples, user_feedback=feedback)

    store.update_content(app.conn, content_id,
                         caption=draft.caption, hashtags=draft.hashtags, hook=draft.hook,
                         draft=draft.model_dump())
    from . import db as db_module

    db_module.log_activity(app.conn, "rewrite",
                           f"Rewrote copy for content #{content_id}"
                           + (f" — “{instruction[:60]}”" if instruction else ""),
                           product_id=product["id"], content_id=content_id)
    return store.get_content(app.conn, content_id)


def _produce_media_with_fallback(app, llm, product, content_id, plan, draft) -> dict:
    try:
        return media_orch.produce_media(app, llm, product, content_id, plan, draft)
    except Exception as exc:  # noqa: BLE001
        if plan.content_type in ("image", "text", "thread"):
            # Nothing simpler to fall back to.
            return {"media_paths": [], "media_urls": []}
        # Fall back to a single image.
        from .agents.media import media_dir_for
        from .media import images

        try:
            plan.content_type = "image"
            if not draft.image_prompt:
                draft.image_prompt = f"{plan.topic} — social visual"
            out_dir = media_dir_for(app, product["id"], content_id)
            size = images.platform_size(plan.platform, "image")
            path = out_dir / f"{content_id}_{plan.platform}_image.png"
            images.generate_image(app, llm, draft.image_prompt, path, size=size,
                                  content_id=content_id, product_id=product["id"])
            return {"media_paths": [str(path)], "media_urls": []}
        except Exception:
            return {"media_paths": [], "media_urls": []}


def _maybe_auto_approve(app: App, content_id: int, content_type: str) -> None:
    cfg = app.settings.approval
    if cfg.auto_approve or content_type in (cfg.auto_approve_types or []):
        store.set_content_status(app.conn, content_id, "approved", approved_at=_now())


def generate_all(app: App, llm: LLM, product: dict,
                 platforms: Optional[list[str]] = None, count: int = 1) -> list[dict]:
    platforms = platforms or [p for p in product_platforms(product)
                              if app.settings.platform(p).enabled]
    results = []
    for platform in platforms:
        for _ in range(max(1, count)):
            results.append(generate_one(app, llm, product, platform))
    return results


def product_platforms(product: dict) -> list[str]:
    from . import db as db_module

    return db_module.loads(product["platforms"], []) or []
