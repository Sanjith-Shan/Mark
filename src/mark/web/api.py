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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import db as db_module
from .. import store
from ..config import ProductConfig
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
        return out

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

    @r.get("/campaigns")
    def campaigns() -> list[dict]:
        return [product_out(p) for p in store.list_products(rt.app().conn)]

    @r.post("/campaigns")
    def create_campaign(body: CampaignIn) -> dict:
        app = rt.app()
        pid = body.id or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")
        if not pid:
            raise HTTPException(400, "campaign needs a name")
        cfg = ProductConfig(
            id=pid, name=body.name, description=body.description,
            target_audience=body.target_audience, brand_voice=body.brand_voice,
            website_url=body.website_url, platforms=body.platforms,
            posting_cadence=body.posting_cadence or {p: 1 for p in body.platforms},
        )
        store.upsert_product(app.conn, cfg, active=False)
        store.update_product(app.conn, pid,
                             active=1 if body.active else 0, archived=0,
                             platform_options=body.platform_options)
        # Keep a YAML copy alongside (same as the CLI flow) for portability.
        try:
            yaml_path = app.paths.products_dir / f"{pid}.yaml"
            yaml_path.write_text(yaml.safe_dump(
                {**cfg.model_dump(), "platform_options": body.platform_options},
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

    @r.patch("/campaigns/{product_id}")
    def patch_campaign(product_id: str, body: CampaignPatch) -> dict:
        app = rt.app()
        get_product_or_404(product_id)
        fields: dict[str, Any] = {}
        for k in ("name", "description", "target_audience", "brand_voice",
                  "website_url", "platforms", "posting_cadence", "platform_options"):
            v = getattr(body, k)
            if v is not None:
                fields[k] = v
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
        rows = store.list_content(rt.app().conn, status=status,
                                  product_id=campaign, limit=limit)
        if platform:
            rows = [x for x in rows if x["platform"] == platform]
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
        store.set_content_status(
            app.conn, content_id, "approved",
            approved_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        db_module.log_activity(app.conn, "approve", f"Approved content #{content_id}",
                               product_id=row["product_id"], content_id=content_id,
                               level="success")
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

    @r.get("/insights")
    def insights(campaign: Optional[str] = None) -> dict:
        app = rt.app()
        product = store.resolve_product(app.conn, campaign)
        if not product:
            return {"insights": None, "bandit": [], "winners": 0}
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
                                 "upload_post", "platforms"}

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

    return r


def _deep_merge(base: dict, patch: dict) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
