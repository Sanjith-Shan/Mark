"""Trend aggregator — merge sources, score relevance to the product, rank, store.

`refresh()` pulls from all sources, scores each trend's relevance to the active
product (LLM, or a keyword-overlap heuristic offline), combines that with the raw
popularity score, and writes ranked rows into the `trends` table.

`recent_trends()` is the read side used by the strategist via the pipeline.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from .. import db as db_module
from ..app import App
from ..llm import LLM
from . import bluesky, google_trends, imgflip, reddit, tiktok


class _ScoredTrend(BaseModel):
    topic: str
    relevance: float = 0.0  # 0..1
    style_notes: str = ""   # how creators are executing this trend (format, style, audio)
    safe: bool = True       # False if origin is tragedy/community-in-joke/NSFW/unclear
    sound_dependent: bool = False  # True if the joke IS a specific audio (API can't attach it)


class _TrendBatch(BaseModel):
    items: list[_ScoredTrend] = []


def refresh(app: App, llm: LLM, product: dict, limit_per_source: int = 15) -> list[dict]:
    """Full refresh — all sources (the slow/expensive ones included)."""
    raw = (tiktok.fetch_trending(app, limit=limit_per_source)
           + google_trends.fetch(app, limit=limit_per_source)
           + reddit.fetch(app, subreddits=_subreddits(app, product), limit=limit_per_source)
           + reddit.fetch_search(app, keywords=_keywords(product), limit=limit_per_source)
           + bluesky.fetch(app, limit=limit_per_source)
           + imgflip.fetch(app, limit=min(limit_per_source, 10)))
    return _score_and_store(app, llm, product, raw)


def refresh_fast(app: App, llm: LLM, product: dict, limit_per_source: int = 10) -> list[dict]:
    """Fast poll — only the free, hours-fresh sources (Reddit rising, Bluesky,
    Google RSS). Runs every ~30 min; Creative Center data lags ~a day so there's
    no point hammering it at this cadence."""
    raw = (reddit.fetch(app, subreddits=_subreddits(app, product), limit=limit_per_source)
           + reddit.fetch_search(app, keywords=_keywords(product), limit=limit_per_source)
           + bluesky.fetch(app, limit=limit_per_source)
           + google_trends.fetch(app, limit=limit_per_source))
    return _score_and_store(app, llm, product, raw)


def _trend_sources(product: Optional[dict]) -> dict:
    """Per-campaign radar config: {"subreddits": [...], "keywords": [...]}.
    Every campaign gets its own watchlist — an entertainment account watching
    r/AItooruined shares nothing with a job tool watching r/recruitinghell."""
    if not product:
        return {}
    return db_module.loads(product.get("trend_sources"), {}) or {}


def _subreddits(app: App, product: Optional[dict] = None) -> list[str]:
    per_campaign = _trend_sources(product).get("subreddits")
    if per_campaign:
        return list(per_campaign)
    subs = getattr(app.settings.trends, "subreddits", None)
    return list(subs) if subs else reddit.DEFAULT_SUBREDDITS


def _keywords(product: Optional[dict]) -> list[str]:
    return list(_trend_sources(product).get("keywords") or [])


def _score_and_store(app: App, llm: LLM, product: dict, raw: list[dict]) -> list[dict]:

    # Dedupe by lowercased topic, keep the higher raw score.
    merged: dict[str, dict] = {}
    for t in raw:
        key = t["topic"].strip().lower()
        if not key:
            continue
        if key not in merged or t["raw_score"] > merged[key]["raw_score"]:
            merged[key] = t
    items = list(merged.values())
    if not items:
        return []

    scored = _score_relevance(app, llm, product, [t["topic"] for t in items])

    stored = []
    for t in items:
        key = t["topic"].strip().lower()
        rel = scored.get(key, _ScoredTrend(topic=t["topic"], relevance=0.2))
        norm_raw = min(t["raw_score"] / 100.0, 1.0)
        # Relevance dominates; popularity boosts. Irrelevant trends stay low.
        final = round(rel.relevance * (0.4 + 0.6 * norm_raw), 4)
        velocity = _velocity(app, t["topic"], norm_raw)
        stage = _stage(velocity, norm_raw)
        meta = dict(t.get("metadata") or {})
        meta.update({"relevance": round(rel.relevance, 3), "raw_score": t["raw_score"],
                     "safe": rel.safe, "sound_dependent": rel.sound_dependent})
        db_module.insert(app.conn, "trends", source=t["source"], topic=t["topic"],
                         trend_score=final, metadata=meta, product_id=product["id"],
                         style_notes=rel.style_notes or None, velocity=velocity,
                         stage=stage)
        stored.append({"source": t["source"], "topic": t["topic"],
                       "trend_score": final, "metadata": meta,
                       "style_notes": rel.style_notes, "velocity": velocity,
                       "stage": stage})
    stored.sort(key=lambda x: x["trend_score"], reverse=True)
    return stored


# Velocity is measured on the RAW popularity signal over a multi-hour horizon.
# (The old version diffed the relevance-weighted composite against the previous
# 30-minute sighting: steady-hot trends read as flat after ONE poll and were
# vetoed as 'mature', and relevance-scoring noise flipped stages randomly.)
_VELOCITY_MIN_AGE_HOURS = 2     # ignore sightings younger than this (no resolution)
_VELOCITY_MAX_AGE_HOURS = 48    # ignore sightings older than this (different era)
_STAGE_EPS = 0.03               # |velocity| below this = flat


def _velocity(app: App, topic: str, norm_raw_now: float):
    """Delta of normalized raw popularity vs the average of sightings 2-48h ago.
    None = no history old enough to measure against — treated as a fresh trend
    (brand-new trends are the most jump-worthy of all)."""
    rows = db_module.query(
        app.conn,
        "SELECT metadata FROM trends WHERE lower(topic) = lower(?) "
        "AND collected_at >= datetime('now', ?) AND collected_at <= datetime('now', ?)",
        (topic.strip(), f"-{_VELOCITY_MAX_AGE_HOURS} hours",
         f"-{_VELOCITY_MIN_AGE_HOURS} hours"),
    )
    prior = []
    for r in rows:
        meta = db_module.loads(r["metadata"], {}) or {}
        raw = meta.get("raw_score")
        if isinstance(raw, (int, float)):
            prior.append(min(float(raw) / 100.0, 1.0))
    if not prior:
        return None
    return round(norm_raw_now - sum(prior) / len(prior), 4)


def _stage(velocity, norm_raw: float) -> str:
    """Trend lifecycle stage. Rules from docs/research/trend-adaptation.md:
    first-seen-already-big with no measurable history = mature (we missed the
    rise); otherwise rising/flat/falling from our own longitudinal history."""
    if velocity is None:
        return "mature" if norm_raw >= 0.7 else "new"
    if velocity > _STAGE_EPS:
        return "rising"
    if velocity < -_STAGE_EPS:
        return "declining"
    return "mature"


# --------------------------------------------------------------------------- #
# Fast path: hot-trend detection → immediate content generation
# --------------------------------------------------------------------------- #
def hot_trends(app: App, limit: int = 5, max_age_hours: int = 6,
               for_auto_react: bool = True,
               product_id: Optional[str] = None) -> list[dict]:
    """Trends worth reacting to RIGHT NOW: fresh, relevant, safe, new-or-rising.

    Jump/skip logic (docs/research/trend-adaptation.md): declining stage is a
    hard veto regardless of score — arriving late to a dying meme reads as brand
    cringe, the worst outcome. Unsafe origin is a hard veto. Sound-dependent
    trends are excluded from AUTO reaction (the posting API can't attach native
    audio) but still surface for manual action. Vetoes are evaluated on each
    topic's LATEST sighting — a crashing trend must not slip through via an
    older, higher-scored row.
    """
    cfg = app.settings.trends
    scope = "AND (product_id = ? OR product_id IS NULL) " if product_id else ""
    params: list = [f"-{int(max_age_hours)} hours"]
    if product_id:
        params.append(product_id)
    rows = db_module.query(
        app.conn,
        "SELECT source, topic, trend_score, metadata, style_notes, velocity, stage, "
        "collected_at FROM trends "
        f"WHERE collected_at >= datetime('now', ?) {scope}"
        "ORDER BY collected_at DESC",
        params,
    )
    latest: dict[str, dict] = {}
    for r in rows:  # newest first — first row per topic IS the latest sighting
        d = dict(r)
        latest.setdefault(d["topic"].strip().lower(), d)
    out = []
    for d in sorted(latest.values(), key=lambda x: x["trend_score"] or 0.0, reverse=True):
        if (d["trend_score"] or 0.0) < float(cfg.react_threshold):
            continue
        if (d.get("stage") or "new") in ("declining", "mature"):
            continue  # hard veto: we missed the window
        vel = d.get("velocity")
        if vel is not None and vel < cfg.min_velocity:
            continue
        d["metadata"] = db_module.loads(d.get("metadata"), {})
        if d["metadata"].get("safe") is False:
            continue  # hard veto: unclear/ugly origin
        if d["metadata"].get("fallback"):
            continue  # canned offline topics must never trigger reactions
        if for_auto_react and d["metadata"].get("sound_dependent"):
            continue  # can't attach native audio via API — manual only
        out.append(d)
        if len(out) >= limit:
            break
    return out


def _reactions_today(app: App, product_id: str) -> int:
    # Only SUCCESSFUL reactions consume budget — expiries and failures logging
    # under related kinds must never starve the day's real reactions.
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM activity WHERE kind = 'trend_react' "
        "AND level = 'success' AND product_id = ? AND date(created_at) = date('now')",
        (product_id,),
    )
    return row["n"] if row else 0


def _already_reacted(app: App, product_id: str, topic: str,
                     within_hours: int = 48) -> bool:
    """True if content was already generated for this trend topic recently —
    the same topic re-surfaces on every fast poll and must not spawn
    duplicates. Candidates narrowed by LIKE, confirmed by JSON decode."""
    rows = db_module.query(
        app.conn,
        "SELECT strategy_context FROM content WHERE product_id = ? "
        "AND created_at >= datetime('now', ?) AND strategy_context LIKE '%forced_trend%'",
        (product_id, f"-{int(within_hours)} hours"))
    want = topic.strip().lower()
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        if (sctx.get("forced_trend") or "").strip().lower() == want:
            return True
    return False


def react(app: App, llm: LLM, product: dict, trend: Optional[dict] = None,
          platforms: Optional[list[str]] = None) -> list[dict]:
    """The fast path: generate content tied to a hot trend immediately, without
    waiting for the daily generation cron. Returns the drafted content rows.

    Called automatically from the trends job when `trends.auto_react` is on, and
    manually from the CLI/web ("act on this trend")."""
    from .. import pipeline

    cfg = app.settings.trends
    if trend is None:
        # Hottest qualifying trend we haven't already reacted to (the same
        # topic re-surfaces every poll while it stays hot).
        trend = next((t for t in hot_trends(app, product_id=product["id"])
                      if not _already_reacted(app, product["id"], t["topic"])), None)
        if trend is None:
            return []
    elif _already_reacted(app, product["id"], trend["topic"]):
        return []

    if platforms is None:
        enabled = [p for p in pipeline.product_platforms(product)
                   if app.settings.platform(p).enabled]
        platforms = [p for p in (cfg.react_platforms or enabled) if p in enabled]
    if not platforms:
        return []

    budget = max(0, int(cfg.max_reactions_per_day) - _reactions_today(app, product["id"]))
    if budget == 0:
        return []

    # Trend content expires: a draft not approved inside the window must never
    # post late (stale meme = brand cringe). New trends get 24h, rising 72h.
    ttl_hours = 24 if (trend.get("stage") or "new") == "new" else 72

    drafted = []
    for platform in platforms[:budget]:
        try:
            row = pipeline.generate_one(app, llm, product, platform, forced_trend=trend)
            db_module.execute(
                app.conn,
                "UPDATE content SET expires_at = datetime('now', ?) WHERE id = ?",
                (f"+{ttl_hours} hours", row["id"]))
            drafted.append(row)
            db_module.log_activity(
                app.conn, "trend_react",
                f"Reacted to trend “{trend['topic']}” on {platform}",
                product_id=product["id"], content_id=row["id"], level="success")
        except Exception:
            db_module.log_activity(
                app.conn, "trend_react",
                f"Failed reacting to trend “{trend['topic']}” on {platform}",
                product_id=product["id"], level="error")
    return drafted


def expire_stale_content(app: App) -> int:
    """Auto-reject unposted trend content past its expiry — never post a dead
    meme. Returns the number of rows expired."""
    rows = db_module.query(
        app.conn,
        "SELECT id, product_id FROM content WHERE expires_at IS NOT NULL "
        "AND expires_at <= datetime('now') AND status IN ('draft', 'approved')")
    for r in rows:
        db_module.execute(
            app.conn,
            "UPDATE content SET status = 'rejected', "
            "rejection_feedback = 'auto-expired: trend window closed' WHERE id = ?",
            (r["id"],))
        db_module.log_activity(app.conn, "trend_expire",
                               f"Expired stale trend content #{r['id']} (window closed)",
                               product_id=r["product_id"], content_id=r["id"])
    return len(rows)


def _score_relevance(app: App, llm: LLM, product: dict,
                     topics: list[str]) -> dict[str, _ScoredTrend]:
    def _offline() -> _TrendBatch:
        return _TrendBatch(items=[
            _ScoredTrend(topic=t, relevance=_heuristic_relevance(t, product)) for t in topics])

    if llm.mock:
        batch = _offline()
    else:
        system = (f"You are a trend analyst for {product['name']}.\n"
                  f"PRODUCT: {product['description']}\nAUDIENCE: {product['target_audience']}\n"
                  "For each trending topic:\n"
                  "1. relevance 0..1 — can we tie into this authentically while PRESERVING "
                  "the joke's structure? (1 = perfect fit, 0 = irrelevant or the product "
                  "angle would ruin it)\n"
                  "2. style_notes — one sentence on HOW creators are executing this trend "
                  "right now: the format (POV/skit/greenscreen/listicle/duet), pacing, "
                  "text-overlay style, audio type. This guides our content generation.\n"
                  "3. safe — false if the trend originates from tragedy, a marginalized "
                  "community's in-joke, a feud, NSFW context, or you're unsure of its origin. "
                  "When in doubt, false — a misread meme damages the brand.\n"
                  "4. sound_dependent — true if the joke IS a specific audio/song (our posting "
                  "API cannot attach native sounds; text/format-driven trends we can ride fully).")
        user = "Analyze these topics:\n" + "\n".join(f"- {t}" for t in topics)
        batch = llm.parse(
            system, user, _TrendBatch, model=app.settings.llm.judge_model, temperature=0.2,
            product_id=product["id"], mock_factory=_offline,
        )
    out = {}
    for s in batch.items:
        s.relevance = max(0.0, min(s.relevance, 1.0))
        out[s.topic.strip().lower()] = s
    return out


def _heuristic_relevance(topic: str, product: dict) -> float:
    text = f"{product['description']} {product['target_audience']} {product['name']}".lower()
    words = [w for w in re.findall(r"[a-z]+", topic.lower()) if len(w) > 3]
    if not words:
        return 0.2
    hits = sum(1 for w in words if w in text)
    return round(min(1.0, 0.2 + 0.3 * hits), 3)


# --------------------------------------------------------------------------- #
# Read side
# --------------------------------------------------------------------------- #
def recent_trends(app: App, platform: Optional[str] = None, limit: int = 10,
                  max_age_hours: int = 48,
                  product_id: Optional[str] = None) -> list[dict]:
    """Read side for the strategist. Campaign-scoped (a trend's relevance score
    was computed for ONE campaign), latest sighting per topic (so the stage the
    strategist sees is current), unsafe origins filtered out."""
    scope = "AND (product_id = ? OR product_id IS NULL) " if product_id else ""
    params: list = [f"-{int(max_age_hours)} hours"]
    if product_id:
        params.append(product_id)
    rows = db_module.query(
        app.conn,
        "SELECT source, topic, trend_score, metadata, style_notes, velocity, stage, "
        f"collected_at FROM trends WHERE collected_at >= datetime('now', ?) {scope}"
        "ORDER BY collected_at DESC",
        params,
    )
    # Latest sighting per topic; lightly boost platform-native sources.
    latest: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        latest.setdefault(d["topic"].strip().lower(), d)
    ranked = []
    for d in latest.values():
        d["metadata"] = db_module.loads(d.get("metadata"), {})
        if d["metadata"].get("safe") is False:
            continue  # tragedy/in-joke/unclear origin never reaches the strategist
        score = d["trend_score"] or 0.0
        if platform == "tiktok" and d["source"] == "tiktok":
            score += 0.05
        d["_score"] = score
        ranked.append(d)
    out = sorted(ranked, key=lambda x: x["_score"], reverse=True)[:limit]
    for d in out:
        d.pop("_score", None)
    return out
