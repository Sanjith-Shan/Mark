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
        style = (t.get("style_notes") or "").strip()
        if style:
            lines.append(f"  how it's being executed: {style}")
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
# Strategy blocks (from the strategy framework — strategies.py)
# --------------------------------------------------------------------------- #
def strategy_block(strategy, platform: str, episode: int = 1) -> str:
    """The shared strategy header injected into both strategist and writer."""
    if strategy is None:
        return ""
    note = strategy.platform_note(platform)
    lines = [
        f"\nACTIVE STRATEGY: {strategy.name} ({strategy.id})",
        f"WHY IT WORKS: {strategy.description}",
        f"EMOTIONAL TARGET: make the viewer feel {strategy.emotional_target}.",
    ]
    if note:
        lines.append(f"ON {platform.upper()}: {note}")
    if strategy.series_format:
        lines.append(f"THIS IS A SERIES — episode {episode}. Format: {strategy.series_format}")
    return "\n".join(lines)


def strategy_examples_block(strategy) -> str:
    if not strategy or not strategy.example_sketches:
        return ""
    ex = "\n".join(f"- {s}" for s in strategy.example_sketches[:3])
    return f"\nWHAT GREAT OUTPUT UNDER THIS STRATEGY LOOKS LIKE (flavor, don't copy):\n{ex}"


def character_block(character: Optional[dict]) -> str:
    """Injected into the writer when a persistent character fronts the content."""
    if not character:
        return ""
    phrases = character.get("catchphrases") or []
    phrase_line = ("\nCATCHPHRASES (use sparingly, max one per post): "
                   + "; ".join(f'"{p}"' for p in phrases[:5])) if phrases else ""
    return f"""
THIS CONTENT IS FRONTED BY A PERSISTENT CHARACTER — write AS them, not about them.
CHARACTER: {character['name']} ({character.get('role') or 'ambassador'})
PERSONA: {character['persona']}
APPEARANCE (for media prompts): {character['visual_desc']}{phrase_line}
Stay ruthlessly in character. The character's voice OVERRIDES the default brand
voice where they conflict. Never break the fourth wall about being AI unless the
persona explicitly plays with that."""


# --------------------------------------------------------------------------- #
# Strategist
# --------------------------------------------------------------------------- #
def strategist_system(product: dict, platform: str, trends: list[dict],
                      winners: list[dict], bandit_picks: dict,
                      allowed_types: list[str], strategy=None, episode: int = 1,
                      forced_trend: Optional[dict] = None) -> str:
    strat = strategy_block(strategy, platform, episode)
    strat_brief = f"\nSTRATEGY BRIEF: {strategy.strategist_brief}" if strategy and strategy.strategist_brief else ""
    forced = ""
    if forced_trend:
        style = (forced_trend.get("style_notes") or "").strip()
        forced = (f"\nNON-NEGOTIABLE: this content MUST ride the trend "
                  f"“{forced_trend.get('topic')}” — it is spiking right now and speed "
                  "matters more than polish. Tie it to the product authentically; if the "
                  "product angle would ruin the joke, let the trend carry and keep the "
                  "product to the caption."
                  + (f"\nHOW CREATORS ARE EXECUTING IT: {style}" if style else ""))
    return f"""You are a world-class social media strategist for {product['name']}.
{strat}{strat_brief}{forced}

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
def writer_system(product: dict, platform: str, plan, winner_examples: list[dict],
                  strategy=None, episode: int = 1, character: Optional[dict] = None) -> str:
    trend = plan.trend_tie_in or "none"
    strat = strategy_block(strategy, platform, episode)
    strat_brief = f"\nSTRATEGY BRIEF: {strategy.writer_brief}" if strategy and strategy.writer_brief else ""
    media_brief = f"\nMEDIA STYLE: {strategy.media_brief}" if strategy and strategy.media_brief else ""
    examples = strategy_examples_block(strategy)
    char = character_block(character)
    return f"""You are an elite copywriter creating a {plan.content_type} for {platform}.
{strat}{strat_brief}{media_brief}{examples}{char}

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


def writer_feedback_section(feedback: list[str]) -> str:
    notes = "\n".join(f"- {f}" for f in feedback[:6])
    return ("\n\nDIRECT FEEDBACK FROM THE OWNER (previous drafts were rejected for these "
            "reasons — do NOT repeat these mistakes, treat them as hard requirements):\n"
            f"{notes}")


