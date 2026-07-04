"""Bluesky trending topics — free realtime, one unauthenticated HTTP call.

Bluesky uniquely exposes platform trends publicly. Volume skews news/tech, so
this feeds text-trend detection for Bluesky/X/Threads posts. Each item:

    {"source": "bluesky", "topic": str, "raw_score": float, "metadata": {...}}
"""

from __future__ import annotations

from ..app import App

TRENDING_URL = "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics"

_FALLBACK = [
    ("new grad job market", 70), ("ai hiring screens", 66),
    ("return to office", 62), ("internship season", 58),
]


def fetch(app: App, limit: int = 15) -> list[dict]:
    if not app.force_mock:
        live = _fetch_live(limit)
        if live:
            return live
    return [{"source": "bluesky", "topic": t, "raw_score": float(s),
             "metadata": {"fallback": True}} for t, s in _FALLBACK[:limit]]


def _fetch_live(limit: int) -> list[dict] | None:
    try:
        import httpx

        with httpx.Client(timeout=12) as client:
            resp = client.get(TRENDING_URL, params={"limit": str(limit)},
                              headers={"User-Agent": "mark-trends/1.0"})
            resp.raise_for_status()
            data = resp.json()
        topics = data.get("topics") or []
        out = []
        n = max(len(topics), 1)
        for i, t in enumerate(topics[:limit]):
            topic = (t.get("topic") or t.get("displayName") or "").strip()
            if not topic:
                continue
            out.append({"source": "bluesky", "topic": topic,
                        "raw_score": float(90 - i * (60 / n)),
                        "metadata": {"link": t.get("link")}})
        return out or None
    except Exception:
        return None
