"""Posting manager — routes a content row to the correct upload method.

Each content row targets a single platform (the strategist adapts copy per
platform), so we post one piece to one platform at a time. The X link strategy
(never put URLs in the post body) is honored by putting the link in a first
comment / reply instead.

Safety invariants enforced HERE (not just in scheduler paths), so every caller
— cron, web button, CLI, bulk — gets them:

* atomic claim: a row is flipped approved→posting in one statement before any
  network call, so double-clicks / overlapping jobs can't double-post;
* expired trend content never posts (dead memes are brand damage);
* links carry UTM tags (utm_campaign=<campaign>, utm_content=<content_id>) so
  clicks/installs are attributable to the exact post that earned them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse

from .. import db as db_module
from .. import store
from ..app import App
from .upload_post import UploadPostClient

# Platforms whose captions should carry hashtags appended.
HASHTAG_PLATFORMS = {"tiktok", "instagram", "x", "linkedin", "youtube", "pinterest"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_caption(app: App, content: dict) -> str:
    caption = (content["caption"] or "").strip()
    if content["platform"] in HASHTAG_PLATFORMS:
        from ..agents.writer import LENGTH_CAPS

        tags = list(db_module.loads(content["hashtags"], []) or [])
        cap = LENGTH_CAPS.get(content["platform"])
        # Shed trailing hashtags until the combined post fits the platform cap
        # (the copy is capped at write time, but hashtags are appended here).
        while tags:
            combined = f"{caption}\n\n{' '.join(tags)}".strip()
            if cap is None or len(combined) <= cap:
                return combined
            tags.pop()
    return caption


def tracked_url(url: str, platform: str, product_id: str, content_id) -> str:
    """Append UTM parameters so clicks→signups are attributable per post.
    This is the wire that closes the loop from content to business results."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return url
        params = urlencode({"utm_source": platform, "utm_medium": "social",
                            "utm_campaign": product_id,
                            "utm_content": str(content_id)})
        query = f"{parsed.query}&{params}" if parsed.query else params
        return urlunparse(parsed._replace(query=query))
    except Exception:
        return url


def _claim(app: App, content: dict) -> bool:
    """Atomically claim the row for posting. Exactly one caller wins; a lost
    claim means another poster (cron overlap, double-click) already has it."""
    cur = app.conn.execute(
        "UPDATE content SET status = 'posting' WHERE id = ? "
        "AND status IN ('approved', 'draft')",
        (content["id"],))
    app.conn.commit()
    return cur.rowcount == 1


def _release_claim(app: App, content_id: int, status: str, **extra) -> None:
    store.set_content_status(app.conn, content_id, status, **extra)


