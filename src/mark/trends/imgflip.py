"""Imgflip get_memes — which meme templates are alive RIGHT NOW.

A dead template is worse than no meme (stale-format cringe), so meme-carousel
generation checks template freshness against this free, keyless API. Templates
surface as trends with source="imgflip" and a "meme template:" prefix so the
strategist can grab a live format when writing meme content.
"""

from __future__ import annotations

from ..app import App

API_URL = "https://api.imgflip.com/get_memes"

_FALLBACK = [
    ("Distracted Boyfriend", 70), ("Drake Hotline Bling", 68),
    ("Two Buttons", 66), ("Expanding Brain", 62), ("Change My Mind", 60),
]


def fetch(app: App, limit: int = 15) -> list[dict]:
    if not app.force_mock:
        live = _fetch_live(limit)
        if live:
            return live
    return [{"source": "imgflip", "topic": f"meme template: {t}",
             "raw_score": float(s), "metadata": {"fallback": True}}
            for t, s in _FALLBACK[:limit]]


def _fetch_live(limit: int) -> list[dict] | None:
    try:
        import httpx

        with httpx.Client(timeout=12) as client:
            resp = client.get(API_URL)
            resp.raise_for_status()
            data = resp.json()
        memes = ((data.get("data") or {}).get("memes") or [])[:limit]
        n = max(len(memes), 1)
        out = []
        for i, m in enumerate(memes):
            name = (m.get("name") or "").strip()
            if not name:
                continue
            out.append({"source": "imgflip", "topic": f"meme template: {name}",
                        "raw_score": float(85 - i * (50 / n)),
                        "metadata": {"template_id": m.get("id"),
                                     "box_count": m.get("box_count")}})
        return out or None
    except Exception:
        return None
