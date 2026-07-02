"""Google Trends — daily trending searches.

Prefers pytrends if installed; otherwise parses Google's public daily-trends RSS
(no key required). Falls back to a small evergreen set when offline. Each item:

    {"source": "google", "topic": str, "raw_score": float, "metadata": {...}}
"""

from __future__ import annotations

import re

from ..app import App

DAILY_RSS = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

_FALLBACK = [
    ("ai tools", 80), ("remote jobs", 74), ("internships 2026", 70),
    ("resume tips", 66), ("side hustle", 64), ("productivity apps", 60),
]


def fetch(app: App, limit: int = 20) -> list[dict]:
    if not app.force_mock:
        live = _fetch_pytrends(limit) or _fetch_rss(limit)
        if live:
            return live
    return [{"source": "google", "topic": t, "raw_score": float(s),
             "metadata": {"fallback": True}} for t, s in _FALLBACK[:limit]]


def _fetch_pytrends(limit: int) -> list[dict] | None:
    try:
        from pytrends.request import TrendReq  # type: ignore

        pytrends = TrendReq(hl="en-US", tz=360)
        df = pytrends.trending_searches(pn="united_states")
        topics = [str(x) for x in df[0].tolist()][:limit]
        n = len(topics)
        return [{"source": "google", "topic": t, "raw_score": float(90 - i * (60 / max(n, 1))),
                 "metadata": {}} for i, t in enumerate(topics)]
    except Exception:
        return None


def _fetch_rss(limit: int) -> list[dict] | None:
    try:
        import httpx

        with httpx.Client(timeout=12) as client:
            resp = client.get(DAILY_RSS, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        titles = re.findall(r"<title>(.*?)</title>", resp.text, flags=re.DOTALL)
        # First <title> is the feed name; skip it.
        topics = [t.strip() for t in titles[1:] if t.strip()][:limit]
        n = len(topics)
        return [{"source": "google", "topic": t, "raw_score": float(90 - i * (60 / max(n, 1))),
                 "metadata": {}} for i, t in enumerate(topics)] or None
    except Exception:
        return None
