"""Writer agent — generates platform-specific copy + media prompts.

Quality pipeline (all toggled in config under `llm:`):
  1. Generate `variants` candidate drafts.
  2. If >1, an LLM judge picks the strongest (hook / brand-fit / scroll-stopping).
  3. A self-critique pass enforces the anti-slop rules and revises if needed.
  4. Finalize: trim hashtags to platform limits, enforce length caps, backfill
     any missing media prompts.
"""

from __future__ import annotations

import re
from typing import Optional

from .. import prompts
from ..app import App
from ..llm import LLM
from ..schemas import ContentDraft, CritiqueResult, JudgeVerdict

# Platform hard length caps (safety net; the prompt already asks for these).
LENGTH_CAPS = {"x": 280, "bluesky": 300, "threads": 500}


def write_content(
    app: App,
    llm: LLM,
    product: dict,
    platform: str,
    plan,
    *,
    winner_examples: Optional[list[dict]] = None,
    novelty_similar: Optional[str] = None,
    user_feedback: Optional[list[str]] = None,
    content_id: Optional[int] = None,
    strategy=None,
    episode: int = 1,
    character: Optional[dict] = None,
    bandit_picks: Optional[dict] = None,
) -> ContentDraft:
    winner_examples = winner_examples or []
    system = prompts.writer_system(product, platform, plan, winner_examples,
                                   strategy=strategy, episode=episode, character=character)
    user = prompts.writer_user(plan)
    if user_feedback:
        user += prompts.writer_feedback_section(user_feedback)
    if novelty_similar:
        user += prompts.writer_novelty_nudge(novelty_similar)

    n_variants = max(1, int(app.settings.llm.variants))
    drafts = []
    for i in range(n_variants):
        d = llm.parse(
            system, user, ContentDraft,
            model=app.settings.llm.text_model,
            temperature=min(0.95, 0.85 + 0.05 * i),
            product_id=product["id"], content_id=content_id,
            mock_factory=lambda i=i: _mock_draft(product, platform, plan, i),
        )
        drafts.append(d)

    draft = drafts[0] if len(drafts) == 1 else _judge(app, llm, product, platform, drafts, content_id)

    if app.settings.llm.self_critique:
        draft = _critique(app, llm, product, platform, draft, content_id)

    # Humor engine: strategies opt in via humor_level; a bare "funny" tone from
    # the strategist gets the light pass so tone-funny content is actually funny.
    humor_level = getattr(strategy, "humor_level", "none") if strategy else "none"
    if humor_level == "none" and plan.tone == "funny":
        humor_level = "light"
    if humor_level != "none":
        from .. import humor

        draft = humor.punch_up(app, llm, product, platform, plan, draft,
                               level=humor_level, bandit_picks=bandit_picks,
                               character=character, content_id=content_id)

    return _finalize(draft, app, platform, plan)


# --------------------------------------------------------------------------- #
# Variant judging
# --------------------------------------------------------------------------- #
def _judge(app: App, llm: LLM, product: dict, platform: str, drafts: list[ContentDraft],
           content_id) -> ContentDraft:
    verdict = llm.parse(
        prompts.judge_system(product, platform),
        prompts.judge_user(drafts),
        JudgeVerdict,
        model=app.settings.llm.judge_model,
        temperature=0.2,
        product_id=product["id"], content_id=content_id,
        mock_factory=lambda: _mock_verdict(drafts),
    )
    idx = verdict.best_index if 0 <= verdict.best_index < len(drafts) else 0
    return drafts[idx]


def _mock_verdict(drafts: list[ContentDraft]) -> JudgeVerdict:
    # Offline heuristic: prefer the punchiest non-empty hook (fewest words, but >=3).
    def score(d: ContentDraft) -> float:
        words = len((d.hook or "").split())
        return -abs(words - 6)  # closest to ~6 words wins
    best = max(range(len(drafts)), key=lambda i: score(drafts[i]))
    return JudgeVerdict(best_index=best, hook_strength=7.0, brand_fit=7.0,
                        scroll_stopping=7.0, reasoning="offline: punchiest hook")


# --------------------------------------------------------------------------- #
# Self-critique
# --------------------------------------------------------------------------- #
def _critique(app: App, llm: LLM, product: dict, platform: str, draft: ContentDraft,
              content_id) -> ContentDraft:
    result = llm.parse(
        prompts.critique_system(product, platform),
        prompts.critique_user(draft),
        CritiqueResult,
        model=app.settings.llm.judge_model,
        temperature=0.3,
        product_id=product["id"], content_id=content_id,
        mock_factory=lambda: _mock_critique(draft),
    )
    if result.needs_revision:
        if result.revised_caption:
            draft.caption = result.revised_caption
        if result.revised_hook:
            draft.hook = result.revised_hook
    return draft


def _mock_critique(draft: ContentDraft) -> CritiqueResult:
    """Real offline anti-slop enforcement: strip banned phrases."""
    new_caption, removed1 = _strip_slop(draft.caption or "")
    new_hook, removed2 = _strip_slop(draft.hook or "")
    problems = sorted(set(removed1 + removed2))
    needs = bool(problems)
    return CritiqueResult(
        needs_revision=needs,
        problems=[f'removed slop phrase: "{p}"' for p in problems],
        revised_caption=new_caption if needs else None,
        revised_hook=new_hook if needs else None,
    )


