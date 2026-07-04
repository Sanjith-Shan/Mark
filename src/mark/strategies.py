"""Strategy framework — the pluggable catalog of named content strategies.

A Strategy is a repeatable, named playbook ("absurdist-ai-slop", "pain-point-pov",
"build-in-public", ...) that shapes every stage of generation:

  * eligibility  — which platforms it fits, and how it adapts per platform
  * strategist   — a brief steering topic/angle selection
  * writer       — a brief steering voice, structure, and joke mechanics
  * media        — a brief steering image/video prompt style
  * humor_level  — none | light | full (drives the humor engine in humor.py)
  * character    — whether the product's AI ambassador fronts the content
  * series       — optional episodic format (episode number derived from history)

Selection is learned: "strategy" is a bandit arm type, so Thompson sampling
gradually concentrates on the strategies that actually earn engagement on each
platform, while still exploring. Products can restrict the pool via a
`strategies` allowlist (products table / product YAML).

The catalog content is distilled from docs/research/MASTER-STRATEGY.md — edit
there first, then encode here.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from . import db as db_module
from .app import App


class Strategy(BaseModel):
    id: str
    name: str
    description: str                    # what it is + why it works (mechanism)
    emotional_target: str               # "laughter", "recognition", "aspiration", ...
    platforms: dict[str, str]           # platform -> adaptation note ("" = native fit)
    content_types: list[str]            # preferred types, best first
    humor_level: str = "none"           # "none" | "light" | "full"
    uses_character: bool = False        # front the product's AI ambassador
    series_format: Optional[str] = None  # episodic recipe; episode # auto-derived
    strategist_brief: str = ""          # injected into the strategist prompt
    writer_brief: str = ""              # injected into the writer prompt
    media_brief: str = ""               # steers image/video prompt writing
    example_sketches: list[str] = Field(default_factory=list)  # few-shot flavor

    def fits(self, platform: str) -> bool:
        return platform in self.platforms

    def platform_note(self, platform: str) -> str:
        return (self.platforms.get(platform) or "").strip()


# --------------------------------------------------------------------------- #
# Catalog (starter entries — expanded from docs/research/MASTER-STRATEGY.md)
# --------------------------------------------------------------------------- #
STRATEGIES: list[Strategy] = [
    Strategy(
        id="pain-point-pov",
        name="Pain-point POV",
        description=(
            "Dramatize one hyper-specific moment of the audience's pain so precisely "
            "they feel seen. Recognition ('this is literally me') drives shares; the "
            "product appears as the quiet punchline, never the hero of the skit."
        ),
        emotional_target="recognition",
        platforms={
            "tiktok": "POV format, first-person, raw not polished",
            "instagram": "Reel or relatable meme image",
            "x": "one-liner observation, no hashtags needed",
            "threads": "conversational gripe that invites replies",
            "youtube": "loopable sub-35s skit",
        },
        content_types=["video", "image", "text"],
        humor_level="light",
        strategist_brief=(
            "Pick ONE ultra-specific pain moment (not a category — a moment: 'writing "
            "the same cover letter for the 40th time at 2am'). The narrower the moment, "
            "the stronger the recognition."
        ),
        writer_brief=(
            "Write in first person, present tense. Zero marketing language. The product "
            "may appear only in the last beat, as relief, or only in the caption."
        ),
        media_brief="Everyday realistic scene, phone-shot energy, expressive face or hands.",
    ),
    Strategy(
        id="educational-hooks",
        name="Educational hooks",
        description=(
            "Genuinely useful, save-worthy tips packaged behind a curiosity hook. "
            "Saves and sends are the strongest ranking signals on IG/LinkedIn; being "
            "actually useful is the whole trick."
        ),
        emotional_target="usefulness",
        platforms={
            "instagram": "carousel, one clear point per slide",
            "linkedin": "listicle post or document carousel",
            "x": "thread, first tweet is the promise",
            "tiktok": "fast-cut tip video with text overlays",
            "youtube": "sub-60s tip video",
        },
        content_types=["carousel", "thread", "text", "video"],
        humor_level="none",
        strategist_brief=(
            "Pick ONE concrete, immediately actionable tactic the audience doesn't know. "
            "It must be specific enough to screenshot ('the 3-line cold-email opener'), "
            "never generic advice ('network more')."
        ),
        writer_brief=(
            "Promise the payoff in the hook, deliver fast, no filler. Every slide/line "
            "must stand alone when screenshotted."
        ),
        media_brief="Clean, high-contrast text-forward slides; bold numerals; no stock-photo energy.",
    ),
    Strategy(
        id="social-proof",
        name="Social proof / results",
        description=(
            "Concrete results, numbers, and receipts. Specific numbers are inherently "
            "credible and curiosity-driving; screenshots read as evidence, not ads."
        ),
        emotional_target="trust",
        platforms={
            "x": "screenshot + dry one-liner",
            "linkedin": "short story arc ending in the number",
            "instagram": "before/after visual",
            "threads": "casual milestone brag",
        },
        content_types=["image", "text"],
        humor_level="none",
        strategist_brief="Anchor on ONE real, specific number or outcome. No round fake-sounding numbers.",
        writer_brief="Understate. Let the number do the work. Dry delivery beats excitement.",
        media_brief="Screenshot aesthetic or minimal stat card; authentic UI beats designed graphics.",
    ),
]

_BY_ID = {s.id: s for s in STRATEGIES}


def get(strategy_id: str) -> Optional[Strategy]:
    return _BY_ID.get(strategy_id)


def register(strategies: list[Strategy]) -> None:
    """Replace/extend catalog entries (used by tests and future config loading)."""
    for s in strategies:
        if s.id in _BY_ID:
            STRATEGIES[STRATEGIES.index(_BY_ID[s.id])] = s
        else:
            STRATEGIES.append(s)
        _BY_ID[s.id] = s


# --------------------------------------------------------------------------- #
# Eligibility + selection
# --------------------------------------------------------------------------- #
def product_allowlist(product: dict) -> Optional[list[str]]:
    """The product's optional strategy allowlist (JSON column / YAML key)."""
    allowed = db_module.loads(product.get("strategies"), None)
    return allowed if allowed else None


