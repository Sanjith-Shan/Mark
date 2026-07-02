"""Google Trends — daily trending searches.

Prefers pytrends if installed; otherwise parses Google's public daily-trends RSS
(no key required). Falls back to a small evergreen set when offline. Each item:

    {"source": "google", "topic": str, "raw_score": float, "metadata": {...}}
"""

from __future__ import annotations

import re

from ..app import App

# Verified working July 2026; the older /trends/trendingsearches/daily/rss path
# is kept as a fallback in case of regional differences.
DAILY_RSS = "https://trends.google.com/trending/rss?geo=US"
DAILY_RSS_LEGACY = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

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
    for url in (DAILY_RSS, DAILY_RSS_LEGACY):
        try:
            import httpx

            with httpx.Client(timeout=12, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
            items = re.findall(r"<item>(.*?)</item>", resp.text, flags=re.DOTALL)
            out = []
            for i, item in enumerate(items[:limit]):
                m = re.search(r"<title>(.*?)</title>", item, flags=re.DOTALL)
                if not m:
                    continue
                topic = m.group(1).strip()
                traffic = re.search(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", item)
                meta = {"approx_traffic": traffic.group(1)} if traffic else {}
                out.append({"source": "google", "topic": topic,
                            "raw_score": float(90 - i * (60 / max(len(items), 1))),
                            "metadata": meta})
            if out:
                return out
        except Exception:
            continue
    return None
