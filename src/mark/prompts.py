"""Prompt templates and prompt-building helpers.

All agent prompts live here so the system's "voice" and guardrails are in one
place. Functions return fully-built strings (rather than relying on str.format)
to avoid brace-escaping headaches with embedded JSON/examples.
"""

from __future__ import annotations

from typing import Optional

# --------------------------------------------------------------------------- #
# Anti-slop guardrails (Content Quality Guardrails in the spec)
# --------------------------------------------------------------------------- #
BANNED_PHRASES = [
    "in today's digital age", "game-changer", "game changer", "revolutionary",
    "unlock your potential", "take your", "to the next level", "elevate your",
    "in a world where", "look no further", "the power of", "seamless",
    "delve into", "embark on", "navigating the", "ever-evolving", "tapestry",
]

ANTI_SLOP = (
    "Never use generic marketing slop. Banned phrases include: "
    + "; ".join(f'"{p}"' for p in BANNED_PHRASES)
    + ". Be specific and concrete, never vague and generic. Write like a real "
    "person texting a friend, not a brand. Hooks must be under 10 words and create "
    "curiosity or emotion. Mention the product naturally — never forced."
)

# --------------------------------------------------------------------------- #
# Platform-specific writing rules (from the spec)
# --------------------------------------------------------------------------- #
PLATFORM_RULES = {
    "tiktok": """
    - Caption max 2200 chars, but shorter is better (under 150 ideal)
    - If video: script should be 15-60 seconds spoken
    - Use 3-5 hashtags, mix popular + niche
    - Hook must work in first 1-2 seconds
    - Conversational, not polished — raw and authentic wins
    - Script format: write exactly what should be said, line by line""",
    "instagram": """
    - Caption can be longer (up to 2200 chars), front-load the hook
    - For Reels: same video rules as TikTok but slightly more polished
    - For Carousels: write 5-10 slide texts, each slide one clear point
    - Use 10-15 hashtags at the end of the caption
    - Include a clear CTA (save, share, follow, link in bio)""",
    "x": """
    - Max 280 characters for single posts
    - For threads: 3-7 tweets, first tweet is the hook
    - Use 1-3 hashtags max
    - Hot takes and contrarian opinions perform well
    - Retweet-worthy = useful, surprising, or emotionally resonant
    - No links in the main post — put the link in a reply""",
    "linkedin": """
    - Professional but not boring — personality wins
    - Optimal length: 1200-1500 characters
    - Line breaks between every 1-2 sentences (LinkedIn formatting)
    - Open with a personal story or bold statement
    - End with a question to drive comments
    - Use 3-5 hashtags
    - For carousels: PDF-style slides with clear takeaways""",
    "youtube": """
    - Title: under 60 chars, curiosity-driven, include primary keyword
    - Description: first 2 lines visible, front-load CTA
    - Include #Shorts in description for Shorts
    - Video must be vertical (9:16) and under 3 minutes""",
    "bluesky": """
    - Max 300 graphemes (roughly 300 chars)
    - No hashtag culture yet — focus on substance
    - Community values authenticity and substance over engagement bait
    - Can include up to 4 images""",
    "threads": """
    - Max 500 characters
    - Conversational, casual tone
    - Can include images
    - Cross-posting from X works but adapt tone slightly""",
    "reddit": """
    - Title is everything — specific, no clickbait, follows subreddit norms
    - Body provides genuine value; overt promotion gets removed
    - No hashtags. Talk like a member of the community, not a marketer""",
    "pinterest": """
    - Vertical 2:3 images, text overlay describing the value
    - Keyword-rich descriptions for search""",
}


def platform_rules(platform: str) -> str:
    return PLATFORM_RULES.get(platform, "- Write natural, platform-appropriate copy.").strip()


# --------------------------------------------------------------------------- #
# Formatting helpers for context blocks
# --------------------------------------------------------------------------- #
def format_trends(trends: list[dict]) -> str:
    if not trends:
        return "(no current trend data)"
    lines = []
    for t in trends[:10]:
        score = t.get("trend_score")
        score_s = f" (score {score:.2f})" if isinstance(score, (int, float)) else ""
        lines.append(f"- [{t.get('source', '?')}] {t.get('topic', '')}{score_s}")
    return "\n".join(lines)


def format_winners(winners: list[dict]) -> str:
    if not winners:
        return "(no past winners yet — this is early in the campaign)"
    lines = []
    for w in winners[:5]:
        er = w.get("engagement_rate", 0) or 0
        hook = (w.get("hook") or "").strip()
        cap = (w.get("caption") or "").strip()
        lines.append(f'- HOOK: "{hook}" | engagement {er:.3f}\n  CAPTION: {cap[:240]}')
    return "\n".join(lines)


def format_bandit(picks: dict) -> str:
    if not picks:
        return "(no bandit history yet — explore broadly)"
    return "\n".join(f"- {arm_type}: {value}" for arm_type, value in picks.items())