def eligible(app: App, product: dict, platform: str) -> list[Strategy]:
    """Strategies that fit this platform, the platform's allowed content types,
    and the product's allowlist."""
    allowed_types = set(app.settings.platform(platform).content_types or ["text"])
    allowlist = product_allowlist(product)
    out = []
    for s in STRATEGIES:
        if not s.fits(platform):
            continue
        if allowlist and s.id not in allowlist:
            continue
        if not any(t in allowed_types for t in s.content_types):
            continue
        out.append(s)
    return out


def pick(app: App, product: dict, platform: str,
         bandit_choice: Optional[str] = None) -> Optional[Strategy]:
    """Resolve the strategy for this generation.

    The bandit's sampled choice wins when it's still eligible; otherwise rotate
    deterministically through the eligible pool (offline-friendly, and gives every
    strategy pulls early on so Thompson sampling has signal to work with).
    """
    pool = eligible(app, product, platform)
    if not pool:
        return None
    if bandit_choice:
        for s in pool:
            if s.id == bandit_choice:
                return s
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? AND platform = ?",
        (product["id"], platform),
    )
    n = row["n"] if row else 0
    return pool[n % len(pool)]


def episode_number(app: App, product: dict, platform: str, strategy: Strategy) -> int:
    """1-based episode number for episodic strategies — how many pieces of content
    this product has already generated under this strategy, plus one."""
    if not strategy.series_format:
        return 1
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? "
        "AND strategy_context LIKE ?",
        (product["id"], f'%"strategy": "{strategy.id}"%'),
    )
    return (row["n"] if row else 0) + 1


def candidate_ids(app: App, platform: str) -> list[str]:
    """All strategy ids that could apply on this platform (bandit arm values).
    Product allowlists are enforced at pick() time, not here — arms are shared
    per (platform, product) and unused arms are harmless."""
    allowed_types = set(app.settings.platform(platform).content_types or ["text"])
    return [s.id for s in STRATEGIES
            if s.fits(platform) and any(t in allowed_types for t in s.content_types)]
