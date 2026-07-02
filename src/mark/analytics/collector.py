"""Analytics collector — pull engagement metrics and store the time series.

Real path calls upload-post.com's analytics endpoints. Offline path synthesizes
plausible, growing metrics (deterministic per post) so the learning loop has data
to optimize against. Either way we compute ``engagement_rate`` and append a row to
``metrics``.
"""

from __future__ import annotations

import random
from typing import Optional

from .. import db as db_module
from .. import store
from ..app import App
from ..posting.upload_post import UploadPostClient

# Per-platform like-rate priors for the offline synthesizer (relative to views).
_PLATFORM_LIKE_RATE = {
    "tiktok": (0.06, 0.14), "instagram": (0.04, 0.10), "x": (0.02, 0.06),
    "linkedin": (0.03, 0.08), "youtube": (0.04, 0.09), "bluesky": (0.03, 0.07),
    "threads": (0.03, 0.08),
}


def collect(app: App, product_id: Optional[str] = None,
            days: Optional[int] = None) -> list[dict]:
    posts = store.list_posts(app.conn, product_id=product_id, since_days=days)
    client = UploadPostClient(app)
    out = []
    for post in posts:
        if app.is_mock("upload_post") or not post.get("request_id"):
            m = _mock_metrics(app, post)
        else:
            raw = client.post_analytics(post["request_id"])
            m = _parse_metrics(raw, post["platform"])
        m["engagement_rate"] = _engagement_rate(m)
        db_module.insert(app.conn, "metrics", post_id=post["id"], **m)
        out.append({"post_id": post["id"], "platform": post["platform"], **m})
    return out


def _engagement_rate(m: dict) -> float:
    views = max(m.get("views", 0), 1)
    interactions = m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0) + m.get("saves", 0)
    return round(interactions / views, 5)


def _mock_metrics(app: App, post: dict) -> dict:
    prior = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM metrics WHERE post_id = ?", (post["id"],))
    growth = (prior["n"] if prior else 0) + 1
    rng = random.Random(post["id"] * 100 + growth)
    views = int(rng.uniform(500, 6000) * growth)
    lo, hi = _PLATFORM_LIKE_RATE.get(post["platform"], (0.03, 0.08))
    likes = int(views * rng.uniform(lo, hi))
    comments = int(likes * rng.uniform(0.03, 0.12))
    shares = int(likes * rng.uniform(0.02, 0.10))
    saves = int(likes * rng.uniform(0.05, 0.25))
    clicks = int(views * rng.uniform(0.005, 0.03))
    return {"views": views, "likes": likes, "comments": comments,
            "shares": shares, "saves": saves, "clicks": clicks}


def _parse_metrics(raw: dict, platform: str) -> dict:
    """Defensively pull metrics out of upload-post's analytics response."""
    block = raw
    for key in ("results", "analytics", "data", "platforms"):
        if isinstance(raw.get(key), dict):
            block = raw[key].get(platform, raw[key])
            break

    def g(*names):
        for n in names:
            v = block.get(n) if isinstance(block, dict) else None
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return 0

    return {
        "views": g("views", "impressions", "play_count", "view_count"),
        "likes": g("likes", "like_count", "favorites"),
        "comments": g("comments", "comment_count", "replies"),
        "shares": g("shares", "share_count", "reposts", "retweets"),
        "saves": g("saves", "saved", "bookmarks"),
        "clicks": g("clicks", "link_clicks", "url_clicks"),
    }


# --------------------------------------------------------------------------- #
# Read side (for `mark analytics`)
# --------------------------------------------------------------------------- #
def recent_performance(app: App, product_id: Optional[str] = None,
                       days: int = 7) -> list[dict]:
    posts = store.list_posts(app.conn, product_id=product_id, since_days=days)
    rows = []
    for p in posts:
        m = store.latest_metric(app.conn, p["id"])
        if not m:
            continue
        rows.append({
            "content_id": p["content_id"], "platform": p["platform"],
            "content_type": p["content_type"], "hook": p["hook"],
            "views": m["views"], "likes": m["likes"], "comments": m["comments"],
            "shares": m["shares"], "saves": m["saves"],
            "engagement_rate": m["engagement_rate"],
        })
    rows.sort(key=lambda r: r["engagement_rate"], reverse=True)
    return rows
