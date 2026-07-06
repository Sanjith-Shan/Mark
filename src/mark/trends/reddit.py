"""Reddit rising posts — the best free early-warning trend source.

Niche-subreddit "rising" posts show unusual upvote velocity BEFORE they peak,
often 1-3 days ahead of the same joke reaching TikTok. For a job-market product
the niche subs are simultaneously trend signal AND content material (the pain
posts are exactly the audience's life).

Access strategy (verified live July 2026): Reddit now 403s anonymous JSON from
most networks, but (a) the OAuth application-only API works with a free script
app (env REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET — 100 req/min), and (b) the
Atom feeds (`/r/<sub>/hot.rss`) still answer anonymously when politely paced
(~1 request per second, no query params). So: OAuth when creds exist, paced
RSS otherwise, canned fallback last. Each item:

    {"source": "reddit", "topic": str, "raw_score": float, "metadata": {...}}
"""

from __future__ import annotations

import html as html_mod
import os
import re
import time

from ..app import App

RISING_URL = "https://www.reddit.com/r/{sub}/rising.json"

_UA = "mark/1.0 (personal marketing tool; contact: local)"
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_RSS_PACING_S = 1.2   # anonymous feeds get blocked when hammered — pace politely
_token_cache: dict = {"token": None, "expires": 0.0}


# --------------------------------------------------------------------------- #
# Shared access layer (used by trend radar AND humor radar)
# --------------------------------------------------------------------------- #
def oauth_token() -> str | None:
    """Application-only OAuth token (free Reddit 'script' app). None = no creds."""
    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        return None
    if _token_cache["token"] and time.time() < _token_cache["expires"] - 60:
        return _token_cache["token"]
    try:
        import httpx

        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(cid, secret), data={"grant_type": "client_credentials"},
            headers={"User-Agent": _UA}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        _token_cache["token"] = data.get("access_token")
        _token_cache["expires"] = time.time() + float(data.get("expires_in") or 3600)
        return _token_cache["token"]
    except Exception:
        return None


def get_listing(sub: str, listing: str = "hot", limit: int = 15) -> list[dict] | None:
    """Full listing children via OAuth (includes ups/created). None = no creds
    or the call failed — caller should try RSS next."""
    token = oauth_token()
    if not token:
        return None
    try:
        import httpx

        resp = httpx.get(
            f"https://oauth.reddit.com/r/{sub}/{listing}",
            params={"limit": str(limit)},
            headers={"Authorization": f"Bearer {token}", "User-Agent": _UA},
            timeout=12)
        resp.raise_for_status()
        return [(c.get("data") or {}) for c in
                ((resp.json().get("data") or {}).get("children") or [])]
    except Exception:
        return None


_IMG_IN_ENTRY = re.compile(
    r'https://(?:i\.redd\.it|preview\.redd\.it)/[^"&\\<>]+?\.(?:jpg|jpeg|png|gif)',
    re.IGNORECASE)


def get_rss(sub: str, listing: str = "hot") -> list[dict] | None:
    """Anonymous Atom feed: rank-ordered entries with title/permalink/author and
    (usually) an extractable image URL. No upvote counts — rank is the signal."""
    try:
        import httpx

        resp = httpx.get(f"https://www.reddit.com/r/{sub}/{listing}.rss",
                         headers={"User-Agent": _BROWSER_UA},
                         timeout=15, follow_redirects=True)
        resp.raise_for_status()
        text = resp.text
        out = []
        for i, entry in enumerate(re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)):
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r'<link href="([^"]+)"', entry)
            author = re.search(r"<name>([^<]+)</name>", entry)
            img = _IMG_IN_ENTRY.search(entry.replace("&amp;", "&"))
            if not title:
                continue
            out.append({
                "rank": i,
                "title": html_mod.unescape(title.group(1)).strip(),
                "permalink": link.group(1) if link else None,
                "author": (author.group(1) or "").strip() if author else None,
                "image_url": img.group(0) if img else None,
                "id": (link.group(1).rstrip("/").rsplit("/", 2)[-2]
                       if link and "/comments/" in link.group(1) else f"{sub}-rss-{i}"),
            })
        return out or None
    except Exception:
        return None

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


