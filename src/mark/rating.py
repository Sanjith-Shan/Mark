"""Content-rating calibration — how much edge a campaign is allowed.

The humor research is unambiguous: what actually trends on TikTok/X skews
darker and sharper than brand-safe copy, and a system locked to cupcake-safe
output can never ride those waves. But edge is a dial, not a switch — so every
campaign declares a rating, every platform enforces a cap, and the effective
rating is the stricter of the two.

  clean    — all-ages: no profanity, no dark themes beyond mild irony.
  standard — mainstream-network comedy: dark humor about systems and processes
             is fine; nothing sexual, no profanity beyond 'hell/damn' tier.
  edgy     — PG-13: gallows humor, biting sarcasm, mild profanity, existential
             dread played for laughs — WHEN the trend/audience calls for it.

Hard bans that survive EVERY rating (these are line-outs, not dials): slurs,
hate, harassment of real people, sexual explicitness, mocking vulnerable
groups, jokes sourced from tragedy. Punching down is never a rating question.
"""

from __future__ import annotations

from typing import Optional

ORDER = ["clean", "standard", "edgy"]

# Per-platform ceilings — a campaign's rating can never exceed these.
# LinkedIn is a professional feed (insider satire only); Bluesky's community
# blocklists are permanent; Reddit mods ban on vibes.
PLATFORM_CAPS = {
    "linkedin": "clean",
    "bluesky": "standard",
    "reddit": "standard",
    "pinterest": "clean",
}

DEFAULT_RATING = "standard"

GUIDANCE = {
    "clean": (
        "CONTENT RATING: CLEAN (all-ages). No profanity, no dark themes beyond "
        "mild irony, nothing that needs a disclaimer. Wit over bite."),
    "standard": (
        "CONTENT RATING: STANDARD (mainstream-network comedy). Dark humor about "
        "systems, processes and absurd institutions is welcome — coping humor "
        "IS the register of this audience. No profanity beyond 'hell/damn' "
        "tier, nothing sexual or graphic."),
    "edgy": (
        "CONTENT RATING: EDGY (PG-13). You may go darker and sharper when the "
        "material calls for it: gallows humor, existential dread played for "
        "laughs, biting sarcasm, mild profanity (damn/hell/ass tier — never "
        "stronger). If the trend everyone is riding is spiky, match its energy "
        "instead of sanding it down; a defanged version of an edgy trend reads "
        "as corporate cosplay and performs worse than not posting. HARD LINES "
        "that still apply: no slurs, no hate, no harassment of real people, "
        "nothing sexual, never mock the audience or vulnerable groups, never "
        "joke about a tragedy."),
}

# How the humor engine's benignness gate moves with rating: at 'edgy' a joke is
# allowed to feel riskier (lower benignness floor); at 'clean' the bar rises.
BENIGNNESS_SHIFT = {"clean": +0.2, "standard": 0.0, "edgy": -0.15}
BENIGNNESS_FLOOR = 0.2  # below this is off-brand at ANY rating


def campaign_rating(product: Optional[dict]) -> str:
    r = (product or {}).get("content_rating") or DEFAULT_RATING
    return r if r in ORDER else DEFAULT_RATING


def effective_rating(product: Optional[dict], platform: str) -> str:
    """The stricter of the campaign's rating and the platform's ceiling."""
    r = campaign_rating(product)
    cap = PLATFORM_CAPS.get(platform, "edgy")
    return ORDER[min(ORDER.index(r), ORDER.index(cap))]


def guidance_block(product: Optional[dict], platform: str) -> str:
    return "\n" + GUIDANCE[effective_rating(product, platform)]


def min_benignness(base: float, product: Optional[dict], platform: str) -> float:
    """Rating-aware benignness gate for the humor engine."""
    shifted = base + BENIGNNESS_SHIFT[effective_rating(product, platform)]
    return max(BENIGNNESS_FLOOR, min(shifted, 0.95))
