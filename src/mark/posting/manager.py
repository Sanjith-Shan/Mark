"""Posting manager — routes a content row to the correct upload method.

Each content row targets a single platform (the strategist adapts copy per
platform), so we post one piece to one platform at a time. The X link strategy
(never put URLs in the post body) is honored by putting the link in a first
comment / reply instead.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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


def post_content(app: App, content: dict, *, client: Optional[UploadPostClient] = None) -> dict:
    """Post one content row. Returns the upload-post normalized response.

    Records a row in ``posts`` and flips content status to ``posted`` (or
    ``failed``). Raises only programmer errors — provider failures are caught and
    recorded so the scheduler never crashes.
    """
    client = client or UploadPostClient(app)
    platform = content["platform"]
    title = build_caption(app, content)
    media = db_module.loads(content["media_paths"], []) or []
    ctype = content["content_type"]
    prod = store.get_product(app.conn, content["product_id"])

    # X link strategy: link goes in a reply, never the post body.
    first_comment = None
    if platform == "x" and prod and prod.get("website_url"):
        first_comment = prod["website_url"]

    # Per-platform required params from the campaign (e.g. Reddit subreddit).
    opts = (db_module.loads(prod.get("platform_options"), {}) or {}) if prod else {}
    extra = dict(opts.get(platform) or {})

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
        store.set_content_status(app.conn, content["id"], "failed",
                                 error=f"post error: {exc}")
        db_module.log_activity(app.conn, "post", f"Failed to post #{content['id']} to {platform}: {exc}",
                               product_id=content["product_id"], content_id=content["id"],
                               level="error")
        return {"error": str(exc), "request_id": None, "results": {}}

    # upload-post returns 200 with per-platform outcomes — a rejected upload
    # (disconnected account, platform policy) arrives as status="failed" here.
    result = resp["results"].get(platform, {})
    if result.get("status") == "failed":
        err = result.get("error") or "platform rejected the upload"
        store.set_content_status(app.conn, content["id"], "failed",
                                 error=f"{platform}: {err}")
        db_module.log_activity(app.conn, "post",
                               f"Failed to post #{content['id']} to {platform}: {err}",
                               product_id=content["product_id"], content_id=content["id"],
                               level="error")
        return {**resp, "error": err}

    # Record the post + flip status.
    store.insert_post(app.conn, content_id=content["id"], platform=platform,
                      platform_post_id=result.get("post_id"), request_id=resp.get("request_id"))
    store.set_content_status(app.conn, content["id"], "posted", posted_at=_now(), error=None)
    db_module.log_activity(app.conn, "post", f"Posted {ctype} #{content['id']} to {platform}",
                           product_id=content["product_id"], content_id=content["id"],
                           level="success")
    return resp


def post_approved(app: App, product_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    """Post all approved content for a product (or all products)."""
    rows = store.list_content(app.conn, status="approved", product_id=product_id, limit=limit)
    client = UploadPostClient(app)
    out = []
    for row in rows:
        resp = post_content(app, row, client=client)
        out.append({"content_id": row["id"], "platform": row["platform"], "response": resp})
    return out