SEARCH_URL = "https://www.reddit.com/search.json"


def fetch_search(app: App, keywords: list[str], limit: int = 15) -> list[dict]:
    """Keyword search across all of Reddit (hot, past day) — the per-campaign
    theming lever for campaigns whose niche has no obvious home subreddits.
    Returns [] when no keywords are configured; never uses canned fallbacks."""
    if not keywords:
        return []
    if app.force_mock:
        return []
    out = []
    per_kw = max(3, limit // max(len(keywords), 1))
    token = oauth_token()
    for i, kw in enumerate(keywords[:6]):
        try:
            import httpx

            if token:
                resp = httpx.get(
                    "https://oauth.reddit.com/search",
                    params={"q": kw, "sort": "hot", "t": "day", "limit": str(per_kw)},
                    headers={"Authorization": f"Bearer {token}", "User-Agent": _UA},
                    timeout=12)
                resp.raise_for_status()
                children = [(c.get("data") or {}) for c in
                            ((resp.json().get("data") or {}).get("children") or [])]
                for d in children:
                    title = (d.get("title") or "").strip()
                    if not title or d.get("stickied") or d.get("over_18"):
                        continue
                    ups = int(d.get("ups") or 0)
                    created = d.get("created_utc") or (time.time() - 3600)
                    age_h = max(time.time() - created, 600) / 3600
                    score = min(100.0, (ups / age_h) * 2.0)
                    out.append({
                        "source": "reddit", "topic": title[:140],
                        "raw_score": round(score, 1),
                        "metadata": {"keyword": kw, "ups": ups,
                                     "subreddit": d.get("subreddit"),
                                     "permalink": f"https://reddit.com{d.get('permalink', '')}"},
                    })
            else:
                if i > 0:
                    time.sleep(_RSS_PACING_S)
                resp = httpx.get("https://www.reddit.com/search.rss",
                                 params={"q": kw, "sort": "hot", "t": "day"},
                                 headers={"User-Agent": _BROWSER_UA},
                                 timeout=15, follow_redirects=True)
                resp.raise_for_status()
                entries = re.findall(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
                for rank, entry in enumerate(entries[:per_kw]):
                    m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
                    link = re.search(r'<link href="([^"]+)"', entry)
                    if not m:
                        continue
                    out.append({
                        "source": "reddit",
                        "topic": html_mod.unescape(m.group(1)).strip()[:140],
                        "raw_score": round(max(20.0, 70.0 - rank * 5.0), 1),
                        "metadata": {"keyword": kw, "rss": True,
                                     "permalink": link.group(1) if link else None},
                    })
        except Exception:
            continue
    out.sort(key=lambda x: x["raw_score"], reverse=True)
    return out[:limit]


def _fetch_live(subs: list[str], limit: int) -> list[dict] | None:
    out = []
    per_sub = max(3, limit // max(len(subs), 1))
    for i, sub in enumerate(subs):
        children = get_listing(sub, "rising", limit=per_sub)
        if children is not None:  # OAuth path: real upvote velocity
            for d in children:
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
            continue
        # Anonymous path: paced RSS, rank-derived score.
        if i > 0:
            time.sleep(_RSS_PACING_S)
        entries = get_rss(sub, "rising") or get_rss(sub, "hot")
        for e in (entries or [])[:per_sub]:
            out.append({
                "source": "reddit",
                "topic": e["title"][:140],
                "raw_score": round(max(20.0, 75.0 - e["rank"] * 4.0), 1),
                "metadata": {"subreddit": sub, "rss": True,
                             "permalink": e.get("permalink")},
            })
    out.sort(key=lambda x: x["raw_score"], reverse=True)
    return out[:limit] or None