def _strip_slop(text: str) -> tuple[str, list[str]]:
    removed = []
    out = text
    for phrase in prompts.BANNED_PHRASES:
        if phrase.lower() in out.lower():
            removed.append(phrase)
            out = re.sub(re.escape(phrase), "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, removed


# --------------------------------------------------------------------------- #
# Finalize
# --------------------------------------------------------------------------- #
def _finalize(draft: ContentDraft, app: App, platform: str, plan) -> ContentDraft:
    pconf = app.settings.platform(platform)

    # Hashtags: dedupe, normalize leading '#', trim to platform count.
    seen, tags = set(), []
    for h in draft.hashtags or []:
        h = h.strip()
        if not h:
            continue
        if not h.startswith("#"):
            h = "#" + re.sub(r"\s+", "", h)
        key = h.lower()
        if key not in seen:
            seen.add(key)
            tags.append(h)
    draft.hashtags = tags[: pconf.hashtag_count]

    # Hook fallback.
    if not (draft.hook or "").strip():
        draft.hook = (draft.caption or "").strip().split("\n", 1)[0][:80]

    # Length safety net for short-form platforms.
    cap = LENGTH_CAPS.get(platform)
    if cap and draft.caption and len(draft.caption) > cap:
        draft.caption = draft.caption[: cap - 1].rstrip() + "…"

    # Backfill media prompts so downstream media gen always has what it needs.
    if plan.content_type in ("image", "video") and not draft.image_prompt:
        draft.image_prompt = f"{plan.topic} — {plan.tone}, scroll-stopping social visual"
    if plan.content_type == "carousel" and not draft.image_prompts:
        slides = draft.slide_texts or [draft.hook, draft.caption]
        draft.image_prompts = [f"{plan.topic} slide: {s[:60]}" for s in slides]
    if plan.content_type == "video":
        if not draft.video_prompt:
            draft.video_prompt = draft.image_prompt
        if not draft.script:
            draft.script = draft.caption
        if not draft.video_style:
            draft.video_style = "text_overlay"
    return draft


# --------------------------------------------------------------------------- #
# Offline draft generation
# --------------------------------------------------------------------------- #
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _hook_for(style: str, name: str, variant: int) -> str:
    options = {
        "question": [f"What if applying took 10 seconds?", f"Still doing this by hand?"],
        "bold_claim": [f"You're doing this the slow way.", f"{name} ends the busywork."],
        "story": [f"I did 200 of these last month.", f"This used to take me all day."],
        "statistic": [f"People waste 23 hours a week on this.", f"90% give up before they finish."],
        "pain_point": [f"Doing the same thing 50 times is brutal.", f"The worst part isn't the work."],
        "before_after": [f"Before {name}: 3 hours. After: 3 minutes.", f"Old way vs. {name}."],
    }
    pool = options.get(style, [f"Meet {name}."])
    return pool[variant % len(pool)]


def _hashtag_pool(product: dict, platform: str) -> list[str]:
    slug = _slug(product["name"])
    base = [f"#{slug}", "#buildinpublic", "#startup", "#productivity", "#automation",
            "#tech", "#founder", "#tools", "#workflow", "#saas", "#indiehacker",
            "#career", "#students", "#hustle", "#growth", "#marketing"]
    return base


def _mock_draft(product: dict, platform: str, plan, variant: int) -> ContentDraft:
    name = product["name"]
    url = product.get("website_url")
    hook = _hook_for(plan.hook_style, name, variant)
    body = (f"{plan.angle.capitalize()}. {name} takes the painful, repetitive part of "
            f"{plan.topic.lower()} and just... handles it. No fluff, no setup headache.")
    cta = "Try it — link in bio." if platform in ("tiktok", "instagram", "youtube") else \
        ("See how 👇" if platform in ("x", "threads", "bluesky") else "What would you automate first?")

    if platform == "linkedin":
        caption = f"{hook}\n\n{body}\n\nWe built {name} because the manual way was wasting everyone's time.\n\n{cta}"
    elif platform in ("x", "bluesky", "threads"):
        caption = f"{hook} {body[:140]} {cta}"
    else:
        caption = f"{hook}\n\n{body}\n\n{cta}"

    tags = _hashtag_pool(product, platform)
    draft = ContentDraft(
        caption=caption.strip(),
        hashtags=tags,
        hook=hook,
        cta=cta,
        alt_text=f"Promotional visual for {name}: {plan.topic}",
        image_prompt=f"{plan.topic}. {plan.tone} mood, bold composition, social-media ready, "
                     f"vertical, high contrast, no text",
    )
    if plan.content_type == "video":
        draft.script = f"{hook}\n{body}\n{cta}"
        draft.video_prompt = draft.image_prompt
        draft.video_style = "text_overlay"
    if plan.content_type in ("carousel",):
        draft.slide_texts = [
            hook,
            f"The problem: {plan.topic.lower()} eats your time.",
            f"What most people do: grind through it manually.",
            f"What {name} does: automates the boring 90%.",
            f"The result: hours back every week.",
            cta,
        ]
        draft.image_prompts = [f"Carousel slide, bold text area, {plan.tone} mood: {s[:50]}"
                               for s in draft.slide_texts]
    if url and platform == "x":
        # Link goes in a reply, never the main post (spec). We stash it in cta-less form.
        draft.cta = "link in reply 👇"
    return draft