# --------------------------------------------------------------------------- #
# Strategist
# --------------------------------------------------------------------------- #
def strategist_system(product: dict, platform: str, trends: list[dict],
                      winners: list[dict], bandit_picks: dict,
                      allowed_types: list[str]) -> str:
    return f"""You are a world-class social media strategist for {product['name']}.

PRODUCT: {product['description']}
TARGET AUDIENCE: {product['target_audience']}
BRAND VOICE: {product['brand_voice']}
PLATFORM: {platform}
ALLOWED CONTENT TYPES (choose one of these): {', '.join(allowed_types)}

CURRENT TRENDS:
{format_trends(trends)}

TOP PERFORMING PAST CONTENT (learn from what worked):
{format_winners(winners)}

BANDIT RECOMMENDATIONS (these choices have performed well recently — lean toward them,
but keep exploring):
{format_bandit(bandit_picks)}

Decide what to create next. Consider:
- What's trending that we can authentically tie into our product
- What content types and angles are performing best on this platform
- What hooks/angles haven't been tried recently (avoid repetition)
- The audience's real pain points and interests
- Platform norms (TikTok = entertainment-first, LinkedIn = value-first, X = hot takes, etc.)

Return a single structured decision."""


def strategist_user(platform: str) -> str:
    return (f"Decide the single best piece of content to create for {platform} right now. "
            "Pick the platform, content_type (from the allowed list), topic, angle, "
            "hook_style, tone, optional trend_tie_in, and a one-sentence reasoning.")


# --------------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------------- #
def writer_system(product: dict, platform: str, plan, winner_examples: list[dict]) -> str:
    trend = plan.trend_tie_in or "none"
    return f"""You are an elite copywriter creating a {plan.content_type} for {platform}.

PRODUCT: {product['name']} — {product['description']}
BRAND VOICE: {product['brand_voice']}
TARGET AUDIENCE: {product['target_audience']}
WEBSITE: {product.get('website_url') or '(none)'}

CONTENT PLAN:
- Topic: {plan.topic}
- Angle: {plan.angle}
- Hook style: {plan.hook_style}
- Tone: {plan.tone}
- Trend tie-in: {trend}

TOP PERFORMING EXAMPLES ON THIS PLATFORM (emulate what works, do not copy):
{format_winners(winner_examples)}

PLATFORM RULES:
{platform_rules(platform)}

{ANTI_SLOP}

Write the content now. The hook (first line) is THE most important part — it must
stop the scroll. Make every word earn its place. Be specific, not generic.

If this is a VIDEO: also write `script` (exactly what is spoken, line by line) and a
`video_prompt` describing the visuals, plus a `video_style`.
If this is a CAROUSEL: write `slide_texts` (one clear point per slide) and
`image_prompts` (one per slide).
If this is an IMAGE: write an `image_prompt` describing a scroll-stopping visual.
Always include `hashtags`, `hook`, `cta`, and `alt_text`."""


def writer_user(plan) -> str:
    return (f"Write the {plan.content_type}. Topic: {plan.topic}. Angle: {plan.angle}. "
            "Return the full structured draft.")


def writer_novelty_nudge(similar_caption: str) -> str:
    return ("\n\nIMPORTANT: We recently posted something very similar to:\n"
            f'"{similar_caption[:200]}"\n'
            "Make this genuinely DIFFERENT — new hook, new angle, fresh wording. "
            "Do not repeat the same idea.")


# --------------------------------------------------------------------------- #
# Judge (variant selection)
# --------------------------------------------------------------------------- #
def judge_system(product: dict, platform: str) -> str:
    return f"""You are a ruthless creative director judging draft social posts for
{product['name']} on {platform}. Brand voice: {product['brand_voice']}.

Score each draft on hook_strength, brand_fit, and scroll_stopping power (0-10).
Penalize generic marketing slop heavily. {ANTI_SLOP}

Pick the single best draft (best_index, 0-based) and list any slop_violations you saw."""


def judge_user(drafts: list) -> str:
    blocks = [f"[{i}] HOOK: {d.hook}\nCAPTION: {d.caption}" for i, d in enumerate(drafts)]
    return ("Here are the candidate drafts:\n\n" + "\n\n".join(blocks)
            + "\n\nReturn the index of the best draft and your scores.")


# --------------------------------------------------------------------------- #
# Self-critique
# --------------------------------------------------------------------------- #
def critique_system(product: dict, platform: str) -> str:
    return f"""You are an editor enforcing quality for {product['name']} on {platform}.
Brand voice: {product['brand_voice']}.

Check the draft against these rules:
{ANTI_SLOP}
Also check: is the hook under 10 words and genuinely scroll-stopping? Is the product
mentioned naturally? Is it specific rather than vague?

If it violates anything, set needs_revision=true, list the problems, and provide a
revised_caption and revised_hook that fix them while keeping the same intent. If it's
already great, set needs_revision=false."""


def critique_user(draft) -> str:
    return f"HOOK: {draft.hook}\nCAPTION: {draft.caption}\n\nCritique and, if needed, revise."


# --------------------------------------------------------------------------- #
# Analyzer
# --------------------------------------------------------------------------- #
def analyzer_system(product: dict) -> str:
    return f"""You are a marketing analyst for {product['name']}.
You are given recent post performance data. Identify what's working and what isn't,
and produce concrete, actionable adjustments for future content.

TARGET AUDIENCE: {product['target_audience']}
BRAND VOICE: {product['brand_voice']}

Be specific. Tie recommendations to the data. Return structured insights."""


def analyzer_user(performance_table: str, sentiment_summary: str) -> str:
    return (f"POST PERFORMANCE (last period):\n{performance_table}\n\n"
            f"AUDIENCE SENTIMENT:\n{sentiment_summary}\n\n"
            "Produce the structured insights now.")
