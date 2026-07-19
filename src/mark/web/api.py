"""REST API — everything the web UI can do.

All endpoints are sync (FastAPI runs them in a thread pool); each request gets a
per-thread App via the Runtime. Long work (generate/post/learn/trends/collect)
returns a job id immediately; progress streams over /api/events (SSE).
"""

# NOTE: no `from __future__ import annotations` here — it would turn endpoint
# annotations into strings, and FastAPI cannot resolve ForwardRefs to the
# request-body models defined inside build_router()'s closure (bodies would
# silently degrade to required query params and every POST/PATCH would 422).
import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from .. import db as db_module
from .. import store
from ..config import ProductConfig, Settings
from .runtime import Runtime


def build_router(rt: Runtime) -> APIRouter:
    r = APIRouter(prefix="/api")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def media_url(path: str) -> Optional[str]:
        """Absolute file path -> served /media URL (None if outside media dir)."""
        try:
            rel = Path(path).resolve().relative_to(rt.app().paths.media_dir.resolve())
            return f"/media/{rel.as_posix()}"
        except Exception:
            return None

    def content_out(row: dict) -> dict:
        out = dict(row)
        out["hashtags"] = db_module.loads(row.get("hashtags"), [])
        out["media_paths"] = db_module.loads(row.get("media_paths"), [])
        out["strategy_context"] = db_module.loads(row.get("strategy_context"), {})
        out["draft"] = db_module.loads(row.get("draft"), {})
        out["media"] = []
        for p in out["media_paths"]:
            url = media_url(p)
            if url:
                kind = "video" if p.endswith((".mp4", ".mov", ".webm")) else "image"
                out["media"].append({"url": url, "kind": kind, "name": Path(p).name})
        return out

    def get_content_or_404(content_id: int) -> dict:
        row = store.get_content(rt.app().conn, content_id)
        if not row:
            raise HTTPException(404, f"content {content_id} not found")
        return row

    def get_product_or_404(product_id: str) -> dict:
        row = store.get_product(rt.app().conn, product_id)
        if not row:
            raise HTTPException(404, f"campaign {product_id} not found")
        return row

    def product_out(p: dict) -> dict:
        out = dict(p)
        out["platforms"] = db_module.loads(p.get("platforms"), [])
        out["posting_cadence"] = db_module.loads(p.get("posting_cadence"), {})
        out["platform_options"] = db_module.loads(p.get("platform_options"), {})
        out["trend_sources"] = db_module.loads(p.get("trend_sources"), {})
        return out

    CAMPAIGN_KINDS = ("product", "entertainment")
    CONTENT_RATINGS = ("clean", "standard", "edgy")

    def check_campaign_enums(kind: Optional[str], content_rating: Optional[str]) -> None:
        if kind is not None and kind not in CAMPAIGN_KINDS:
            raise HTTPException(400, f"kind must be one of {', '.join(CAMPAIGN_KINDS)}")
        if content_rating is not None and content_rating not in CONTENT_RATINGS:
            raise HTTPException(
                400, f"content_rating must be one of {', '.join(CONTENT_RATINGS)}")

    def normalized_trend_sources(ts: Optional[dict]) -> Optional[dict]:
        if ts is None:
            return None
        return {"subreddits": [str(s).strip() for s in ts.get("subreddits", []) if str(s).strip()],
                "keywords": [str(k).strip() for k in ts.get("keywords", []) if str(k).strip()]}

    # ------------------------------------------------------------------ #
    # Status / overview
    # ------------------------------------------------------------------ #
    @r.get("/status")
    def status() -> dict:
        app = rt.app()
        providers = {p: ("mock" if app.is_mock(p) else "live")
                     for p in ("openai", "fal", "upload_post", "elevenlabs")}
        spend = db_module.query_one(
            app.conn, "SELECT COALESCE(SUM(usd), 0) AS usd FROM costs WHERE mocked = 0")
        spend_30d = db_module.query_one(
            app.conn, "SELECT COALESCE(SUM(usd), 0) AS usd FROM costs "
                      "WHERE mocked = 0 AND created_at >= datetime('now', '-30 days')")
        return {
            "providers": providers,
            "force_mock": app.force_mock,
            "autopilot": {"running": rt.autopilot.running,
                          "started_at": rt.autopilot.started_at},
            "counts": store.content_counts(app.conn),
            "spend_total_usd": round(spend["usd"], 4) if spend else 0,
            "spend_30d_usd": round(spend_30d["usd"], 4) if spend_30d else 0,
            "timezone": app.settings.scheduling.timezone,
        }

    @r.get("/overview")
    def overview() -> dict:
        app = rt.app()
        campaigns = []
        for p in store.list_products(app.conn):
            counts = store.content_counts(app.conn, p["id"])
            perf = db_module.query_one(
                app.conn,
                """
                SELECT COUNT(DISTINCT po.id) AS posts,
                       COALESCE(AVG(m.engagement_rate), 0) AS avg_engagement,
                       COALESCE(SUM(m.views), 0) AS views
                FROM posts po
                JOIN content c ON c.id = po.content_id
                LEFT JOIN metrics m ON m.id = (
                    SELECT id FROM metrics WHERE post_id = po.id
                    ORDER BY collected_at DESC LIMIT 1)
                WHERE c.product_id = ?
                  AND po.posted_at >= datetime('now', '-7 days')
                """, (p["id"],))
            spend = db_module.query_one(
                app.conn, "SELECT COALESCE(SUM(usd), 0) AS usd FROM costs "
                          "WHERE product_id = ? AND mocked = 0", (p["id"],))
            campaigns.append({
                **product_out(p),
                "counts": counts,
                "posts_7d": perf["posts"] if perf else 0,
                "avg_engagement_7d": round(perf["avg_engagement"], 4) if perf else 0,
                "views_7d": perf["views"] if perf else 0,
                "spend_usd": round(spend["usd"], 4) if spend else 0,
            })
        # Engagement time series (all campaigns, last 14 days).
        series = [dict(row) for row in db_module.query(
            app.conn,
            """
            SELECT date(po.posted_at) AS day, c.platform AS platform,
                   AVG(m.engagement_rate) AS engagement, SUM(m.views) AS views
            FROM metrics m
            JOIN posts po ON po.id = m.post_id
            JOIN content c ON c.id = po.content_id
            WHERE m.id IN (SELECT MAX(id) FROM metrics GROUP BY post_id)
              AND po.posted_at >= datetime('now', '-14 days')
            GROUP BY day, c.platform ORDER BY day
            """)]
        return {
            "campaigns": campaigns,
            "series": series,
            "activity": store.list_activity(app.conn, limit=30),
            "jobs": rt.jobs.recent(10),
        }

    @r.get("/activity")
    def activity(campaign: Optional[str] = None, limit: int = 100) -> list[dict]:
        return store.list_activity(rt.app().conn, limit=limit, product_id=campaign)

    # ------------------------------------------------------------------ #
    # Campaigns
    # ------------------------------------------------------------------ #
    class CampaignIn(BaseModel):
        id: Optional[str] = None
        name: str
        description: str
        target_audience: str
        brand_voice: str
        website_url: Optional[str] = None
        platforms: list[str] = Field(default_factory=list)
        posting_cadence: dict[str, int] = Field(default_factory=dict)
        platform_options: dict[str, dict] = Field(default_factory=dict)
        active: bool = True
        kind: str = "product"                 # "product" | "entertainment"
        content_rating: str = "standard"      # "clean" | "standard" | "edgy"
        upload_profile: Optional[str] = None  # per-campaign upload-post profile
        trend_sources: dict[str, list[str]] = Field(default_factory=dict)  # subreddits/keywords

    @r.get("/campaigns")
    def campaigns() -> list[dict]:
        return [product_out(p) for p in store.list_products(rt.app().conn)]

    @r.post("/campaigns")
    def create_campaign(body: CampaignIn) -> dict:
        app = rt.app()
        pid = body.id or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")
        if not pid:
            raise HTTPException(400, "campaign needs a name")
        check_campaign_enums(body.kind, body.content_rating)
        cfg = ProductConfig(
            id=pid, name=body.name, description=body.description,
            target_audience=body.target_audience, brand_voice=body.brand_voice,
            website_url=body.website_url, platforms=body.platforms,
            posting_cadence=body.posting_cadence or {p: 1 for p in body.platforms},
        )
        store.upsert_product(app.conn, cfg, active=False)
        trend_sources = normalized_trend_sources(body.trend_sources) or {}
        store.update_product(app.conn, pid,
                             active=1 if body.active else 0, archived=0,
                             platform_options=body.platform_options,
                             kind=body.kind, content_rating=body.content_rating,
                             upload_profile=body.upload_profile or None,
                             trend_sources=trend_sources)
        # Keep a YAML copy alongside (same as the CLI flow) for portability.
        try:
            yaml_path = app.paths.products_dir / f"{pid}.yaml"
            yaml_path.write_text(yaml.safe_dump(
                {**cfg.model_dump(), "platform_options": body.platform_options,
                 "kind": body.kind, "content_rating": body.content_rating,
                 "upload_profile": body.upload_profile,
                 "trend_sources": trend_sources},
                sort_keys=False))
        except Exception:
            pass
        db_module.log_activity(app.conn, "campaign", f"Campaign “{body.name}” saved",
                               product_id=pid, level="success")
        return product_out(get_product_or_404(pid))

    @r.get("/campaigns/{product_id}")
    def campaign(product_id: str) -> dict:
        return product_out(get_product_or_404(product_id))

    class CampaignPatch(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        target_audience: Optional[str] = None
        brand_voice: Optional[str] = None
        website_url: Optional[str] = None
        platforms: Optional[list[str]] = None
        posting_cadence: Optional[dict[str, int]] = None
        platform_options: Optional[dict[str, dict]] = None
        active: Optional[bool] = None
        kind: Optional[str] = None
        content_rating: Optional[str] = None
        upload_profile: Optional[str] = None
        trend_sources: Optional[dict[str, list[str]]] = None

    @r.patch("/campaigns/{product_id}")
    def patch_campaign(product_id: str, body: CampaignPatch) -> dict:
        app = rt.app()
        get_product_or_404(product_id)
        check_campaign_enums(body.kind, body.content_rating)
        fields: dict[str, Any] = {}
        for k in ("name", "description", "target_audience", "brand_voice",
                  "website_url", "platforms", "posting_cadence", "platform_options",
                  "kind", "content_rating", "upload_profile"):
            v = getattr(body, k)
            if v is not None:
                fields[k] = v
        if body.trend_sources is not None:
            fields["trend_sources"] = normalized_trend_sources(body.trend_sources)
        if body.active is not None:
            fields["active"] = 1 if body.active else 0
        if fields:
            store.update_product(app.conn, product_id, **fields)
        if body.active is not None:
            db_module.log_activity(
                app.conn, "campaign",
                f"Campaign {'resumed' if body.active else 'paused'}",
                product_id=product_id)
        return product_out(get_product_or_404(product_id))

    @r.delete("/campaigns/{product_id}")
    def archive_campaign(product_id: str) -> dict:
        app = rt.app()
        get_product_or_404(product_id)
        store.archive_product(app.conn, product_id)
        db_module.log_activity(app.conn, "campaign", "Campaign archived",
                               product_id=product_id)
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # Content
    # ------------------------------------------------------------------ #
    @r.get("/content")
    def content_list(status: Optional[str] = None, campaign: Optional[str] = None,
                     platform: Optional[str] = None, limit: int = 100) -> list[dict]:
        # Platform filtering happens in SQL so LIMIT applies AFTER the filter —
        # filtering in Python post-LIMIT silently hid matching items.
        rows = store.list_content(rt.app().conn, status=status,
                                  product_id=campaign, platform=platform, limit=limit)
        return [content_out(x) for x in rows]

    @r.get("/content/{content_id}")
    def content_detail(content_id: int) -> dict:
        app = rt.app()
        row = get_content_or_404(content_id)
        out = content_out(row)
        posts = [dict(x) for x in db_module.query(
            app.conn, "SELECT * FROM posts WHERE content_id = ? ORDER BY posted_at DESC",
            (content_id,))]
        for p in posts:
            p["latest_metric"] = store.latest_metric(app.conn, p["id"])
            p["comments"] = [dict(c) for c in db_module.query(
                app.conn, "SELECT * FROM comments WHERE post_id = ? ORDER BY id DESC LIMIT 50",
                (p["id"],))]
        out["posts"] = posts
        return out

    class ContentPatch(BaseModel):
        caption: Optional[str] = None
        hook: Optional[str] = None
        hashtags: Optional[list[str]] = None
        scheduled_at: Optional[str] = None
        # Draft-level fields (script, prompts, slides) — merged into draft JSON.
        script: Optional[str] = None
        cta: Optional[str] = None
        alt_text: Optional[str] = None
        image_prompt: Optional[str] = None
        image_prompts: Optional[list[str]] = None
        video_prompt: Optional[str] = None
        slide_texts: Optional[list[str]] = None

    @r.patch("/content/{content_id}")
    def patch_content(content_id: int, body: ContentPatch) -> dict:
        app = rt.app()
        row = get_content_or_404(content_id)
        # Posted content is immutable — the winners index and learning history
        # embed the caption/hook as posted; editing after the fact corrupts them.
        if row["status"] == "posted":
            raise HTTPException(400, "content is already posted and cannot be edited")
        fields: dict[str, Any] = {}
        for k in ("caption", "hook", "hashtags", "scheduled_at"):
            v = getattr(body, k)
            if v is not None:
                fields[k] = v
        if body.hashtags is not None:  # normalize: posting joins these verbatim
            fields["hashtags"] = [h if h.startswith("#") else f"#{h}"
                                  for h in (t.strip() for t in body.hashtags) if h]
        draft = db_module.loads(row.get("draft"), {}) or {}
        draft_changed = False
        for k in ("script", "cta", "alt_text", "image_prompt", "image_prompts",
                  "video_prompt", "slide_texts", "caption", "hook", "hashtags"):
            v = getattr(body, k, None)
            if v is not None:
                draft[k] = v
                draft_changed = True
        if draft_changed:
            fields["draft"] = draft
        if fields:
            store.update_content(app.conn, content_id, **fields)
            db_module.log_activity(app.conn, "edit", f"Edited content #{content_id}",
                                   product_id=row["product_id"], content_id=content_id)
        return content_out(get_content_or_404(content_id))

    @r.post("/content/{content_id}/approve")
    def approve(content_id: int) -> dict:
        from datetime import datetime, timezone

        app = rt.app()
        row = get_content_or_404(content_id)
        # Trend content has a TTL — approving after the window closed would
        # queue a dead meme for posting.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if row.get("expires_at") and str(row["expires_at"]) <= now:
            raise HTTPException(
                400, f"content {content_id} expired at {row['expires_at']} UTC — "
                     "the trend window has closed; reject it instead")
        already_approved = row["status"] == "approved"
        store.set_content_status(
            app.conn, content_id, "approved",
            approved_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        db_module.log_activity(app.conn, "approve", f"Approved content #{content_id}",
                               product_id=row["product_id"], content_id=content_id,
                               level="success")
        # Character episodes advance the lore on FIRST approval only — a
        # double-click/retry must not drift the running counters.
        if not already_approved:
            from .. import characters as characters_mod

            try:
                characters_mod.on_content_approved(app, row)
            except Exception:
                pass
        rt.bus.publish("content", {"id": content_id, "status": "approved"})
        return content_out(get_content_or_404(content_id))

    class RejectIn(BaseModel):
        feedback: str = ""

    @r.post("/content/{content_id}/reject")
    def reject(content_id: int, body: RejectIn) -> dict:
        app = rt.app()
        row = get_content_or_404(content_id)
        store.set_content_status(app.conn, content_id, "rejected",
                                 rejection_feedback=body.feedback or None)
        db_module.log_activity(app.conn, "reject",
                               f"Rejected content #{content_id}"
                               + (f": {body.feedback[:80]}" if body.feedback else ""),
                               product_id=row["product_id"], content_id=content_id)
        rt.bus.publish("content", {"id": content_id, "status": "rejected"})
        return content_out(get_content_or_404(content_id))

    @r.post("/content/{content_id}/post")
    def post_now(content_id: int) -> dict:
        row = get_content_or_404(content_id)
        if row["status"] not in ("approved", "draft", "failed"):
            raise HTTPException(400, f"content is {row['status']}, cannot post")

        def _run(app, llm, job, report):
            from ..posting import manager

            report(0.2, f"Posting to {row['platform']}…")
            resp = manager.post_content(app, store.get_content(app.conn, content_id))
            if resp.get("error"):
                raise RuntimeError(resp["error"])
            rt.bus.publish("content", {"id": content_id, "status": "posted"})
            return {"request_id": resp.get("request_id")}

        job = rt.jobs.submit("post", f"Post #{content_id} → {row['platform']}", _run,
                             product_id=row["product_id"])
        return {"job_id": job.id}

    class RewriteIn(BaseModel):
        instruction: Optional[str] = None

    @r.post("/content/{content_id}/rewrite")
    def rewrite(content_id: int, body: RewriteIn) -> dict:
        row = get_content_or_404(content_id)

        def _run(app, llm, job, report):
            from .. import pipeline

            report(0.2, "Rewriting copy…")
            out = pipeline.rewrite_content(app, llm, content_id, body.instruction)
            rt.bus.publish("content", {"id": content_id, "status": out["status"]})
            return {"content_id": content_id}

        job = rt.jobs.submit("rewrite", f"Rewrite #{content_id}", _run,
                             product_id=row["product_id"])
        return {"job_id": job.id}

    @r.post("/content/{content_id}/regenerate-media")
    def regenerate_media(content_id: int) -> dict:
        row = get_content_or_404(content_id)

        def _run(app, llm, job, report):
            from .. import pipeline

            report(0.1, "Regenerating media…")
            pipeline.regenerate_media(app, llm, content_id)
            rt.bus.publish("content", {"id": content_id, "status": row["status"]})
            return {"content_id": content_id}

        job = rt.jobs.submit("media", f"Regenerate media #{content_id}", _run,
                             product_id=row["product_id"])
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    class GenerateIn(BaseModel):
        campaign_id: Optional[str] = None     # default: all running campaigns
        platforms: Optional[list[str]] = None  # default: campaign's platforms
        count: int = 1

    @r.post("/generate")
    def generate(body: GenerateIn) -> dict:
        app = rt.app()
        if body.campaign_id:
            products = [get_product_or_404(body.campaign_id)]
        else:
            products = [p for p in store.list_products(app.conn) if p["active"]]
        if not products:
            raise HTTPException(400, "no running campaigns — create or resume one first")

        def _run(app, llm, job, report):
            from .. import pipeline

            created: list[int] = []
            tasks = []
            for product in products:
                plats = body.platforms or [
                    p for p in pipeline.product_platforms(product)
                    if app.settings.platform(p).enabled]
                tasks.extend((product, p) for p in plats for _ in range(max(1, body.count)))
            for i, (product, platform) in enumerate(tasks):
                report(i / max(len(tasks), 1),
                       f"{product['name']}: drafting {platform} ({i + 1}/{len(tasks)})")
                try:
                    row = pipeline.generate_one(app, llm, product, platform)
                    created.append(row["id"])
                    rt.bus.publish("content", {"id": row["id"], "status": row["status"]})
                except Exception as exc:  # keep going; report per-piece failures
                    db_module.log_activity(app.conn, "generate",
                                           f"Generation failed for {platform}: {exc}",
                                           product_id=product["id"], level="error")
            report(1.0, f"Created {len(created)} drafts")
            return {"created": created}

        label = ("Generate for " + products[0]["name"]) if len(products) == 1 \
            else f"Generate for {len(products)} campaigns"
        job = rt.jobs.submit("generate", label, _run,
                             product_id=products[0]["id"] if len(products) == 1 else None)
        return {"job_id": job.id}

    @r.post("/post-approved")
    def post_approved(campaign: Optional[str] = None) -> dict:
        def _run(app, llm, job, report):
            from ..posting import manager

            report(0.1, "Posting approved content…")
            out = manager.post_approved(app, product_id=campaign)
            ok = sum(1 for o in out if not o["response"].get("error"))
            report(1.0, f"Posted {ok}/{len(out)}")
            return {"posted": ok, "attempted": len(out)}

        job = rt.jobs.submit("post", "Post all approved", _run, product_id=campaign)
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Analytics / comments
    # ------------------------------------------------------------------ #
    @r.get("/analytics")
    def analytics(campaign: Optional[str] = None, days: int = 30) -> dict:
        app = rt.app()
        from ..analytics import collector

        table = collector.recent_performance(app, product_id=campaign, days=days)
        where_campaign = "AND c.product_id = ?" if campaign else ""
        params: list[Any] = [f"-{int(days)} days"] + ([campaign] if campaign else [])
        series = [dict(row) for row in db_module.query(
            app.conn,
            f"""
            SELECT date(po.posted_at) AS day, c.platform AS platform,
                   AVG(m.engagement_rate) AS engagement,
                   SUM(m.views) AS views, SUM(m.likes) AS likes,
                   SUM(m.comments) AS comments, SUM(m.shares) AS shares
            FROM metrics m
            JOIN posts po ON po.id = m.post_id
            JOIN content c ON c.id = po.content_id
            WHERE m.id IN (SELECT MAX(id) FROM metrics GROUP BY post_id)
              AND po.posted_at >= datetime('now', ?) {where_campaign}
            GROUP BY day, c.platform ORDER BY day
            """, params)]
        totals = db_module.query_one(
            app.conn,
            f"""
            SELECT COALESCE(SUM(m.views), 0) AS views, COALESCE(SUM(m.likes), 0) AS likes,
                   COALESCE(SUM(m.comments), 0) AS comments,
                   COALESCE(SUM(m.shares), 0) AS shares,
                   COALESCE(AVG(m.engagement_rate), 0) AS avg_engagement
            FROM metrics m JOIN posts po ON po.id = m.post_id
            JOIN content c ON c.id = po.content_id
            WHERE m.id IN (SELECT MAX(id) FROM metrics GROUP BY post_id)
              AND po.posted_at >= datetime('now', ?) {where_campaign}
            """, params)
        return {"table": table, "series": series,
                "totals": dict(totals) if totals else {}}

    @r.post("/analytics/collect")
    def collect(campaign: Optional[str] = None) -> dict:
        def _run(app, llm, job, report):
            from ..analytics import collector, sentiment

            report(0.2, "Collecting metrics…")
            out = collector.collect(app, product_id=campaign)
            report(0.7, "Scoring comment sentiment…")
            scored = sentiment.analyze_unscored(app, llm, product_id=campaign)
            report(1.0, f"Collected {len(out)} metric snapshots, scored {scored} comments")
            db_module.log_activity(app.conn, "analytics",
                                   f"Collected metrics for {len(out)} posts",
                                   product_id=campaign)
            return {"metrics": len(out), "comments_scored": scored}

        job = rt.jobs.submit("analytics", "Collect analytics", _run, product_id=campaign)
        return {"job_id": job.id}

    @r.get("/comments")
    def comments(campaign: Optional[str] = None, limit: int = 100) -> dict:
        app = rt.app()
        where_campaign = "WHERE c.product_id = ?" if campaign else ""
        params = ([campaign] if campaign else []) + [limit]
        rows = [dict(x) for x in db_module.query(
            app.conn,
            f"""
            SELECT cm.*, po.platform AS post_platform, c.id AS content_id,
                   c.hook AS content_hook, c.product_id AS product_id
            FROM comments cm
            JOIN posts po ON po.id = cm.post_id
            JOIN content c ON c.id = po.content_id
            {where_campaign}
            ORDER BY cm.id DESC LIMIT ?
            """, params)]
        from ..analytics import sentiment

        return {"comments": rows,
                "sentiment_summary": sentiment.summarize(app, product_id=campaign)}

    @r.get("/costs")
    def costs(days: int = 30) -> dict:
        app = rt.app()
        rows = [dict(x) for x in db_module.query(
            app.conn,
            """
            SELECT provider, operation, COUNT(*) AS calls,
                   SUM(usd) AS usd, SUM(mocked) AS mocked_calls
            FROM costs WHERE created_at >= datetime('now', ?)
            GROUP BY provider, operation ORDER BY usd DESC
            """, (f"-{int(days)} days",))]
        by_day = [dict(x) for x in db_module.query(
            app.conn,
            "SELECT date(created_at) AS day, SUM(usd) AS usd FROM costs "
            "WHERE mocked = 0 AND created_at >= datetime('now', ?) "
            "GROUP BY day ORDER BY day", (f"-{int(days)} days",))]
        return {"breakdown": rows, "by_day": by_day}

    # ------------------------------------------------------------------ #
    # Trends / learning
    # ------------------------------------------------------------------ #
    @r.get("/trends")
    def trends(limit: int = 25) -> list[dict]:
        from ..trends import aggregator

        return aggregator.recent_trends(rt.app(), limit=limit)

    @r.post("/trends/refresh")
    def refresh_trends(campaign: Optional[str] = None) -> dict:
        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        if not product:
            raise HTTPException(400, "no campaign to score trends against")

        def _run(app, llm, job, report):
            from ..trends import aggregator

            report(0.2, "Fetching trend sources…")
            out = aggregator.refresh(app, llm, product)
            report(1.0, f"Ranked {len(out)} trends")
            db_module.log_activity(app.conn, "trends",
                                   f"Refreshed {len(out)} trends",
                                   product_id=product["id"])
            return {"count": len(out)}

        job = rt.jobs.submit("trends", "Refresh trends", _run, product_id=product["id"])
        return {"job_id": job.id}

    @r.get("/trends/hot")
    def hot_trends(limit: int = 5) -> list[dict]:
        from ..trends import aggregator

        return aggregator.hot_trends(rt.app(), limit=limit, for_auto_react=False)

    # ------------------------------------------------------------------ #
    # Humor radar — curated copyworthy humor (entertainment campaigns)
    # ------------------------------------------------------------------ #
    @r.get("/humor")
    def humor_finds(campaign: Optional[str] = None, limit: int = 12) -> list[dict]:
        from .. import humor_radar
        from ..llm import LLM

        app = rt.app()
        product = store.get_product(app.conn, campaign) if campaign else None
        return humor_radar.radar(app, LLM(app), campaign=product, limit=limit)

    @r.post("/humor/refresh")
    def refresh_humor() -> dict:
        def _run(app, llm, job, report):
            from .. import humor_radar

            report(0.2, "Polling humor sources…")
            out = humor_radar.refresh(app, llm)
            report(1.0, f"Scored {len(out)} finds")
            db_module.log_activity(app.conn, "humor_radar",
                                   f"Humor radar refreshed: {len(out)} finds")
            return {"count": len(out)}

        job = rt.jobs.submit("humor", "Refresh humor radar", _run)
        return {"job_id": job.id}

    class HumorDraftIn(BaseModel):
        campaign_id: str
        platform: str = "x"

    @r.post("/humor/{find_id}/draft")
    def humor_draft(find_id: int, body: HumorDraftIn) -> dict:
        from .. import humor_radar
        from ..llm import LLM

        app = rt.app()
        product = store.get_product(app.conn, body.campaign_id)
        if not product:
            raise HTTPException(404, f"campaign {body.campaign_id!r} not found")
        try:
            row = humor_radar.draft_repost(app, LLM(app), product, find_id,
                                           platform=body.platform)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return content_out(row)

    # ------------------------------------------------------------------ #
    # Paid clipping-campaign discovery (ContentRewards/Whop). DISCOVERY +
    # TRACKING ONLY — joining/posting/submitting are always human actions.
    # ------------------------------------------------------------------ #
    @r.get("/clip-campaigns")
    def clip_campaigns(limit: int = 15, include_blocked: bool = False) -> list[dict]:
        from ..templates import campaigns

        app = rt.app()
        return campaigns.digest(app, limit=limit, include_blocked=include_blocked)

    @r.post("/clip-campaigns/refresh")
    def refresh_clip_campaigns() -> dict:
        def _run(app, llm, job, report):
            from ..templates import campaigns

            report(0.2, "Polling clipping-campaign platforms…")
            campaigns.refresh(app, llm)
            rows = campaigns.digest(app, limit=200, include_blocked=True)
            report(1.0, f"Tracking {len(rows)} campaigns")
            return {"count": len(rows)}

        job = rt.jobs.submit("clip_campaigns", "Refresh clip campaigns", _run)
        return {"job_id": job.id}

    @r.post("/clip-campaigns/{campaign_id}/joined")
    def mark_clip_campaign_joined(campaign_id: int, joined: bool = True) -> dict:
        """Record that the HUMAN joined this campaign (never automated)."""
        app = rt.app()
        db_module.execute(app.conn, "UPDATE clip_campaigns SET joined = ? WHERE id = ?",
                          (1 if joined else 0, campaign_id))
        return {"id": campaign_id, "joined": joined}

    class ReactIn(BaseModel):
        campaign_id: Optional[str] = None
        topic: Optional[str] = None            # default: hottest qualifying trend
        platforms: Optional[list[str]] = None  # default: config react_platforms/all

    @r.post("/trends/react")
    def react_to_trend(body: ReactIn) -> dict:
        app = rt.app()
        product = store.resolve_product(app.conn, body.campaign_id)
        if not product:
            raise HTTPException(400, "no campaign to react for")
        from ..trends import aggregator

        trend = None
        if body.topic:
            for t in aggregator.recent_trends(app, limit=100, max_age_hours=48):
                if t["topic"].strip().lower() == body.topic.strip().lower():
                    trend = t
                    break
            if trend is None:
                raise HTTPException(404, f"trend “{body.topic}” not found in recent trends")

        def _run(app, llm, job, report):
            report(0.1, "Riding the trend…")
            rows = aggregator.react(app, llm, product, trend=trend,
                                    platforms=body.platforms)
            for row in rows:
                rt.bus.publish("content", {"id": row["id"], "status": row["status"]})
            report(1.0, f"Drafted {len(rows)} trend posts")
            return {"created": [row["id"] for row in rows]}

        label = f"React to “{(trend or {}).get('topic', 'hottest trend')}”"
        job = rt.jobs.submit("trends", label, _run, product_id=product["id"])
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Strategies
    # ------------------------------------------------------------------ #
    @r.get("/strategies")
    def strategies_catalog(campaign: Optional[str] = None) -> list[dict]:
        from .. import strategies as strategies_mod

        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        allowlist = strategies_mod.product_allowlist(product) if product else None
        out = []
        for s in strategies_mod.STRATEGIES:
            d = s.model_dump()
            d["enabled"] = (allowlist is None) or (s.id in allowlist)
            if product:
                d["episode"] = strategies_mod.episode_number(
                    app, product, "", s) if s.series_format else None
                d["usage"] = db_module.query_one(
                    app.conn,
                    "SELECT COUNT(*) AS n FROM content WHERE product_id = ? "
                    "AND strategy_context LIKE ?",
                    (product["id"], f'%"strategy": "{s.id}"%'))["n"]
            out.append(d)
        return out

    class StrategiesIn(BaseModel):
        strategies: Optional[list[str]] = None  # null = all enabled

    @r.patch("/campaigns/{product_id}/strategies")
    def set_campaign_strategies(product_id: str, body: StrategiesIn) -> dict:
        from .. import strategies as strategies_mod

        app = rt.app()
        get_product_or_404(product_id)
        if body.strategies is not None:
            unknown = [s for s in body.strategies if not strategies_mod.get(s)]
            if unknown:
                raise HTTPException(400, f"unknown strategies: {', '.join(unknown)}")
        # null = all enabled; [] = all disabled (stored as an explicit empty
        # list — a falsy check here would silently invert the request).
        store.update_product(app.conn, product_id, strategies=body.strategies)
        db_module.log_activity(app.conn, "edit",
                               "Updated strategy allowlist", product_id=product_id)
        return product_out(get_product_or_404(product_id))

    # ------------------------------------------------------------------ #
    # Characters (AI ambassadors)
    # ------------------------------------------------------------------ #
    def character_out(c: dict) -> dict:
        out = dict(c)
        ref = c.get("reference_image")
        out["reference_url"] = media_url(ref) if ref else None
        return out

    @r.get("/characters")
    def characters_list(campaign: Optional[str] = None) -> list[dict]:
        from .. import characters as characters_mod

        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        if not product:
            return []
        rows = characters_mod.list_for_product(app, product["id"], include_inactive=True)
        return [character_out(c) for c in rows]

    @r.post("/characters/sync")
    def characters_sync() -> list[dict]:
        from .. import characters as characters_mod

        synced = characters_mod.sync_from_config(rt.app())
        return [character_out(c) for c in synced]

    class CharacterPatch(BaseModel):
        persona: Optional[str] = None
        visual_desc: Optional[str] = None
        voice: Optional[str] = None
        catchphrases: Optional[list[str]] = None
        active: Optional[bool] = None

    @r.patch("/characters/{character_id}")
    def patch_character(character_id: int, body: CharacterPatch) -> dict:
        from .. import characters as characters_mod

        app = rt.app()
        if not characters_mod.get(app, character_id):
            raise HTTPException(404, "character not found")
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if "active" in fields:
            fields["active"] = 1 if fields["active"] else 0
        out = characters_mod.update(app, character_id, **fields)
        return character_out(out)

    @r.post("/characters/{character_id}/sheet")
    def generate_sheet(character_id: int) -> dict:
        from .. import characters as characters_mod

        character = characters_mod.get(rt.app(), character_id)
        if not character:
            raise HTTPException(404, "character not found")

        def _run(app, llm, job, report):
            report(0.2, f"Generating reference sheet for {character['name']}…")
            # Force regeneration: clear the stored path first.
            db_module.update(app.conn, "characters", character_id, reference_image=None)
            fresh = characters_mod.get(app, character_id)
            path = characters_mod.ensure_reference_image(app, llm, fresh)
            return {"reference_image": str(path)}

        job = rt.jobs.submit("media", f"Character sheet: {character['name']}", _run,
                             product_id=character["product_id"])
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Comment replies (drafted for one-tap approval)
    # ------------------------------------------------------------------ #
    @r.get("/replies")
    def replies_list(campaign: Optional[str] = None, status: str = "draft",
                     limit: int = 50) -> list[dict]:
        from .. import replies as replies_mod

        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        return replies_mod.list_drafts(app, product_id=product["id"] if product else None,
                                       status=status, limit=limit)

    @r.post("/replies/draft")
    def draft_replies_now(campaign: Optional[str] = None) -> dict:
        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        if not product:
            raise HTTPException(400, "no campaign")

        def _run(app, llm, job, report):
            from .. import replies as replies_mod

            report(0.3, "Drafting replies to fresh comments…")
            drafted = replies_mod.draft_replies(app, llm, product)
            report(1.0, f"Drafted {len(drafted)} replies")
            return {"drafted": len(drafted)}

        job = rt.jobs.submit("replies", "Draft comment replies", _run,
                             product_id=product["id"])
        return {"job_id": job.id}

    class ReplyPatch(BaseModel):
        reply_text: Optional[str] = None
        status: Optional[str] = None   # "approved" | "posted" | "skipped" | "draft"

    @r.patch("/replies/{reply_id}")
    def patch_reply(reply_id: int, body: ReplyPatch) -> dict:
        from .. import replies as replies_mod

        app = rt.app()
        row = replies_mod.get(app, reply_id)
        if not row:
            raise HTTPException(404, "reply not found")
        out = replies_mod.set_status(app, reply_id, body.status or row["status"],
                                     reply_text=body.reply_text)
        return out

    @r.get("/insights")
    def insights(campaign: Optional[str] = None) -> dict:
        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        if not product:
            return {"insights": None, "bandit": [], "winners": 0, "holdout_lift": None}
        from ..learning import bandit, feedback, winners

        data = feedback.latest_insights(app, product["id"])
        insights_out = None
        if data:
            data = dict(data)
            created = data.pop("_created_at", None)
            insights_out = {"payload": data, "created_at": created}
        return {
            "insights": insights_out,
            "bandit": bandit.leaderboard(app, product["id"]),
            "winners": winners.count(app, product_id=product["id"]),
            # Standing empirical proof the learning loop lifts performance:
            # bandit-policy posts vs the random holdout control group.
            "holdout_lift": feedback.holdout_lift(app, product["id"]),
            "campaign": product["id"],
        }

    class LearnIn(BaseModel):
        campaign_id: Optional[str] = None
        days: int = 7

    @r.post("/learn")
    def learn(body: LearnIn) -> dict:
        app = rt.app()
        if body.campaign_id:
            products = [get_product_or_404(body.campaign_id)]
        else:
            products = [p for p in store.list_products(app.conn) if p["active"]]
        if not products:
            raise HTTPException(400, "no running campaigns")

        def _run(app, llm, job, report):
            from ..learning import feedback

            reports = []
            for i, product in enumerate(products):
                report(i / len(products), f"Learning from {product['name']}…")
                reports.append(feedback.run(app, llm, product, days=body.days))
                db_module.log_activity(app.conn, "learn",
                                       "Feedback loop complete",
                                       product_id=product["id"], level="success")
            report(1.0, "Feedback loop complete")
            return {"reports": reports}

        job = rt.jobs.submit("learn", "Run feedback loop", _run)
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Experiments (campaigns as A/B variants)
    # ------------------------------------------------------------------ #
    @r.get("/experiments")
    def experiments_list() -> list[dict]:
        from .. import experiments as experiments_mod

        return experiments_mod.list_experiments(rt.app())

    class ExperimentIn(BaseModel):
        name: str
        hypothesis: str = ""
        campaign_ids: list[str]
        metric: str = "engagement_rate"

    @r.post("/experiments")
    def create_experiment(body: ExperimentIn) -> dict:
        from .. import experiments as experiments_mod

        app = rt.app()
        if not body.name.strip():
            raise HTTPException(400, "experiment needs a name")
        if len(body.campaign_ids) < 2:
            raise HTTPException(400, "an experiment needs at least 2 variant campaigns")
        for cid in body.campaign_ids:
            get_product_or_404(cid)
        exp_id = experiments_mod.create_experiment(
            app, body.name.strip(), body.hypothesis.strip(),
            body.campaign_ids, metric=body.metric)
        db_module.log_activity(app.conn, "experiment",
                               f"Experiment “{body.name.strip()}” started",
                               level="success")
        return experiments_mod.get_experiment(app, exp_id)

    @r.get("/experiments/{experiment_id}/report")
    def experiment_report(experiment_id: int) -> dict:
        from .. import experiments as experiments_mod

        report = experiments_mod.experiment_report(rt.app(), experiment_id)
        if report is None:
            raise HTTPException(404, f"experiment {experiment_id} not found")
        return report

    class ConcludeIn(BaseModel):
        conclusion: str

    @r.post("/experiments/{experiment_id}/conclude")
    def conclude_experiment(experiment_id: int, body: ConcludeIn) -> dict:
        from .. import experiments as experiments_mod

        app = rt.app()
        out = experiments_mod.conclude_experiment(app, experiment_id, body.conclusion)
        if out is None:
            raise HTTPException(404, f"experiment {experiment_id} not found")
        db_module.log_activity(app.conn, "experiment",
                               f"Experiment “{out['name']}” concluded")
        return out

    # ------------------------------------------------------------------ #
    # Review feed (mobile) + owner-taste learning
    # ------------------------------------------------------------------ #
    def _character_out(app, character_id: Optional[int]) -> Optional[dict]:
        if not character_id:
            return None
        row = db_module.query_one(app.conn, "SELECT * FROM characters WHERE id = ?",
                                  (character_id,))
        if not row:
            return None
        img = media_url(row["reference_image"]) if row["reference_image"] else None
        return {"id": row["id"], "name": row["name"], "role": row["role"],
                "image": img}

    def _review_item(app, row: dict, campaigns_by_id: dict) -> dict:
        out = content_out(row)
        sctx = out.get("strategy_context") or {}
        campaign = campaigns_by_id.get(row["product_id"]) or {}
        from .. import taste as taste_mod

        out["campaign"] = {
            "id": row["product_id"],
            "name": campaign.get("name") or row["product_id"],
            "kind": campaign.get("kind") or "product",
            "upload_profile": campaign.get("upload_profile"),
        }
        out["character"] = _character_out(app, sctx.get("character_id"))
        out["experiment"] = sctx.get("experiment")
        out["review"] = taste_mod.get_review(app, row["id"])
        return out

    @r.get("/review/feed")
    def review_feed(campaign: Optional[str] = None, kind: str = "video",
                    limit: int = 50) -> list[dict]:
        """The phone feed: unposted drafts/approved content with media, soonest-
        scheduled first, then freshest. kind="video" (default) or "all"."""
        app = rt.app()
        campaigns_by_id = {p["id"]: dict(p) for p in store.list_products(app.conn)}
        where = ["c.status IN ('draft', 'approved')",
                 "c.media_paths IS NOT NULL", "c.media_paths != '[]'"]
        params: list[Any] = []
        if kind == "video":
            where.append("c.content_type = 'video'")
        if campaign:
            where.append("c.product_id = ?")
            params.append(campaign)
        rows = db_module.query(
            app.conn,
            f"""
            SELECT c.* FROM content c
            WHERE {' AND '.join(where)}
            ORDER BY c.scheduled_at IS NULL, c.scheduled_at, c.created_at DESC
            LIMIT ?
            """, params + [int(limit)])
        return [_review_item(app, dict(row), campaigns_by_id) for row in rows]

    @r.get("/review/account/{product_id}")
    def review_account(product_id: str) -> dict:
        """The tap-into-the-account profile view: campaign identity, its
        characters, and its past + upcoming posts like a profile grid."""
        app = rt.app()
        product = get_product_or_404(product_id)
        campaigns_by_id = {product_id: dict(product)}
        rows = db_module.query(
            app.conn,
            """
            SELECT c.* FROM content c
            WHERE c.product_id = ? AND c.media_paths IS NOT NULL
              AND c.media_paths != '[]' AND c.status != 'rejected'
            ORDER BY CASE c.status WHEN 'posted' THEN 1 ELSE 0 END,
                     COALESCE(c.posted_at, c.scheduled_at, c.created_at) DESC
            LIMIT 60
            """, (product_id,))
        items = []
        for row in rows:
            item = _review_item(app, dict(row), campaigns_by_id)
            post = db_module.query_one(
                app.conn, "SELECT id FROM posts WHERE content_id = ? "
                          "ORDER BY posted_at DESC LIMIT 1", (row["id"],))
            item["latest_metric"] = store.latest_metric(app.conn, post["id"]) if post else None
            items.append(item)
        chars = [dict(c) for c in db_module.query(
            app.conn, "SELECT * FROM characters WHERE product_id = ? AND active = 1",
            (product_id,))]
        for c in chars:
            c["image"] = media_url(c["reference_image"]) if c.get("reference_image") else None
            c.pop("reference_image", None)
        stats = db_module.query_one(
            app.conn,
            """
            SELECT (SELECT COUNT(*) FROM posts p JOIN content c ON c.id = p.content_id
                    WHERE c.product_id = ?) AS posts,
                   (SELECT AVG(rating) FROM reviews WHERE product_id = ? AND rating IS NOT NULL)
                    AS avg_rating,
                   (SELECT COUNT(*) FROM reviews WHERE product_id = ? AND rating IS NOT NULL)
                    AS rated
            """, (product_id, product_id, product_id))
        return {"campaign": product_out(product), "characters": chars,
                "stats": dict(stats) if stats else {}, "items": items}

    class ReviewIn(BaseModel):
        rating: Optional[int] = Field(default=None, ge=1, le=10)
        feedback: Optional[str] = None
        action: Optional[str] = None          # "approve" | "reject"
        watch_seconds: Optional[float] = None
        video_duration: Optional[float] = None
        replays: Optional[int] = None
        completed: Optional[bool] = None

    @r.post("/review/{content_id}")
    def submit_review(content_id: int, body: ReviewIn) -> dict:
        """Everything the phone does lands here — rating slide, note, approve/
        reject, watch telemetry. Persisted immediately; learning runs as a
        background job and streams its takeaways over SSE."""
        from datetime import datetime, timezone

        from .. import taste as taste_mod

        app = rt.app()
        row = get_content_or_404(content_id)
        if body.action and body.action not in ("approve", "reject"):
            raise HTTPException(400, "action must be approve or reject")

        review, first_rating = taste_mod.record_review(
            app, row, rating=body.rating, feedback=body.feedback,
            action=body.action, watch_seconds=body.watch_seconds,
            video_duration=body.video_duration, replays=body.replays,
            completed=body.completed)

        # Apply the approval decision through the same paths the Studio uses.
        if body.action == "approve" and row["status"] != "posted":
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if row.get("expires_at") and str(row["expires_at"]) <= now:
                raise HTTPException(400, "trend window closed — reject it instead")
            already = row["status"] == "approved"
            store.set_content_status(app.conn, content_id, "approved", approved_at=now)
            db_module.log_activity(app.conn, "approve",
                                   f"Approved content #{content_id} (review app)",
                                   product_id=row["product_id"], content_id=content_id,
                                   level="success")
            if not already:
                from .. import characters as characters_mod

                try:
                    characters_mod.on_content_approved(app, row)
                except Exception:
                    pass
            rt.bus.publish("content", {"id": content_id, "status": "approved"})
        elif body.action == "reject" and row["status"] != "posted":
            # The note also lands in rejection_feedback so the writer's legacy
            # "don't repeat this" path keeps working.
            store.set_content_status(app.conn, content_id, "rejected",
                                     rejection_feedback=(body.feedback or "").strip() or None)
            db_module.log_activity(app.conn, "reject",
                                   f"Rejected content #{content_id} (review app)",
                                   product_id=row["product_id"], content_id=content_id)
            rt.bus.publish("content", {"id": content_id, "status": "rejected"})

        # Learning job — only when there's a new signal worth processing.
        job_id = None
        has_note = bool((body.feedback or "").strip())
        if first_rating or has_note:
            note = (body.feedback or "").strip() or None

            def _run(app, llm, job, report):
                from .. import scientist as scientist_mod
                from .. import taste as taste_mod2

                report(0.2, "Interpreting your feedback…")
                out = taste_mod2.process_review(app, llm, content_id,
                                                new_rating=first_rating,
                                                new_feedback=note)
                product = store.get_product(app.conn, row["product_id"])
                report(0.7, "Scientist checking experiments…")
                sci = None
                try:
                    sci = scientist_mod.run(app, llm, product)
                except Exception:
                    sci = None
                if sci and sci.get("notebook_entry"):
                    out["learned"].append(f"Scientist: {sci['notebook_entry']}")
                rt.bus.publish("review", {"content_id": content_id,
                                          "learned": out["learned"]})
                return out

            job = rt.jobs.submit("learn", f"Learn from review #{content_id}", _run,
                                 product_id=row["product_id"])
            job_id = job.id

        return {"review": taste_mod.get_review(app, content_id), "job_id": job_id,
                "status": store.get_content(app.conn, content_id)["status"]}

    @r.get("/review/insights")
    def review_insights(campaign: Optional[str] = None) -> dict:
        """Everything the Taste dashboard shows: the rating trend, each reviewed
        video with what the AI took away, the taste profile, the experiment lab,
        and the scientist's notebook."""
        from .. import scientist as scientist_mod
        from .. import taste as taste_mod

        app = rt.app()
        campaigns_by_id = {p["id"]: dict(p) for p in store.list_products(app.conn)}
        where = "WHERE r.product_id = ?" if campaign else ""
        params: list[Any] = [campaign] if campaign else []
        review_rows = db_module.query(
            app.conn,
            f"""
            SELECT r.*, c.caption, c.hook, c.platform AS c_platform, c.content_type,
                   c.media_paths, c.status, c.strategy_context, c.product_id AS c_product
            FROM reviews r JOIN content c ON c.id = r.content_id
            {where} ORDER BY r.updated_at DESC LIMIT 60
            """, params)
        reviews = []
        for row in review_rows:
            d = dict(row)
            media = []
            for p in db_module.loads(d.pop("media_paths"), []) or []:
                url = media_url(p)
                if url:
                    kind = "video" if p.endswith((".mp4", ".mov", ".webm")) else "image"
                    media.append({"url": url, "kind": kind})
            sctx = db_module.loads(d.pop("strategy_context"), {}) or {}
            learning = db_module.query_one(
                app.conn, "SELECT payload, created_at FROM review_learnings "
                          "WHERE content_id = ? ORDER BY created_at DESC LIMIT 1",
                (d["content_id"],))
            campaign_row = campaigns_by_id.get(d["product_id"]) or {}
            reviews.append({
                **d, "media": media,
                "campaign_name": campaign_row.get("name") or d["product_id"],
                "strategy": sctx.get("strategy"), "experiment": sctx.get("experiment"),
                "learning": db_module.loads(learning["payload"], {}) if learning else None,
                "learned_at": learning["created_at"] if learning else None,
            })

        lessons_where = "WHERE product_id = ?" if campaign else ""
        lessons = [dict(x) for x in db_module.query(
            app.conn,
            f"SELECT id, product_id, aspect, polarity, directive, scope_platform, "
            f"scope_strategy, scope_content_type, confidence, support, contradictions, "
            f"status, retired_reason, updated_at, created_at FROM taste_lessons "
            f"{lessons_where} ORDER BY status = 'retired', confidence DESC LIMIT 80",
            params)]

        exp_where = "WHERE product_id = ?" if campaign else ""
        experiments = []
        for x in db_module.query(
                app.conn,
                f"SELECT * FROM creative_experiments {exp_where} "
                f"ORDER BY status = 'concluded', started_at DESC LIMIT 30", params):
            exp = scientist_mod._exp_out(x)
            exp["stats"] = scientist_mod.variant_stats(app, exp)
            experiments.append(exp)

        nb_where = "WHERE product_id = ?" if campaign else ""
        notebook = [dict(x) for x in db_module.query(
            app.conn,
            f"SELECT * FROM lab_notebook {nb_where} ORDER BY created_at DESC LIMIT 25",
            params)]
        for n in notebook:
            n["payload"] = db_module.loads(n.get("payload"), {})

        totals = db_module.query_one(
            app.conn,
            f"""
            SELECT COUNT(rating) AS rated, AVG(rating) AS avg_rating,
                   AVG(CASE WHEN COALESCE(rated_at, created_at) >=
                       datetime('now', '-14 days') THEN rating END) AS avg_rating_14d
            FROM reviews {'WHERE product_id = ?' if campaign else ''}
            """, params)
        return {
            "trend": taste_mod.rating_trend(app, campaign),
            "reviews": reviews,
            "lessons": lessons,
            "experiments": experiments,
            "notebook": notebook,
            "aspects": taste_mod.aspect_report(app, campaign) if campaign else [],
            "totals": dict(totals) if totals else {},
        }

    # ------------------------------------------------------------------ #
    # Jobs / events / autopilot
    # ------------------------------------------------------------------ #
    @r.get("/jobs")
    def jobs(limit: int = 25) -> list[dict]:
        return rt.jobs.recent(limit)

    @r.get("/jobs/{job_id}")
    def job_detail(job_id: str) -> dict:
        job = rt.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return job.to_dict()

    @r.get("/events")
    async def events(request: Request) -> StreamingResponse:
        q = rt.bus.subscribe()

        async def stream():
            import queue as _q

            import anyio

            # Private limiter: a sync generator would pin one token of the
            # shared 40-token thread pool per connection, starving the whole
            # API. abandon_on_cancel frees the worker on client disconnect.
            limiter = anyio.CapacityLimiter(1)
            try:
                yield "event: hello\ndata: {}\n\n"
                while True:
                    try:
                        event = await anyio.to_thread.run_sync(
                            lambda: q.get(timeout=15),
                            limiter=limiter, abandon_on_cancel=True)
                        yield f"data: {json.dumps(event)}\n\n"
                    except _q.Empty:
                        yield ": keepalive\n\n"
            finally:
                rt.bus.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @r.get("/autopilot")
    def autopilot() -> dict:
        return {"running": rt.autopilot.running,
                "started_at": rt.autopilot.started_at,
                "upcoming": rt.autopilot.upcoming()}

    @r.post("/autopilot/start")
    def autopilot_start() -> dict:
        rt.autopilot.start()
        return {"running": rt.autopilot.running}

    @r.post("/autopilot/stop")
    def autopilot_stop() -> dict:
        rt.autopilot.stop()
        return {"running": rt.autopilot.running}

    @r.post("/autopilot/run-once")
    def autopilot_run_once() -> dict:
        def _run(app, llm, job, report):
            from ..scheduler import engine

            report(0.1, "Trends…")
            engine.job_trends(app, llm)
            report(0.35, "Generating…")
            engine.job_generate(app, llm)
            if app.settings.approval.auto_approve:
                report(0.65, "Posting…")
                for platform in app.settings.enabled_platforms():
                    engine.job_post_platform(app, platform)
            report(0.85, "Analytics…")
            engine.job_collect_analytics(app)
            report(1.0, "Cycle complete")
            return {"ok": True}

        job = rt.jobs.submit("cycle", "Run one full cycle", _run)
        return {"job_id": job.id}

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    @r.get("/settings")
    def settings() -> dict:
        app = rt.app()
        raw = {}
        if app.paths.default_config.exists():
            raw = yaml.safe_load(app.paths.default_config.read_text()) or {}
        return {"settings": raw,
                "profile_username": app.settings.upload_post.profile_username}

    ALLOWED_SETTINGS_SECTIONS = {"llm", "media", "scheduling", "approval",
                                 "upload_post", "platforms", "trends", "humor",
                                 "learning"}

    class SettingsPatch(BaseModel):
        settings: dict[str, Any]

    @r.patch("/settings")
    def patch_settings(body: SettingsPatch) -> dict:
        app = rt.app()
        raw = {}
        if app.paths.default_config.exists():
            raw = yaml.safe_load(app.paths.default_config.read_text()) or {}
        for section, value in body.settings.items():
            if section not in ALLOWED_SETTINGS_SECTIONS:
                raise HTTPException(400, f"unknown settings section: {section}")
            if isinstance(value, dict) and isinstance(raw.get(section), dict):
                _deep_merge(raw[section], value)
            else:
                raw[section] = value
        # Validate BEFORE writing: a malformed value persisted to YAML would
        # crash Settings loading and brick every endpoint (and the CLI).
        try:
            Settings.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(400, f"invalid settings: {exc}")
        app.paths.default_config.write_text(yaml.safe_dump(raw, sort_keys=False))
        rt.reload()
        db_module.log_activity(app.conn, "settings", "Settings updated")
        # Autopilot schedule may have changed; restart it if it was running.
        if rt.autopilot.running:
            rt.autopilot.stop()
            rt.autopilot.start()
        return {"ok": True}

    @r.get("/connections")
    def connections() -> dict:
        """upload-post profile info: which social accounts are connected."""
        from ..posting.upload_post import UploadPostClient

        return UploadPostClient(rt.app()).profile_info()

    # ------------------------------------------------------------------ #
    # Clip / caption editor (EDL) — Contract 6 of the templates build
    # ------------------------------------------------------------------ #
    # Fonts are vendored OFL-only; family names must match what the renderer's
    # libass/Pillow burn resolves so the browser preview looks like the export.
    _FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    _FONT_FAMILIES = {
        "Montserrat-ExtraBold.ttf": "Montserrat ExtraBold",
        "Anton-Regular.ttf": "Anton",
        "BebasNeue-Regular.ttf": "Bebas Neue",
    }

    def media_url_for(app, path: str) -> Optional[str]:
        """Like media_url() but bound to a job thread's own App (no rt.app())."""
        try:
            rel = Path(path).resolve().relative_to(app.paths.media_dir.resolve())
            return f"/media/{rel.as_posix()}"
        except Exception:
            return None

    def edit_json_path(row: dict) -> Optional[Path]:
        """Locate this content's edit.json: content.edl_path, else next to media."""
        if row.get("edl_path"):
            return Path(row["edl_path"])
        for m in db_module.loads(row.get("media_paths"), []) or []:
            d = Path(m).parent
            if d.is_dir():
                return d / "edit.json"
        return None

    def caption_styles() -> list[dict]:
        """Every caption style preset (id + fields) for the editor's style picker
        and preview. Loaded fresh so config edits show up without a restart."""
        out = []
        sdir = rt.app().paths.config_dir / "caption_styles"
        if sdir.is_dir():
            for f in sorted(sdir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(f.read_text()) or {}
                except Exception:
                    data = {}
                data["id"] = f.stem
                out.append(data)
        return out

    def font_list() -> list[dict]:
        out = []
        if _FONTS_DIR.is_dir():
            for fn, family in _FONT_FAMILIES.items():
                if (_FONTS_DIR / fn).is_file():
                    out.append({"family": family, "url": f"/api/fonts/{fn}", "file": fn})
        return out

    @r.get("/edit/{content_id}")
    def edit_get(content_id: int) -> dict:
        from ..media import edl as edl_mod

        app = rt.app()
        row = get_content_or_404(content_id)
        ejp = edit_json_path(row)
        if not ejp or not ejp.is_file():
            raise HTTPException(
                404, f"content {content_id} has no editable EDL (edit.json) — "
                     "only auto-assembled clip videos are editable")
        try:
            edl_obj = edl_mod.load(ejp)
        except Exception as exc:
            raise HTTPException(400, f"edit.json is invalid: {exc}")
        edl_dir = ejp.parent
        # Preview video: a fast proxy first, else the captionless master, else the
        # content's final rendered video (captions burned — still previewable).
        media_urls: dict[str, Optional[str]] = {"proxy": None, "master": None, "video": None}
        for key, name in (("proxy", "proxy.mp4"), ("master", "master.mp4")):
            f = edl_dir / name
            if f.is_file():
                media_urls[key] = media_url(str(f))
        for m in db_module.loads(row.get("media_paths"), []) or []:
            if str(m).endswith((".mp4", ".mov", ".webm")):
                media_urls["video"] = media_url(m)
                break
        # Voiceover audio drives the waveform (caption-timing lane).
        audio_url = None
        for tr in edl_obj.audio:
            if tr.kind == "voiceover" and tr.src:
                ap = Path(tr.src)
                ap = ap if ap.is_absolute() else (edl_dir / ap)
                if ap.is_file():
                    audio_url = media_url(str(ap))
                    break
        return {
            "content_id": content_id,
            "platform": row["platform"],
            "content_type": row["content_type"],
            "status": row["status"],
            "edl": edl_obj.model_dump(by_alias=True),
            "media_urls": media_urls,
            "audio_url": audio_url,
            "styles": caption_styles(),
            "fonts": font_list(),
            "sfx_available": (app.paths.config_dir / "sfx_library.yaml").is_file(),
        }

    @r.post("/edit/{content_id}")
    def edit_save(content_id: int, body: dict) -> dict:
        from ..media import edl as edl_mod

        app = rt.app()
        row = get_content_or_404(content_id)
        if row["status"] == "posted":
            raise HTTPException(400, "content is already posted — its EDL is locked")
        try:
            edl_obj = edl_mod.EDL.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(400, f"invalid EDL: {exc}")
        except Exception as exc:  # pydantic raises ValueError from validators
            raise HTTPException(400, f"invalid EDL: {exc}")
        ejp = edit_json_path(row)
        if not ejp:
            raise HTTPException(400, "content has no media directory to store the EDL")
        edl_mod.save(edl_obj, ejp)
        if row.get("edl_path") != str(ejp):
            store.update_content(app.conn, content_id, edl_path=str(ejp))
        db_module.log_activity(app.conn, "edit", f"Edited EDL for #{content_id}",
                               product_id=row["product_id"], content_id=content_id)
        return {"ok": True, "edl_path": str(ejp)}

    @r.post("/edit/{content_id}/proxy")
    def edit_proxy(content_id: int) -> dict:
        row = get_content_or_404(content_id)

        def _run(app, llm, job, report):
            from ..media import edl as edl_mod
            from ..media import render as render_mod

            report(0.1, "Loading EDL…")
            r2 = store.get_content(app.conn, content_id)
            ejp = edit_json_path(r2)
            if not ejp or not ejp.is_file():
                raise RuntimeError("no edit.json for this content")
            edl_obj = edl_mod.load(ejp)
            out = ejp.parent / "proxy.mp4"
            report(0.3, "Rendering 480p preview…")
            render_mod.render_edl(app, edl_obj, ejp.parent, out, proxy=True)
            report(1.0, "Preview ready")
            return {"proxy_url": media_url_for(app, str(out)), "content_id": content_id}

        job = rt.jobs.submit("edit", f"Re-cut proxy #{content_id}", _run,
                             product_id=row["product_id"])
        return {"job_id": job.id}

    @r.post("/edit/{content_id}/render")
    def edit_render(content_id: int) -> dict:
        row = get_content_or_404(content_id)
        if row["status"] == "posted":
            raise HTTPException(400, "content is already posted — cannot re-render")

        def _run(app, llm, job, report):
            from ..media import edl as edl_mod
            from ..media import render as render_mod

            report(0.1, "Loading EDL…")
            r2 = store.get_content(app.conn, content_id)
            ejp = edit_json_path(r2)
            if not ejp or not ejp.is_file():
                raise RuntimeError("no edit.json for this content")
            edl_obj = edl_mod.load(ejp)
            out = ejp.parent / f"{content_id}_{r2['platform']}_video.mp4"
            report(0.3, "Rendering final 1080×1920…")
            render_mod.render_edl(app, edl_obj, ejp.parent, out, proxy=False)
            # Swap the content's media to the freshly rendered file; it flows back
            # into the normal approve/post path from here.
            store.update_content(app.conn, content_id, media_paths=[str(out)])
            report(1.0, "Final render complete")
            rt.bus.publish("content", {"id": content_id, "status": r2["status"]})
            return {"video_url": media_url_for(app, str(out)), "content_id": content_id}

        job = rt.jobs.submit("render", f"Render final #{content_id}", _run,
                             product_id=row["product_id"])
        return {"job_id": job.id}

    @r.get("/sfx")
    def sfx_library() -> list[dict]:
        """The curated SFX library (Contract 7). Degrades to [] when the
        parallel SFX engine hasn't shipped its manifest yet — the editor then
        just shows no library, but SFX cues already in an EDL stay editable."""
        app = rt.app()
        manifest = app.paths.config_dir / "sfx_library.yaml"
        if not manifest.is_file():
            return []
        try:
            data = yaml.safe_load(manifest.read_text()) or {}
        except Exception:
            return []
        # Schema is owned by the parallel SFX engine (Contract 7). Accept its
        # actual shape (top-level `effects`, per-item `family`) as well as a
        # plain `sfx` list — and tolerate either without crashing.
        items = None
        default_gain = 0
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            default_gain = (data.get("defaults") or {}).get("gain_db", 0)
            for key in ("effects", "sfx", "library", "items"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
        if not isinstance(items, list):
            return []
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            slug = str(it.get("slug") or "").strip()
            if not slug:
                continue
            cached = app.paths.data_dir / "assets" / "sfx" / f"{slug}.mp3"
            out.append({
                "slug": slug,
                "name": it.get("name") or slug.replace("_", " "),
                "category": it.get("category") or it.get("family"),
                "purpose": it.get("purpose"),
                "duration": it.get("duration"),
                "gain_db": it.get("gain_db", default_gain),
                "src": str(cached) if cached.is_file() else None,
                "url": media_url_for(app, str(cached)) if cached.is_file() else None,
            })
        return out

    @r.get("/fonts/{name}")
    def font_file(name: str) -> FileResponse:
        """Serve a vendored caption font so the browser preview @font-face uses
        the exact same file the burn does."""
        if name not in _FONT_FAMILIES or "/" in name or "\\" in name:
            raise HTTPException(404, "unknown font")
        path = _FONTS_DIR / name
        if not path.is_file():
            raise HTTPException(404, "font file missing")
        return FileResponse(str(path), media_type="font/ttf",
                            headers={"Cache-Control": "public, max-age=86400"})

    return r


def _deep_merge(base: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