def post_content(app: App, content: dict, *, client: Optional[UploadPostClient] = None) -> dict:
    """Post one content row. Returns the upload-post normalized response.

    Records a row in ``posts`` and flips content status to ``posted`` (or
    ``failed``). Raises only programmer errors — provider failures are caught and
    recorded so the scheduler never crashes.
    """
    platform = content["platform"]

    # Dead-meme guard: expired trend content must never post, from ANY path.
    expires = content.get("expires_at")
    if expires and str(expires) <= _now():
        store.set_content_status(app.conn, content["id"], "rejected",
                                 rejection_feedback="auto-expired: trend window closed")
        db_module.log_activity(app.conn, "trend_expire",
                               f"Refused to post expired trend content #{content['id']}",
                               product_id=content["product_id"], content_id=content["id"])
        return {"error": "expired", "request_id": None, "results": {}}

    if not _claim(app, content):
        return {"error": "already claimed/posted", "request_id": None, "results": {}}

    prod = store.get_product(app.conn, content["product_id"])
    client = client or UploadPostClient(app, profile=(prod or {}).get("upload_profile"))
    title = build_caption(app, content)
    media = db_module.loads(content["media_paths"], []) or []
    ctype = content["content_type"]

    # X link strategy: link goes in a reply, never the post body. UTM-tagged so
    # every click is attributable to this exact post.
    first_comment = None
    if platform == "x" and prod and prod.get("website_url"):
        first_comment = tracked_url(prod["website_url"], platform,
                                    content["product_id"], content["id"])

    # Per-platform required params from the campaign (e.g. Reddit subreddit).
    opts = (db_module.loads(prod.get("platform_options"), {}) or {}) if prod else {}
    extra = dict(opts.get(platform) or {})

    # AI-content self-labeling: proactively labeled AIGC loses far less reach
    # than retroactively flagged content (and undisclosed synthetic video risks
    # 14-day suppression on TikTok). AI-slop and character content is synthetic
    # by design; AI-generated video counts too.
    sctx = db_module.loads(content.get("strategy_context"), {}) or {}
    synthetic = (sctx.get("strategy") in ("absurdist-ai-slop",)
                 or bool(sctx.get("character_id"))
                 or (ctype == "video" and not app.is_mock("fal")))
    if synthetic and platform == "tiktok":
        extra.setdefault("is_aigc", True)   # TikTok Content Posting API AIGC flag
    if synthetic and platform in ("instagram", "youtube"):
        extra.setdefault("is_ai_generated", True)  # passed through if supported

    try:
        if ctype == "video":
            if not media:
                raise RuntimeError("video content has no media file")
            resp = client.upload_video(media[0], title, [platform],
                                       first_comment=first_comment, **extra)
        elif ctype in ("image", "carousel"):
            if not media:
                raise RuntimeError(f"{ctype} content has no media files")
            resp = client.upload_photo(media, title, [platform],
                                       first_comment=first_comment, **extra)
        else:  # text, thread
            resp = client.upload_text(title, [platform],
                                      first_comment=first_comment, **extra)
    except Exception as exc:  # noqa: BLE001 - record and continue
        _release_claim(app, content["id"], "failed", error=f"post error: {exc}")
        db_module.log_activity(app.conn, "post", f"Failed to post #{content['id']} to {platform}: {exc}",
                               product_id=content["product_id"], content_id=content["id"],
                               level="error")
        return {"error": str(exc), "request_id": None, "results": {}}

    # upload-post returns 200 with per-platform outcomes — a rejected upload
    # (disconnected account, platform policy) arrives as status="failed" here.
    result = resp["results"].get(platform, {})
    if result.get("status") == "failed":
        err = result.get("error") or "platform rejected the upload"
        _release_claim(app, content["id"], "failed", error=f"{platform}: {err}")
        db_module.log_activity(app.conn, "post",
                               f"Failed to post #{content['id']} to {platform}: {err}",
                               product_id=content["product_id"], content_id=content["id"],
                               level="error")
        return {**resp, "error": err}

    # Record the post + flip status.
    store.insert_post(app.conn, content_id=content["id"], platform=platform,
                      platform_post_id=result.get("post_id"), request_id=resp.get("request_id"))
    _release_claim(app, content["id"], "posted", posted_at=_now(), error=None)
    db_module.log_activity(app.conn, "post", f"Posted {ctype} #{content['id']} to {platform}",
                           product_id=content["product_id"], content_id=content["id"],
                           level="success")
    return resp


def posts_today(app: App, platform: str, product_id: Optional[str] = None) -> int:
    """Posts made today on a platform. When the campaign posts through its own
    upload-post profile (multi-account test lab), the daily cap is per campaign
    — accounts are independent; a shared profile shares the cap."""
    if product_id:
        prod = store.get_product(app.conn, product_id)
        if prod and prod.get("upload_profile"):
            row = db_module.query_one(
                app.conn,
                "SELECT COUNT(*) AS n FROM posts p JOIN content c ON c.id = p.content_id "
                "WHERE p.platform = ? AND c.product_id = ? "
                "AND date(p.posted_at) = date('now')", (platform, product_id))
            return row["n"] if row else 0
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM posts p JOIN content c ON c.id = p.content_id "
        "LEFT JOIN products pr ON pr.id = c.product_id "
        "WHERE p.platform = ? AND COALESCE(pr.upload_profile, '') = '' "
        "AND date(p.posted_at) = date('now')", (platform,))
    return row["n"] if row else 0


def post_approved(app: App, product_id: Optional[str] = None, limit: int = 100,
                  respect_caps: bool = True) -> list[dict]:
    """Post approved content for a product (or all products).

    Honors the same invariants as the scheduler: expired content is skipped
    (and auto-rejected by post_content), user-scheduled content waits for its
    time, and per-platform daily caps apply unless explicitly disabled.
    """
    rows = store.list_content(app.conn, status="approved", product_id=product_id, limit=limit)
    out = []
    for row in rows:
        if row.get("scheduled_at") and str(row["scheduled_at"]) > _now():
            continue  # its own scheduler job posts it at the chosen time
        platform = row["platform"]
        if respect_caps:
            cap = app.settings.platform(platform).max_posts_per_day
            if posts_today(app, platform, product_id=row["product_id"]) >= cap:
                continue
        resp = post_content(app, row)
        out.append({"content_id": row["id"], "platform": platform, "response": resp})
    return out
