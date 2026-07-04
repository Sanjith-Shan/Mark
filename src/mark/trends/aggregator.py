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
from . import google_trends, tiktok


class _ScoredTrend(BaseModel):
    topic: str
    relevance: float = 0.0  # 0..1
    style_notes: str = ""   # how creators are executing this trend (format, style, audio)


class _TrendBatch(BaseModel):
    items: list[_ScoredTrend] = []


def refresh(app: App, llm: LLM, product: dict, limit_per_source: int = 15) -> list[dict]:
    raw = tiktok.fetch_trending(app, limit=limit_per_source) + google_trends.fetch(app, limit=limit_per_source)

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
        velocity = _velocity(app, t["topic"], final)
        meta = dict(t.get("metadata") or {})
        meta.update({"relevance": round(rel.relevance, 3), "raw_score": t["raw_score"]})
        db_module.insert(app.conn, "trends", source=t["source"], topic=t["topic"],
                         trend_score=final, metadata=meta,
                         style_notes=rel.style_notes or None, velocity=velocity)
        stored.append({"source": t["source"], "topic": t["topic"],
                       "trend_score": final, "metadata": meta,
                       "style_notes": rel.style_notes, "velocity": velocity})
    stored.sort(key=lambda x: x["trend_score"], reverse=True)
    return stored


def _velocity(app: App, topic: str, score_now: float):
    """Score delta vs the most recent prior sighting of this topic (last 7 days).
    None = first sighting — brand-new trends are the most jump-worthy of all."""
    row = db_module.query_one(
        app.conn,
        "SELECT trend_score FROM trends WHERE lower(topic) = lower(?) "
        "AND collected_at >= datetime('now', '-7 days') "
        "ORDER BY collected_at DESC LIMIT 1",
        (topic.strip(),),
    )
    if row is None or row["trend_score"] is None:
        return None
    return round(score_now - float(row["trend_score"]), 4)


# --------------------------------------------------------------------------- #
# Fast path: hot-trend detection → immediate content generation
# --------------------------------------------------------------------------- #
def hot_trends(app: App, limit: int = 5, max_age_hours: int = 6) -> list[dict]:
    """Trends worth reacting to RIGHT NOW: fresh, relevant, and new-or-rising.

    Jump/skip logic: a trend qualifies if its score clears the config threshold
    AND it is either brand new (velocity IS NULL) or still rising (velocity >=
    min_velocity). A falling trend is a skip — arriving late to a dying meme
    reads as brand cringe, the worst outcome.
    """
    cfg = app.settings.trends
    rows = db_module.query(
        app.conn,
        "SELECT source, topic, trend_score, metadata, style_notes, velocity, collected_at "
        "FROM trends WHERE collected_at >= datetime('now', ?) AND trend_score >= ? "
        "ORDER BY trend_score DESC",
        (f"-{int(max_age_hours)} hours", float(cfg.react_threshold)),
    )
    out, seen = [], set()
    for r in rows:
        d = dict(r)
        key = d["topic"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        vel = d.get("velocity")
        if vel is not None and vel < cfg.min_velocity:
            continue  # falling trend — skip
        d["metadata"] = db_module.loads(d.get("metadata"), {})
        out.append(d)
        if len(out) >= limit:
            break
    return out


def _reactions_today(app: App, product_id: str) -> int:
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM activity WHERE kind = 'trend_react' "
        "AND product_id = ? AND date(created_at) = date('now')",
        (product_id,),
    )
    return row["n"] if row else 0


def react(app: App, llm: LLM, product: dict, trend: Optional[dict] = None,
          platforms: Optional[list[str]] = None) -> list[dict]:
    """The fast path: generate content tied to a hot trend immediately, without
    waiting for the daily generation cron. Returns the drafted content rows.

    Called automatically from the trends job when `trends.auto_react` is on, and
    manually from the CLI/web ("act on this trend")."""
    from .. import pipeline

    cfg = app.settings.trends
    if trend is None:
        hot = hot_trends(app)
        if not hot:
            return []
        trend = hot[0]

    if platforms is None:
        enabled = [p for p in pipeline.product_platforms(product)
                   if app.settings.platform(p).enabled]
        platforms = [p for p in (cfg.react_platforms or enabled) if p in enabled]
    if not platforms:
        return []

    budget = max(0, int(cfg.max_reactions_per_day) - _reactions_today(app, product["id"]))
    if budget == 0:
        return []

    drafted = []
    for platform in platforms[:budget]:
        try:
            row = pipeline.generate_one(app, llm, product, platform, forced_trend=trend)
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
                  "1. relevance 0..1 — can we tie into this authentically? "
                  "(1 = perfect fit, 0 = irrelevant)\n"
                  "2. style_notes — one sentence on HOW creators are executing this trend "
                  "right now: the format (POV/skit/greenscreen/listicle/duet), pacing, "
                  "text-overlay style, audio type. This guides our content generation.")
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
                  max_age_hours: int = 48) -> list[dict]:
    rows = db_module.query(
        app.conn,
        "SELECT source, topic, trend_score, metadata, style_notes, velocity, collected_at "
        "FROM trends WHERE collected_at >= datetime('now', ?) ORDER BY trend_score DESC",
        (f"-{int(max_age_hours)} hours",),
    )
    # Dedupe by topic keeping the highest score; lightly boost source match.
    best: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        d["metadata"] = db_module.loads(d.get("metadata"), {})
        score = d["trend_score"] or 0.0
        if platform == "tiktok" and d["source"] == "tiktok":
            score += 0.05
        key = d["topic"].strip().lower()
        if key not in best or score > best[key]["_score"]:
            d["_score"] = score
            best[key] = d
    out = sorted(best.values(), key=lambda x: x["_score"], reverse=True)[:limit]
    for d in out:
        d.pop("_score", None)
    return out
