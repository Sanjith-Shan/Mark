"""Analytics collector — pull engagement metrics and store the time series.

Real path calls upload-post.com's analytics endpoints. Offline path synthesizes
plausible, growing metrics (deterministic per post) so the learning loop has data
to optimize against. Either way we compute ``engagement_rate`` and append a row to
``metrics``.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

log = logging.getLogger("mark.analytics")

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
    # Metrics stabilize within weeks; polling every post ever made forever
    # burns API quota for nothing. 45 days covers reward maturity + baselines.
    posts = store.list_posts(app.conn, product_id=product_id,
                             since_days=days if days is not None else 45)
    client = UploadPostClient(app)
    out = []
    for post in posts:
        rid = post.get("request_id") or ""
        # Posts made offline carry "mock-…" ids the real API doesn't know;
        # keep synthesizing metrics for them even after keys are added.
        if app.is_mock("upload_post") or not rid or rid.startswith("mock-"):
            m = _mock_metrics(app, post)
        else:
            try:
                raw = client.post_analytics(rid)
                m = _parse_metrics(raw, post["platform"])
            except Exception as exc:  # one bad post must not abort the sweep
                log.warning("analytics fetch failed for post %s (request_id=%s): %s",
                            post["id"], rid, exc)
                continue
            if not any(m.values()):
                # All-zero almost always means the response shape wasn't
                # recognized (or analytics aren't ready). Storing it would
                # poison rewards/winners/calibration with a fake flop.
                log.warning("analytics for post %s returned all zeros; skipping row",
                            post["id"])
                continue
        m["engagement_rate"] = _engagement_rate(m)
        db_module.insert(app.conn, "metrics", post_id=post["id"], **m)
        out.append({"post_id": post["id"], "platform": post["platform"], **m})
    collect_comments(app, posts, client=client)
    return out


# --------------------------------------------------------------------------- #
# Comments (fuel for sentiment analysis + the feedback loop)
# --------------------------------------------------------------------------- #
def collect_comments(app: App, posts: list[dict],
                     client: Optional[UploadPostClient] = None) -> int:
    """Pull comments for posts and store new ones (deduped per post by text).

    Live path: upload-post only exposes comment text for Instagram; other
    platforms only report counts. Offline path synthesizes plausible comments so
    the sentiment loop is exercised end-to-end.
    """
    client = client or UploadPostClient(app)
    added = 0
    for post in posts:
        if app.is_mock("upload_post") or not post.get("platform_post_id"):
            fetched = _mock_comments(app, post)
        else:
            fetched = client.get_comments(post["platform"], post["platform_post_id"])
        if not fetched:
            continue
        existing = {r["comment_text"] for r in db_module.query(
            app.conn, "SELECT comment_text FROM comments WHERE post_id = ?", (post["id"],))}
        for c in fetched:
            if c["text"] in existing:
                continue
            db_module.insert(app.conn, "comments", post_id=post["id"],
                             comment_text=c["text"], author=c.get("author"),
                             platform=post["platform"])
            added += 1
    return added


_MOCK_COMMENT_POOL = [
    ("this is actually so useful", "positive"), ("okay I need this", "positive"),
    ("where has this been all my life 😭", "positive"), ("just tried it, works great", "positive"),
    ("love the idea", "positive"), ("sharing this with my roommate", "positive"),
    ("is this free?", "neutral"), ("how is this different from the other ones?", "neutral"),
    ("does it work outside the US?", "neutral"), ("what's the catch", "neutral"),
    ("seen 100 of these, all the same", "negative"), ("feels like an ad tbh", "negative"),
    ("tried it, didn't work for me", "negative"),
]


def _mock_comments(app: App, post: dict) -> list[dict]:
    """Deterministic synthetic comments — mostly none, sometimes a few, weighted
    positive (matching real engagement distributions)."""
    prior = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM comments WHERE post_id = ?", (post["id"],))
    rng = random.Random(post["id"] * 7919 + (prior["n"] if prior else 0))
    n = rng.choice([0, 0, 1, 1, 2, 3])
    picks = rng.sample(_MOCK_COMMENT_POOL, k=min(n, len(_MOCK_COMMENT_POOL)))
    return [{"text": text, "author": f"user{rng.randint(100, 9999)}"} for text, _ in picks]


def _engagement_rate(m: dict) -> float:
    """Weighted engagement per view. Shares and saves are weighted 2x likes:
    2025-26 ranking signals put sends/saves far above likes on every short-form
    platform (they predict distribution; likes barely do) — see
    docs/research/strategy-frameworks.md 'Measurement'."""
    views = max(m.get("views", 0), 1)
    interactions = (m.get("likes", 0) + m.get("comments", 0)
                    + 2 * m.get("shares", 0) + 2 * m.get("saves", 0))
    return round(interactions / views, 5)


# Which content attributes the simulated audience has opinions about.
_TASTE_ARMS = ("hook_style", "tone", "strategy", "humor_mechanism",
               "humor_persona", "emotional_target")


def _taste_multiplier(app: App, post: dict) -> float:
    """Hidden ground-truth audience preference for the offline world.

    The old synthesizer was content-blind — engagement was pure noise, so the
    learning loop had nothing real to converge on and no convergence proof was
    possible. Now every mock post's engagement depends on WHAT it was (hook
    style, tone, strategy, persona, emotion), via:

      1. a planted taste profile in meta key ``mock_taste`` (JSON of
         ``{"platform:arm_type:value": mult}`` or ``{"arm_type:value": mult}``)
         — used by the evolution-proof harness to plant known preferences and
         then SHIFT them mid-run;
      2. otherwise a deterministic hidden taste derived by hashing
         (product, platform, arm, value) into [0.8, 1.25] — stable, invisible
         to the generator, and discoverable only by experimenting.
    """
    import hashlib

    content = db_module.query_one(
        app.conn, "SELECT product_id, strategy_context, content_type FROM content WHERE id = ?",
        (post["content_id"],))
    if not content:
        return 1.0
    sctx = db_module.loads(content["strategy_context"], {}) or {}
    platform = post["platform"]
    profile = db_module.loads(db_module.get_meta(app.conn, "mock_taste"), None) or {}
    mult = 1.0
    for arm_type in _TASTE_ARMS:
        value = sctx.get(arm_type)
        if not value:
            continue
        planted = profile.get(f"{platform}:{arm_type}:{value}", profile.get(f"{arm_type}:{value}"))
        if planted is not None:
            mult *= float(planted)
            continue
        seed_src = f"{content['product_id']}|{platform}|{arm_type}|{value}"
        h = int.from_bytes(hashlib.sha256(seed_src.encode()).digest()[:8], "big")
        mult *= 0.8 + (h % 10_000) / 10_000 * 0.45  # uniform [0.8, 1.25]
    return mult


def _mock_metrics(app: App, post: dict) -> dict:
    prior = db_module.query_one(
        app.conn, "SELECT COUNT(*) AS n FROM metrics WHERE post_id = ?", (post["id"],))
    growth = (prior["n"] if prior else 0) + 1
    rng = random.Random(post["id"] * 100 + growth)
    taste = _taste_multiplier(app, post)
    views = int(rng.uniform(500, 6000) * growth)
    lo, hi = _PLATFORM_LIKE_RATE.get(post["platform"], (0.03, 0.08))
    likes = int(views * rng.uniform(lo, hi) * taste)
    comments = int(likes * rng.uniform(0.03, 0.12))
    shares = int(likes * rng.uniform(0.02, 0.10))
    saves = int(likes * rng.uniform(0.05, 0.25))
    clicks = int(views * rng.uniform(0.005, 0.03) * taste)
    return {"views": views, "likes": likes, "comments": comments,
            "shares": shares, "saves": saves, "clicks": clicks}


def _parse_metrics(raw: dict, platform: str) -> dict:
    """Defensively pull metrics out of upload-post's analytics response.

    Documented shape: {"platforms": {"<p>": {"post_metrics": {...}}}} — but we
    tolerate older/other nestings too.
    """
    block = raw
    for key in ("platforms", "results", "analytics", "data"):
        if isinstance(raw.get(key), dict):
            block = raw[key].get(platform, raw[key])
            break
    if isinstance(block, dict) and isinstance(block.get("post_metrics"), dict):
        block = block["post_metrics"]

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
