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
    # RSS first: it carries the real approx_traffic signal, and pytrends'
    # trending_searches endpoint has been dead/unreliable since 2025.
    if not app.force_mock:
        live = _fetch_rss(limit) or _fetch_pytrends(limit)
        if live:
            return live
    return [{"source": "google", "topic": t, "raw_score": float(s),
             "metadata": {"fallback": True}} for t, s in _FALLBACK[:limit]]


def _traffic_score(traffic: str) -> float | None:
    """'200K+' / '1M+' / '50,000+' → 0-100 popularity score (log scale)."""
    import math

    m = re.match(r"([\d,.]+)\s*([KM]?)", (traffic or "").strip(), flags=re.IGNORECASE)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    n *= {"K": 1_000, "M": 1_000_000}.get(m.group(2).upper(), 1)
    if n <= 0:
        return None
    # 10K → ~53, 100K → ~66, 1M → ~80, 20M+ → 100
    return round(min(100.0, 13.3 * math.log10(n)), 1)


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
            import html as html_mod

            items = re.findall(r"<item>(.*?)</item>", resp.text, flags=re.DOTALL)
            out = []
            for i, item in enumerate(items[:limit]):
                m = re.search(r"<title>(.*?)</title>", item, flags=re.DOTALL)
                if not m:
                    continue
                topic = html_mod.unescape(m.group(1).strip())
                traffic = re.search(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", item)
                meta = {"approx_traffic": traffic.group(1)} if traffic else {}
                # Real search-volume signal when present; rank position otherwise.
                score = (_traffic_score(traffic.group(1)) if traffic else None) \
                    or float(90 - i * (60 / max(len(items), 1)))
                out.append({"source": "google", "topic": topic,
                            "raw_score": score, "metadata": meta})
            if out:
                return out
        except Exception:
            continue
    return None
