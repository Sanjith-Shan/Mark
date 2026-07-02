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
        meta = dict(t.get("metadata") or {})
        meta.update({"relevance": round(rel.relevance, 3), "raw_score": t["raw_score"]})
        db_module.insert(app.conn, "trends", source=t["source"], topic=t["topic"],
                         trend_score=final, metadata=meta,
                         style_notes=rel.style_notes or None)
        stored.append({"source": t["source"], "topic": t["topic"],
                       "trend_score": final, "metadata": meta,
                       "style_notes": rel.style_notes})
    stored.sort(key=lambda x: x["trend_score"], reverse=True)
    return stored


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
        "SELECT source, topic, trend_score, metadata, style_notes, collected_at FROM trends "
        "WHERE collected_at >= datetime('now', ?) ORDER BY trend_score DESC",
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