def writer_novelty_nudge(similar_caption: str) -> str:
    return ("\n\nIMPORTANT: We recently posted something very similar to:\n"
            f'"{similar_caption[:200]}"\n'
            "Make this genuinely DIFFERENT — new hook, new angle, fresh wording. "
            "Do not repeat the same idea.")


# --------------------------------------------------------------------------- #
# Humor engine (humor.py) — grounded in docs/research/humor-mechanics.md
# --------------------------------------------------------------------------- #
# Hedges and humor-slop that kill jokes: never explain, never soften.
HUMOR_BANNED = [
    "just kidding", "we've all been there", "am i right", "amirite",
    "because let's face it", "if you know you know", "lol right",
    "wacky", "zany", "hilarious", "😂😂", "who can relate",
]

HUMOR_RULES = (
    "IRON RULES OF THE JOKE:\n"
    "1. NEVER explain the joke. The piece ENDS on the punch — no sentence after the "
    "punch word, no restating the premise, no trailing emoji laughing at itself.\n"
    "2. The punch word goes LAST. Put a beat (line break) before the final line.\n"
    "3. Punch UP or SIDEWAYS only: at institutions, processes, the absurd system, or "
    "the brand itself. Never at the audience or any vulnerable group.\n"
    "4. Be hyper-specific. Concrete, lived details ('the Workday account you made for "
    "one application in 2023') beat categories ('job applications are annoying'). "
    "At least one hyper-specific detail per piece.\n"
    "5. Surprise is non-negotiable — if the reader can guess the ending, it is dead.\n"
    "6. Banned humor-slop: " + "; ".join(f'"{p}"' for p in HUMOR_BANNED) + "."
)

PERSONA_VOICES = {
    "cynic": "dry, seen-it-all, dark around the edges; finds the bleak detail and states it plainly",
    "absurdist": "commits to complete nonsense with a perfectly straight face; internally consistent lunacy",
    "deadpan_observer": "flat, factual delivery of devastatingly specific observations; zero exclamation points",
    "neurotic_student": "first-person spiraling anxiety played for laughs; escalating inner monologue",
    "corporate_parodist": "speaks fluent recruiter/HR-ese and weaponizes it; the language itself is the joke",
    "unhinged_ai": "openly a machine and makes THAT the bit; cheerful menace; treats being an unsupervised marketing script as normal",
}

MECHANISM_RECIPES = {
    "setup_subversion": (
        "SETUP-SUBVERSION: the setup builds a false 1st story via a connector (one element "
        "with two readings); the punchline reveals the 2nd reading and shatters the target "
        "assumption. You must be able to name: target_assumption, connector, reinterpretation, "
        "punch_word. Reveal goes last."),
    "rule_of_three": (
        "RULE OF THREE: items 1 and 2 establish a clean pattern (parallel, similar length); "
        "item 3 is slightly longer and carries the violation. Item 3 must be the funny one."),
    "escalation": (
        "ESCALATION: one 'first unusual thing' stated in the first beat, then 3-5 heightens, "
        "each answering 'if that's true, what else is true?' — premise-consistent and bigger "
        "each time. End at the peak, or loop back to the opening."),
    "anti_humor": (
        "ANTI-HUMOR: play a saturated format perfectly straight and land a flat, literal, "
        "abrupt payoff where the punchline should be. The missing joke IS the joke. Deadpan "
        "throughout; do not wink."),
    "absurdist_lore": (
        "ABSURDIST LORE: self-aware AI absurdism. Rigid template, escalating lore, entities "
        "with repetitive/rhythmic names. Obvious artificiality is the aesthetic — acknowledge "
        "machine identity as part of the bit. Never explain the lore."),
    "observational_specific": (
        "OBSERVATIONAL SPECIFICITY: name the hyper-specific shared experience the audience "
        "thought only they had, and say the quiet part too honestly. The specificity does the "
        "comedic work — no twist needed, just recognition sharp enough to sting."),
    "callback": (
        "CALLBACK: bring back an earlier bit/character/phrase from this account's history in "
        "a new context. Reward followers for paying attention. NEVER explain the reference."),
}


