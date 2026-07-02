"""TikTok Creative Center trending hashtags.

The Creative Center exposes trending hashtags without login. Its internal JSON
endpoint is best-effort (it changes and sometimes rate-limits), so any failure
falls back to a curated set of evergreen short-form trend formats. Each item:

    {"topic": str, "raw_score": float (0..100), "metadata": {...}}
"""

from __future__ import annotations

from ..app import App

CREATIVE_CENTER_API = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
)

# Evergreen short-form formats used when the live endpoint is unavailable.
_FALLBACK = [
    ("day in my life", 92), ("get ready with me", 88), ("pov", 86),
    ("before and after", 84), ("study with me", 80), ("how i", 78),
    ("things i wish i knew", 76), ("a week in my life", 72),
    ("productivity hacks", 70), ("life hack", 68),
]


def fetch_trending(app: App, country: str = "US", limit: int = 20) -> list[dict]:
    if not app.force_mock:
        live = _fetch_live(country, limit)
        if live:
            return live
    return [{"source": "tiktok", "topic": t, "raw_score": float(s),
             "metadata": {"fallback": True}} for t, s in _FALLBACK[:limit]]


def _fetch_live(country: str, limit: int) -> list[dict] | None:
    try:
        import httpx

        params = {"period": "7", "page": "1", "limit": str(limit),
                  "country_code": country, "sort_by": "popular"}
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        with httpx.Client(timeout=12) as client:
            resp = client.get(CREATIVE_CENTER_API, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        items = (data.get("data") or {}).get("list") or []
        out = []
        for it in items[:limit]:
            name = it.get("hashtag_name") or it.get("name")
            if not name:
                continue
            out.append({
                "source": "tiktok",
                "topic": name,
                "raw_score": float(it.get("trend") or it.get("rank") or 50),
                "metadata": {"publish_cnt": it.get("publish_cnt"),
                             "video_views": it.get("video_views")},
            })
        return out or None
    except Exception:
        return None
