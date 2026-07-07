"""Paid clipping-campaign discovery — find the money, rank it, track it.

Paid "clipping" marketplaces (ContentRewards, Whop Content Rewards, Vyro, …) are
two-sided: brands/streamers deposit a budget and pay "clippers" a CPM (~$0.50–$5
per 1,000 verified views) for posting short vertical clips to the clipper's OWN
accounts. This module DISCOVERS those campaigns, scores them by expected value,
extracts hard requirements + a brand-safety verdict, and surfaces a ranked daily
digest.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  DISCOVERY + TRACKING ONLY.                                            │
    │  This module NEVER auto-joins, auto-posts, or auto-submits.            │
    │  Joining a campaign, downloading its content bank, posting a clip, and │
    │  clicking "Submit Video" are ALWAYS human actions performed in the web │
    │  UI. Every clipping platform's ToS bans "automating posting or         │
    │  engagement" — the penalty is a permanent, no-appeal ban, forfeiture   │
    │  of all pending earnings, and blacklisting of every linked social      │
    │  account. So there is deliberately NO produce()/submit path here.      │
    └──────────────────────────────────────────────────────────────────────┘

Why it's still safe to automate: campaign DISCOVERY is not posting. ContentRewards
serves its /discover page fully server-rendered (Next.js flight data) and
robots.txt explicitly ALLOWS /discover, so polling it is permitted. We only read.

Design mirrors ``humor_radar`` / the trend radar: defensive fetchers with offline
mocks → an LLM judge (brand-safety + requirement extraction) → a re-sighting
upsert that tracks budget burn → a ranked read side (``digest``).

INTEGRATION (orchestrator wires these — this module must not edit central files):
  * Scheduler: ``refresh(app, llm)`` is exposed and auto-registers into the
    templates ``DISCOVERY`` map (templates/__init__ maps refresh() by attribute
    presence), so it runs on the fast-trends pulse alongside the humor radar —
    same cadence hook as ``scheduler/engine.py:job_trends_fast``. Keep it at
    ≥1h intervals; the /discover page is heavy (~7MB).
  * Web: add a ``GET /api/campaigns`` route returning ``digest(app)`` for a future
    "Campaign digest" page, plus ``POST /api/campaigns/{id}/joined`` to let a
    human mark a campaign joined (sets clip_campaigns.joined = 1). Submission /
    posting UI is intentionally out of scope for automation — a human does it.
  * Brand-safety sign-off: campaigns flagged ``blocked=1`` (gambling/casino/
    adult/etc.) are excluded from the default digest. Surfacing a blocked
    campaign to a human requires an explicit ``include_blocked=True`` and should
    carry a visible warning in the UI. Gambling/casino skews the biggest budgets
    (Roobet, Stake ecosystem) — do not let EV ranking tempt an override without
    human review of regional branded-content/gambling policy.
  * No producer: this template has no autonomous content, so it is NOT added to
    the PRODUCERS map — only ``refresh`` (discovery) and ``digest`` are exposed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

from .. import db as db_module
from ..app import App
from ..llm import LLM
from ..strategies import Strategy

log = logging.getLogger("mark.templates.campaigns")

# --------------------------------------------------------------------------- #
# Strategy registration — the lane appears in the catalog so it's discoverable,
# but it has NO producer (discovery-only). never_auto_approve is belt-and-braces:
# even if a producer were ever bolted on, nothing here may reach a live account
# without a human. requires_product=False: campaigns are found regardless of the
# active product; fit is scored, not gated.
# --------------------------------------------------------------------------- #
STRATEGY = Strategy(
    id="campaign-clips",
    name="Paid campaign clips (discovery)",
    description=(
        "Discover paid clipping/UGC campaigns on ContentRewards/Whop/etc., rank "
        "them by expected value (CPM × remaining budget × freshness × platform "
        "fit − competition), extract each brief's hard requirements, and flag "
        "brand-safety. DISCOVERY + TRACKING ONLY — joining, posting and "
        "submitting are always human actions (platform ToS bans automation)."
    ),
    emotional_target="satisfaction",
    platforms={
        "tiktok": "clipper's own account — never a brand account; originality-policy sensitive",
        "instagram": "Reels on a dedicated clipper account",
        "youtube": "Shorts on a dedicated clipper account",
        "x": "clipper's own account",
    },
    content_types=["video"],
    never_auto_approve=True,
    requires_product=False,
    mix_weight=0.0,  # never auto-sampled for content generation — discovery only
    strategist_brief=(
        "This is a discovery lane, not a content lane. It surfaces paid campaigns "
        "to a human; it never itself creates or posts clips."
    ),
)

PLATFORM = "contentrewards"
_DISCOVER_URL = "https://contentrewards.com/discover"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# CPM outliers: a "$1000.00 per view" entry is really a flat per-approved-video
# UGC rate typed into the CPM field. Keep the true value but cap the EV-effective
# CPM so one mislabelled flat-fee campaign can't dominate the ranking.
_CPM_OUTLIER = 100.0
_CPM_EV_CAP = 15.0

# Brand-safety keyword heuristic (mock / offline fallback for the LLM judge).
_BLOCK_KEYWORDS = (
    "casino", "roobet", "stake.com", "gambl", "betting", "sportsbook", "poker",
    "slots", "roulette", "blackjack", "wager", "18+", "21+", "onlyfans",
    "adult content", "nsfw", "sweepstake", "crypto casino",
)

# Requirement-extraction keyword heuristic (mock fallback).
_REQ_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("watermark_required", ("watermark",)),
    ("pinned_comment_required", ("pinned comment", "pin the comment", "pinned link")),
    ("content_bank_only", ("content bank", "pre-approved clip", "provided clips")),
    ("logo_embed_required", ("logo embed", "logo on", "embedded logo")),
    ("english_only", ("english only", "[english]", "english-speaking")),
    ("us_only", ("us only", "united states only", "us-based")),
    ("original_edit_required", ("original edit", "add commentary", "no auto-clipper",
                                "genuine editorial")),
]

# Target platforms for platform-fit scoring when settings are unavailable.
_DEFAULT_TARGET_PLATFORMS = {"tiktok", "instagram", "youtube", "x"}


# --------------------------------------------------------------------------- #
# ContentRewards flight-data parser (verified against the live /discover HTML).
#
# The page is a Next.js App Router SSR document: every campaign object lives in
# the `self.__next_f.push([1, "<json-escaped flight chunk>"])` calls. We decode
# each push payload (a JSON string → real text), then brace-balance every object
# that starts with the alphabetized `{"avatar":` marker and json.loads it.
#
# Built DEFENSIVELY: this structure breaks silently on any Next.js redeploy, so
# every step is wrapped and yields [] rather than raising. Verified: extracts
# ~438 unique campaigns from the saved 7.4MB sample.
# --------------------------------------------------------------------------- #
_OBJ_MARKER = '{"avatar":'


def _decode_flight_pushes(html: str) -> str:
    """Concatenate the decoded (unescaped) payloads of every __next_f push."""
    out: list[str] = []
    marker = "self.__next_f.push(["
    i = 0
    while True:
        s = html.find(marker, i)
        if s < 0:
            break
        # payload = the JSON string literal after the leading `<chunk_num>,`
        comma = html.find(",", s + len(marker))
        q = html.find('"', comma) if comma >= 0 else -1
        if q < 0:
            i = s + len(marker)
            continue
        # scan to the closing UNescaped quote
        j = q + 1
        n = len(html)
        while j < n:
            c = html[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                break
            j += 1
        try:
            out.append(json.loads(html[q:j + 1]))
        except Exception:
            pass
        i = j + 1
    return "\n".join(out)


def _balance_object(text: str, start: int) -> Optional[str]:
    """Return the brace-balanced object string starting at `start`, respecting
    JSON string context (so `{`/`}` inside descriptions don't miscount)."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def _parse_money(value) -> float:
    """'$$1,500.00' / '$1.50' / 1500 → float. The '$$' doubling is an escaping
    artifact of the flight data; strip all '$' and commas."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _normalize_cr(raw: dict) -> Optional[dict]:
    """Map a raw ContentRewards campaign object to our normalized shape."""
    cid = raw.get("id")
    if not cid:
        return None
    cpm = _parse_money(raw.get("pricePerView"))
    budget = _parse_money(raw.get("totalBudget"))
    spent = _parse_money(raw.get("budgetSpent"))
    progress = raw.get("progressPercentage")
    if progress is None and budget > 0:
        progress = 100.0 * spent / budget
    progress = float(progress or 0.0)
    route = raw.get("whopProductRoute")
    url = f"https://whop.com/{route}" if route else _DISCOVER_URL
    status = "open" if (raw.get("status") == "active") else (raw.get("status") or "open")
    return {
        "platform": PLATFORM,
        "external_id": str(cid),
        "title": (raw.get("title") or "").strip()[:300],
        "brand": (raw.get("brand") or "").strip()[:200],
        "description": (raw.get("description") or "").strip(),
        "category": (raw.get("category") or "Other").strip(),
        "campaign_type": raw.get("campaignType") or "clipping",
        "cpm": round(cpm, 4),
        "cpm_outlier": cpm > _CPM_OUTLIER,
        "budget": round(budget, 2),
        "budget_used": round(spent, 2),
        "progress": round(progress, 2),
        "creators": int(raw.get("creators") or 0),
        "platforms": list(raw.get("socialPlatforms") or []),
        "verified": bool(raw.get("isVerified")),
        "url": url,
        "status": status,
        "stats": raw.get("stats") or {},
        "whop_experience_id": raw.get("whopExperienceId") or raw.get("experienceId"),
    }


def _parse_discover(html: str) -> list[dict]:
    """Parse ContentRewards /discover HTML into normalized campaign dicts.
    Defensive: any failure returns []. Deduped on campaign id."""
    if not html or _OBJ_MARKER not in html and "avatar" not in html:
        return []
    try:
        flight = _decode_flight_pushes(html)
        if _OBJ_MARKER not in flight:
            # Flight decode found nothing usable — the layout likely changed.
            log.warning("contentrewards: no campaign objects in decoded flight data")
            return []
        seen: dict[str, dict] = {}
        idx = 0
        while True:
            s = flight.find(_OBJ_MARKER, idx)
            if s < 0:
                break
            idx = s + len(_OBJ_MARKER)
            obj = _balance_object(flight, s)
            if not obj:
                continue
            try:
                raw = json.loads(obj)
            except Exception:
                continue
            norm = _normalize_cr(raw)
            if norm:
                seen[norm["external_id"]] = norm
        return list(seen.values())
    except Exception as exc:  # never let a parser break the discovery pulse
        log.warning("contentrewards parse failed: %s", exc)
        return []


# --------------------------------------------------------------------------- #
# Deterministic offline samples (used in mock mode so tests + offline runs work
# without the network or the 7MB fixture). Mirrors the real schema, includes a
# gambling campaign (→ must be blocked) and a low-competition alpha.
# --------------------------------------------------------------------------- #
def _sample_campaigns() -> list[dict]:
    samples = [
        {
            "id": "sample-roobet-ugc", "title": "ROOBET UGC REPOSTING V2",
            "brand": "Creator Casino", "campaignType": "ugc", "category": "Entertainment",
            "description": ("Roobet casino product placement — creators integrating "
                            "Roobet into their videos, logo embedded. Post pre-approved "
                            "clips from the Content Bank, keep the watermark visible and "
                            "the pinned comment up."),
            "pricePerView": "$$1.50", "totalBudget": "$$250,000", "budgetSpent": "$$19,359.46",
            "progressPercentage": 8, "creators": 2482, "isVerified": False,
            "socialPlatforms": ["tiktok", "instagram"], "status": "active",
            "whopProductRoute": "creator-casino-7b", "whopExperienceId": "exp_ZOGZeyhNIa6vDv",
            "stats": {"viewCount": "10.2M"},
        },
        {
            "id": "sample-podcast-fresh", "title": "Earn Your Leisure Podcast [CLIPS]",
            "brand": "EYL Network", "campaignType": "clipping", "category": "Personal Brand",
            "description": ("Clip the latest episodes. English only. Keep the watermark "
                            "visible and add a pinned comment linking the full episode. "
                            "Original edits with real hooks — no auto-clipper output."),
            "pricePerView": "$$1.50", "totalBudget": "$$10,000", "budgetSpent": "$$300",
            "progressPercentage": 3, "creators": 41, "isVerified": True,
            "socialPlatforms": ["tiktok", "instagram", "youtube"], "status": "active",
            "whopProductRoute": "eyl-network", "whopExperienceId": "exp_eyl01",
            "stats": {"viewCount": "1.1M"},
        },
        {
            "id": "sample-app-ugc", "title": "Talking-Head UGC [English]",
            "brand": "ToneMatcher", "campaignType": "ugc", "category": "Product",
            "description": ("Original talking-head UGC to the brief. US only. Provided "
                            "guidelines, no content bank."),
            "pricePerView": "$$3.00", "totalBudget": "$$20,000", "budgetSpent": "$$2,667.25",
            "progressPercentage": 13, "creators": 241, "isVerified": True,
            "socialPlatforms": ["instagram", "x", "tiktok", "youtube"], "status": "active",
            "whopProductRoute": "tonematcher", "whopExperienceId": "exp_tone01",
            "stats": {"viewCount": "420K"},
        },
        {
            "id": "sample-music-mature", "title": "Leon Bridges Live Performances",
            "brand": "Columbia Records", "campaignType": "clipping", "category": "Music",
            "description": "Clip live performances. Keep the watermark visible.",
            "pricePerView": "$$1.00", "totalBudget": "$$5,000", "budgetSpent": "$$4,600",
            "progressPercentage": 92, "creators": 380, "isVerified": True,
            "socialPlatforms": ["tiktok", "instagram"], "status": "active",
            "whopProductRoute": "columbia-leon", "whopExperienceId": "exp_leon01",
            "stats": {"viewCount": "6.4M"},
        },
    ]
    out = []
    for s in samples:
        norm = _normalize_cr(s)
        if norm:
            out.append(norm)
    return out


def _load_fixture_html() -> Optional[str]:
    """Opt-in: parse a saved /discover HTML fixture offline when MARK_CR_FIXTURE
    points at one. Lets offline runs use real campaign data; tests stay on the
    deterministic samples unless the env var is set."""
    path = os.environ.get("MARK_CR_FIXTURE")
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except Exception as exc:
            log.warning("MARK_CR_FIXTURE unreadable: %s", exc)
    return None


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #
def fetch_contentrewards(app: App, *, html: Optional[str] = None) -> list[dict]:
    """Poll ContentRewards /discover and return normalized campaign dicts.

    * ``html`` given → parse it directly (used by the real-parser test).
    * mock / offline → parse MARK_CR_FIXTURE if set, else deterministic samples.
    * live → httpx GET with a browser UA; any failure returns [] (never raises).
    """
    if html is not None:
        return _parse_discover(html)
    if app.force_mock or app.is_mock("openai"):
        fixture = _load_fixture_html()
        return _parse_discover(fixture) if fixture else _sample_campaigns()
    try:
        import httpx

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(_DISCOVER_URL, headers={"User-Agent": _UA})
            resp.raise_for_status()
            campaigns = _parse_discover(resp.text)
        db_module.log_activity(
            app.conn, "campaigns",
            f"ContentRewards /discover: {len(campaigns)} campaigns parsed",
            level="info" if campaigns else "warning")
        return campaigns
    except Exception as exc:
        log.warning("contentrewards fetch failed: %s", exc)
        return []


def fetch_whop(app: App) -> list[dict]:
    """Whop Content Rewards fetcher (best-effort stub).

    whop.com/discover/content-rewards is CLIENT-rendered (data loads via
    authenticated client calls), so live discovery needs a headless browser or
    the Apify actor ``memo23/whop-leaderboards-scraper`` ($1.50/1k results) —
    neither is wired here. Individual whop campaign pages (whop.com/<route>) DO
    server-render, so the ContentRewards path already yields Whop campaign URLs
    via ``whopProductRoute``. This returns a deterministic sample in mock mode
    and [] live until a scraper is provisioned.
    """
    if app.force_mock or app.is_mock("openai"):
        norm = _normalize_cr({
            "id": "sample-whop-native", "title": "Kick Streamer Live [KICK CLIPS]",
            "brand": "Billy Brown Live", "campaignType": "clipping", "category": "Entertainment",
            "description": ("Clip the live streams. Keep the watermark visible, add a "
                            "pinned comment. English only."),
            "pricePerView": "$$1.25", "totalBudget": "$$8,000", "budgetSpent": "$$500",
            "progressPercentage": 6, "creators": 63, "isVerified": False,
            "socialPlatforms": ["tiktok", "youtube"], "status": "active",
            "whopProductRoute": "billy-brown-live", "whopExperienceId": "exp_billy01",
            "stats": {"viewCount": "2.0M"},
        })
        if norm:
            norm["platform"] = "whop"
            return [norm]
        return []
    # Live Whop discovery requires headless/Apify — not provisioned. See docstring.
    log.debug("fetch_whop: live Whop discovery needs a headless/Apify scraper; skipping")
    return []


# --------------------------------------------------------------------------- #
# Brand-safety + requirement extraction (LLM judge; mock = keyword heuristic)
# --------------------------------------------------------------------------- #
class _CampaignVerdict(BaseModel):
    external_id: str = ""
    blocked: bool = False          # True: gambling/casino/adult/etc. — never surface by default
    safety_category: str = "general"  # e.g. gambling, adult, crypto, general
    requirements: list[str] = Field(default_factory=list)  # hard rules from the brief


class _CampaignVerdicts(BaseModel):
    items: list[_CampaignVerdict] = Field(default_factory=list)


def _heuristic_verdict(c: dict) -> _CampaignVerdict:
    text = f"{c.get('title', '')} {c.get('brand', '')} {c.get('description', '')} " \
           f"{c.get('category', '')}".lower()
    blocked = any(k in text for k in _BLOCK_KEYWORDS)
    safety = "general"
    if blocked:
        safety = "adult" if ("adult" in text or "nsfw" in text or "onlyfans" in text) \
            else "gambling"
    reqs = [label for label, pats in _REQ_PATTERNS if any(p in text for p in pats)]
    return _CampaignVerdict(external_id=c["external_id"], blocked=blocked,
                            safety_category=safety, requirements=reqs)


def _judge(app: App, llm: LLM, campaigns: list[dict]) -> dict[str, _CampaignVerdict]:
    def _mock() -> _CampaignVerdicts:
        return _CampaignVerdicts(items=[_heuristic_verdict(c) for c in campaigns])

    if llm.mock or not campaigns:
        verdicts = _mock()
    else:
        listing = "\n".join(
            f'- id={c["external_id"]!r} [{c.get("category")}] brand={c.get("brand")!r} '
            f'"{c.get("title")}" :: {c.get("description", "")[:280]}'
            for c in campaigns[:40])
        system = (
            "You screen paid clipping/UGC campaigns for a discovery tool. For each "
            "campaign return: blocked (true if the campaign is gambling/casino/"
            "sportsbook/betting, adult/NSFW, or otherwise brand-unsafe to promote "
            "on TikTok/Instagram without age-gating — when unsure, true), "
            "safety_category (gambling|adult|crypto|alcohol|general), and "
            "requirements (the HARD rules a clipper must follow, extracted verbatim-"
            "ish from the brief: watermark, pinned comment, content-bank-only, "
            "logo embed, region/language limits, original-edit requirement, max "
            "accounts). Keep each requirement a short phrase.")
        verdicts = llm.parse(system, f"Screen these campaigns:\n{listing}",
                             _CampaignVerdicts,
                             model=app.settings.llm.judge_model, temperature=0.1,
                             mock_factory=_mock)
    return {v.external_id: v for v in verdicts.items}


# --------------------------------------------------------------------------- #
# Expected-value scoring
#   EV = CPM × remaining_budget × (1 − progress) × platform_match − competition
# scaled so the number is human-readable ("expected $ still winnable, weighted").
# --------------------------------------------------------------------------- #
def _target_platforms(app: App) -> set[str]:
    try:
        enabled = set(app.settings.enabled_platforms())
        return enabled or set(_DEFAULT_TARGET_PLATFORMS)
    except Exception:
        return set(_DEFAULT_TARGET_PLATFORMS)


def _ev_score(c: dict, targets: set[str]) -> float:
    remaining = max(0.0, c["budget"] - c["budget_used"])
    progress_frac = min(max(c["progress"] / 100.0, 0.0), 1.0)
    freshness = 1.0 - progress_frac
    plats = c.get("platforms") or []
    if plats and targets:
        platform_match = len([p for p in plats if p in targets]) / len(plats)
    else:
        platform_match = 1.0
    # Flat-fee outliers mislabelled as CPM shouldn't dominate — cap for EV.
    cpm_eff = min(c["cpm"], _CPM_EV_CAP) if c.get("cpm_outlier") else c["cpm"]
    # remaining in $1k units keeps EV on a readable scale.
    ev = cpm_eff * (remaining / 1000.0) * freshness * platform_match
    competition = c.get("creators", 0) / 250.0  # crowded campaigns are worth less
    return round(ev - competition, 3)


# --------------------------------------------------------------------------- #
# Refresh — the discovery pass (wired into the fast-trends pulse via DISCOVERY)
# --------------------------------------------------------------------------- #
def refresh(app: App, llm: LLM) -> None:
    """Fetch all sources, score EV, screen brand-safety + requirements, and
    upsert into clip_campaigns (re-sighting updates budget/last_seen, never
    duplicates and never clobbers the human `joined` flag). Discovery only —
    nothing here joins, posts, or submits."""
    campaigns = fetch_contentrewards(app) + fetch_whop(app)
    # Dedupe within the batch on (platform, external_id).
    merged: dict[tuple[str, str], dict] = {}
    for c in campaigns:
        merged[(c["platform"], c["external_id"])] = c
    campaigns = list(merged.values())
    if not campaigns:
        log.info("campaigns.refresh: no campaigns discovered")
        return

    verdicts = _judge(app, llm, campaigns)
    targets = _target_platforms(app)
    upserted = 0
    for c in campaigns:
        v = verdicts.get(c["external_id"]) or _heuristic_verdict(c)
        ev = _ev_score(c, targets)
        _upsert(app, c, v, ev)
        upserted += 1
    db_module.log_activity(
        app.conn, "campaigns",
        f"Discovered/updated {upserted} paid clip campaigns "
        f"({sum(1 for c in campaigns if (verdicts.get(c['external_id']) or _heuristic_verdict(c)).blocked)} blocked)",
        level="success")


def _upsert(app: App, c: dict, verdict: _CampaignVerdict, ev: float) -> None:
    """Insert a new campaign or update an existing sighting. Computes burn-delta
    (budget spent since we last saw it) and preserves the human `joined` flag."""
    existing = db_module.query_one(
        app.conn,
        "SELECT id, budget_used, joined, first_seen FROM clip_campaigns "
        "WHERE platform = ? AND external_id = ?",
        (c["platform"], c["external_id"]))
    burn_delta = 0.0
    if existing is not None and existing["budget_used"] is not None:
        burn_delta = round(c["budget_used"] - float(existing["budget_used"]), 2)
    metadata = {
        "campaign_type": c.get("campaign_type"),
        "verified": c.get("verified"),
        "progress": c.get("progress"),
        "safety_category": verdict.safety_category,
        "cpm_outlier": c.get("cpm_outlier", False),
        "stats": c.get("stats") or {},
        "whop_experience_id": c.get("whop_experience_id"),
        "burn_delta": burn_delta,
        "description": (c.get("description") or "")[:1000],
    }
    # ON CONFLICT keeps `joined` (human action) and `first_seen`; bumps last_seen.
    db_module.execute(
        app.conn,
        """
        INSERT INTO clip_campaigns
            (platform, external_id, title, brand, url, category, cpm, budget,
             budget_used, creators, platforms, requirements, ev_score, blocked,
             status, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, external_id) DO UPDATE SET
            title = excluded.title,
            brand = excluded.brand,
            url = excluded.url,
            category = excluded.category,
            cpm = excluded.cpm,
            budget = excluded.budget,
            budget_used = excluded.budget_used,
            creators = excluded.creators,
            platforms = excluded.platforms,
            requirements = excluded.requirements,
            ev_score = excluded.ev_score,
            blocked = excluded.blocked,
            status = excluded.status,
            metadata = excluded.metadata,
            last_seen = CURRENT_TIMESTAMP
        """,
        (c["platform"], c["external_id"], c["title"], c["brand"], c["url"],
         c["category"], c["cpm"], c["budget"], c["budget_used"], c["creators"],
         json.dumps(c.get("platforms") or []),
         json.dumps(list(verdict.requirements)),
         ev, 1 if verdict.blocked else 0, c["status"], json.dumps(metadata)))


# --------------------------------------------------------------------------- #
# Digest — the ranked read side (for a future web page / notification)
# --------------------------------------------------------------------------- #
def digest(app: App, *, limit: int = 15, include_blocked: bool = False) -> list[dict]:
    """Ranked daily digest: top campaigns by EV plus burn-rate deltas on joined
    ones. Brand-safety-blocked campaigns are excluded unless include_blocked."""
    where = "WHERE status != 'ended'"
    if not include_blocked:
        where += " AND blocked = 0"
    rows = db_module.query(
        app.conn,
        f"SELECT * FROM clip_campaigns {where} "
        "ORDER BY joined DESC, ev_score DESC LIMIT ?",
        (int(limit),))
    out = []
    for r in rows:
        d = dict(r)
        meta = db_module.loads(d.get("metadata"), {}) or {}
        remaining = round(max(0.0, (d.get("budget") or 0.0) - (d.get("budget_used") or 0.0)), 2)
        out.append({
            "id": d["id"],
            "platform": d["platform"],
            "external_id": d["external_id"],
            "title": d.get("title"),
            "brand": d.get("brand"),
            "category": d.get("category"),
            "cpm": d.get("cpm"),
            "budget": d.get("budget"),
            "budget_used": d.get("budget_used"),
            "remaining_budget": remaining,
            "progress": meta.get("progress"),
            "creators": d.get("creators"),
            "platforms": db_module.loads(d.get("platforms"), []) or [],
            "requirements": db_module.loads(d.get("requirements"), []) or [],
            "ev_score": d.get("ev_score"),
            "blocked": bool(d.get("blocked")),
            "safety_category": meta.get("safety_category"),
            "joined": bool(d.get("joined")),
            "verified": meta.get("verified"),
            "cpm_outlier": meta.get("cpm_outlier", False),
            "burn_delta": meta.get("burn_delta", 0.0),
            "url": d.get("url"),
            "first_seen": d.get("first_seen"),
            "last_seen": d.get("last_seen"),
            # Human-action reminder carried on every digest item — the UI must
            # never offer an automated join/post/submit for these.
            "action": "human_only: join, post and submit are manual web actions",
        })
    return out