def violation_search_system(product: dict, platform: str, specificity_bank: list[str]) -> str:
    bank = "\n".join(f"- {s}" for s in specificity_bank[:8]) if specificity_bank else "(none yet)"
    return f"""You are a comedy writer mining for material for {product['name']} on {platform}.

AUDIENCE: {product['target_audience']}

THE THEORY (benign violation): a laugh needs something simultaneously WRONG (violates
how the world ought to be) and SAFE (harmless for this audience). Too safe = boring.
Too wrong = offensive. Funny lives on the ridge between.

RAW MATERIAL — real artifacts of this audience's life (use these, add your own):
{bank}

List candidate violations about the given topic: things that are wrong, absurd, or
secretly-true-but-never-said — each safe for this audience because it punches at the
system/process/institutions (or the brand itself), never at the audience.
Score each: strength (how strongly it violates expectations, 0-1) and benignness
(how safe it is, 0-1). Name the target of each. Discard nothing — list them all,
weak ones included; ranking happens later."""


def violation_search_user(topic: str, angle: str) -> str:
    return (f"Topic: {topic}\nAngle: {angle}\n\n"
            "List 8-12 candidate violations with strength, benignness, and target.")


def humor_fanout_system(product: dict, platform: str, plan, violation,
                        personas: list[str], mechanism: str,
                        specificity_bank: list[str], character: Optional[dict] = None) -> str:
    persona_lines = "\n".join(f"- {p}: {PERSONA_VOICES.get(p, p)}" for p in personas)
    recipe = MECHANISM_RECIPES.get(mechanism, "")
    bank = "\n".join(f"- {s}" for s in specificity_bank[:6]) if specificity_bank else "(none)"
    char = character_block(character)
    return f"""You are a punch-up room writing {plan.content_type} comedy for {product['name']} on {platform}.
{char}
THE VIOLATION TO BUILD ON (this is the joke's engine):
"{violation.violation}" (punches at: {violation.target})

STRUCTURE TO USE:
{recipe}

WRITE ONE CANDIDATE PER PERSONA — each persona forces a different direction:
{persona_lines}

SPECIFICITY BANK (weave in real artifacts of the audience's life):
{bank}

{HUMOR_RULES}

For each candidate fill the full scaffold: persona, mechanism ("{mechanism}"),
hook (the scroll-stopping opening — it doubles as the setup), caption, script (only
if this is a video — exactly what is spoken, the punch beat on its own line),
target_assumption, connector, reinterpretation, punch_word.
If you cannot name all four scaffold fields for a candidate, that candidate is not
a joke yet — rework it until you can."""


def humor_fanout_user(plan, draft) -> str:
    base = f"Topic: {plan.topic}\nAngle: {plan.angle}\n"
    base += f"Current (unfunny) draft to transform:\nHOOK: {draft.hook}\nCAPTION: {draft.caption}"
    if draft.script:
        base += f"\nSCRIPT: {draft.script}"
    return base + "\n\nWrite the candidates now — one per persona."


def pairwise_judge_system(product: dict, platform: str) -> str:
    return f"""You judge which of two comedy drafts is FUNNIER for {product['name']} on {platform}.
Audience: {product['target_audience']}

Compare PAIRWISE (never absolute scores). The funnier draft is the one with:
- a genuine violation (something actually wrong/absurd, not humor-shaped blandness)
- an unguessable punchline (if you saw the twist coming, it loses)
- the audience doing the final step (nothing explained after the punch)
- hyper-specific details over categories
- a clear target assumption that gets shattered

Instantly penalize: explanation after the punch, hedging, "wacky" adjectives doing
the humor's work, punching down, generic references, recycled/well-known jokes.

Also score the WINNER: violation_strength 0-1 (0 = bland corporate safety),
benignness 0-1 (0 = punches wrong / off-brand offense), and guessable (true if the
punchline is predictable from the setup)."""


def pairwise_judge_user(a, b) -> str:
    def fmt(c, i):
        s = f"[{i}] ({c.persona}/{c.mechanism})\nHOOK: {c.hook}\nCAPTION: {c.caption}"
        if c.script:
            s += f"\nSCRIPT: {c.script}"
        return s
    return f"{fmt(a, 0)}\n\n{fmt(b, 1)}\n\nWhich is funnier? Return winner (0 or 1) and the winner's scores."


def guess_check_system() -> str:
    return ("You are given the SETUP of a joke (everything before the final line). "
            "Predict how it ends: write 3 different plausible final lines. Just predict "
            "the most likely endings — do not try to be funny.")

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
