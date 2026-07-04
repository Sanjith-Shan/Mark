"""Reddit rising posts — the best free early-warning trend source.

Niche-subreddit "rising" posts show unusual upvote velocity BEFORE they peak,
often 1-3 days ahead of the same joke reaching TikTok. For a job-market product
the niche subs are simultaneously trend signal AND content material (the pain
posts are exactly the audience's life).

Public JSON endpoints, no auth needed at this polling volume. Each item:

    {"source": "reddit", "topic": str, "raw_score": float, "metadata": {...}}
"""

from __future__ import annotations

import time

from ..app import App

RISING_URL = "https://www.reddit.com/r/{sub}/rising.json"

# Product-relevant defaults; override via config trends.subreddits.
DEFAULT_SUBREDDITS = ["recruitinghell", "internships", "jobs",
                      "csMajors", "cscareerquestions", "college"]

_FALLBACK = [
    ("rejection email after 6 rounds of interviews", 70),
    ("ghosted by a recruiter after final round", 66),
    ("entry level job requiring 5 years experience", 64),
    ("application portal made me retype my whole resume", 60),
]


def fetch(app: App, subreddits: list[str] | None = None, limit: int = 20) -> list[dict]:
    subs = subreddits or DEFAULT_SUBREDDITS
    if not app.force_mock:
        live = _fetch_live(subs, limit)
        if live:
            return live
    return [{"source": "reddit", "topic": t, "raw_score": float(s),
             "metadata": {"fallback": True}} for t, s in _FALLBACK[:limit]]


def _fetch_live(subs: list[str], limit: int) -> list[dict] | None:
    try:
        import httpx

        headers = {"User-Agent": "mark-trends/1.0 (personal marketing tool)"}
        out = []
        per_sub = max(3, limit // max(len(subs), 1))
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            for sub in subs:
                try:
                    resp = client.get(RISING_URL.format(sub=sub),
                                      params={"limit": str(per_sub)}, headers=headers)
                    resp.raise_for_status()
                    children = (resp.json().get("data") or {}).get("children") or []
                except Exception:
                    continue
                for child in children:
                    d = child.get("data") or {}
                    title = (d.get("title") or "").strip()
                    if not title or d.get("stickied"):
                        continue
                    ups = int(d.get("ups") or 0)
                    created = d.get("created_utc") or (time.time() - 3600)
                    age_h = max(time.time() - created, 600) / 3600
                    # Upvote velocity, squashed to ~0-100.
                    score = min(100.0, (ups / age_h) * 2.0)
                    out.append({
                        "source": "reddit",
                        "topic": title[:140],
                        "raw_score": round(score, 1),
                        "metadata": {"subreddit": sub, "ups": ups,
                                     "permalink": f"https://reddit.com{d.get('permalink', '')}"},
                    })
        out.sort(key=lambda x: x["raw_score"], reverse=True)
        return out[:limit] or None
    except Exception:
        return None
