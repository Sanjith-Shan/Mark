"""APScheduler engine — the autonomous heartbeat.

Jobs (all driven by the crons in config/default.yaml):
  * generate   — daily: create the day's drafts per product cadence
  * post       — per platform optimal-time, with jitter, respecting daily caps
  * analytics  — every few hours: collect metrics
  * trends     — twice daily: refresh trend cache
  * feedback   — weekly: run the self-improvement loop

Every job is wrapped so a failure logs and is swallowed — the scheduler never
crashes. `run_once()` fires generate→post→analytics→trends once (handy for an
external cron / smoke test); `start()` runs the long-lived scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from .. import db as db_module
from .. import store
from ..app import App
from ..llm import LLM

log = logging.getLogger("mark.scheduler")


# --------------------------------------------------------------------------- #
# Safe job wrapper
# --------------------------------------------------------------------------- #
def _safe(fn: Callable, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - jobs must never crash the scheduler
        log.exception("job %s failed: %s", getattr(fn, "__name__", fn), exc)


def _active_products(app: App) -> list[dict]:
    return [dict(r) for r in db_module.query(
        app.conn,
        "SELECT * FROM products WHERE active = 1 AND COALESCE(archived, 0) = 0")]


def _all_products(app: App) -> list[dict]:
    return store.list_products(app.conn)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def job_generate(app: App, llm: LLM) -> None:
    from .. import pipeline

    for product in _active_products(app):
        cadence = db_module.loads(product["posting_cadence"], {}) or {}
        platforms = [p for p in pipeline.product_platforms(product)
                     if app.settings.platform(p).enabled]
        for platform in platforms:
            count = max(1, int(cadence.get(platform, 1)))
            _safe(pipeline.generate_all, app, llm, product, [platform], count)
        log.info("generated drafts for %s", product["id"])


def job_post_platform(app: App, platform: str) -> None:
    from ..posting import manager

    cap = app.settings.platform(platform).max_posts_per_day
    if _posts_today(app, platform) >= cap:
        return
    # Rotate across running campaigns fairly: pick the campaign that has posted
    # least recently on this platform, oldest approved draft first.
    row = db_module.query_one(
        app.conn,
        "SELECT c.* FROM content c JOIN products pr ON pr.id = c.product_id "
        "WHERE c.status = 'approved' AND c.platform = ? "
        "AND (c.expires_at IS NULL OR c.expires_at > datetime('now')) "
        "AND pr.active = 1 AND COALESCE(pr.archived, 0) = 0 "
        "ORDER BY c.created_at ASC LIMIT 1", (platform,))
    if not row:
        return
    manager.post_content(app, dict(row))
    log.info("posted content %s to %s", row["id"], platform)


def job_collect_analytics(app: App) -> None:
    from ..analytics import collector

    for product in _all_products(app):
        _safe(collector.collect, app, product["id"])
    log.info("collected analytics")


def job_trends(app: App, llm: LLM) -> None:
    from ..trends import aggregator

    for product in _active_products(app):
        _safe(aggregator.refresh, app, llm, product)
        # Fast path: if a hot trend just appeared and auto_react is on, draft
        # trend-riding content immediately instead of waiting for tomorrow's cron.
        if app.settings.trends.auto_react:
            _safe(aggregator.react, app, llm, product)
    _safe(aggregator.expire_stale_content, app)
    log.info("refreshed trends")


def job_trends_fast(app: App, llm: LLM) -> None:
    """The 30-minute pulse: free, hours-fresh sources only (Reddit rising,
    Bluesky trending, Google RSS). Auto-react fires from here too — this is
    where detection→live in 2-6 hours actually happens."""
    from ..trends import aggregator

    for product in _active_products(app):
        _safe(aggregator.refresh_fast, app, llm, product)
        if app.settings.trends.auto_react:
            _safe(aggregator.react, app, llm, product)
    _safe(aggregator.expire_stale_content, app)
    log.info("fast trend poll done")


def job_post_scheduled(app: App) -> None:
    """Post approved content whose explicit `scheduled_at` time has arrived.
    User-scheduled items bypass optimal-time slots but still respect daily caps."""
    from ..posting import manager

    rows = db_module.query(
        app.conn,
        "SELECT c.* FROM content c JOIN products pr ON pr.id = c.product_id "
        "WHERE c.status = 'approved' AND c.scheduled_at IS NOT NULL "
        "AND c.scheduled_at <= datetime('now') "
        "AND (c.expires_at IS NULL OR c.expires_at > datetime('now')) "
        "AND pr.active = 1 AND COALESCE(pr.archived, 0) = 0 "
        "ORDER BY c.scheduled_at ASC")
    for row in rows:
        platform = row["platform"]
        if _posts_today(app, platform) >= app.settings.platform(platform).max_posts_per_day:
            continue
        _safe(manager.post_content, app, dict(row))
        log.info("posted scheduled content %s to %s", row["id"], platform)


def job_feedback(app: App, llm: LLM) -> None:
    from ..learning import feedback

    for product in _active_products(app):
        _safe(feedback.run, app, llm, product)
    log.info("ran feedback loop")


def _posts_today(app: App, platform: str) -> int:
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM posts WHERE platform = ? "
        "AND date(posted_at, 'localtime') = date('now', 'localtime')", (platform,))
    return row["n"] if row else 0


# --------------------------------------------------------------------------- #
# Scheduler assembly
# --------------------------------------------------------------------------- #
def build_scheduler(app: App, llm: LLM, *, blocking: bool = True,
                    app_factory: Optional[Callable[[], App]] = None):
    """Assemble the scheduler.

    blocking=True (CLI `mark run`) uses a BlockingScheduler and the given app.
    blocking=False (web autopilot) uses a BackgroundScheduler; pass app_factory
    so each job run gets its own App/DB connection (jobs run in worker threads).
    """
    from apscheduler.triggers.cron import CronTrigger

    # APScheduler's default misfire_grace_time is 1 second — on a laptop that
    # sleeps through a cron fire time, the run would be silently discarded.
    # A 1-hour grace window lets a late wakeup still run each job once;
    # coalesce collapses multiple missed runs into one.
    job_defaults = {"misfire_grace_time": 3600, "coalesce": True}
    if blocking:
        from apscheduler.schedulers.blocking import BlockingScheduler

        sched = BlockingScheduler(timezone=app.settings.scheduling.timezone,
                                  job_defaults=job_defaults)
    else:
        from apscheduler.schedulers.background import BackgroundScheduler

        sched = BackgroundScheduler(timezone=app.settings.scheduling.timezone,
                                    job_defaults=job_defaults)

    tz = app.settings.scheduling.timezone
    sc = app.settings.scheduling

    def _job(fn, *, needs_llm: bool = False, extra_args: tuple = ()):
        """Wrap a job so it acquires (and disposes) its own App when a factory
        is provided — required for cross-thread SQLite safety."""
        def run() -> None:
            if app_factory is not None:
                a = app_factory()
                try:
                    args = (a, LLM(a)) if needs_llm else (a,)
                    _safe(fn, *args, *extra_args)
                finally:
                    a.close()
            else:
                args = (app, llm) if needs_llm else (app,)
                _safe(fn, *args, *extra_args)
        return run

    sched.add_job(_job(job_generate, needs_llm=True),
                  CronTrigger.from_crontab(sc.content_generation_cron, timezone=tz),
                  id="generate", name="generate drafts")
    sched.add_job(_job(job_collect_analytics),
                  CronTrigger.from_crontab(sc.analytics_collection_cron, timezone=tz),
                  id="analytics", name="collect analytics")
    sched.add_job(_job(job_trends, needs_llm=True),
                  CronTrigger.from_crontab(sc.trend_monitoring_cron, timezone=tz),
                  id="trends", name="refresh trends")
    sched.add_job(_job(job_feedback, needs_llm=True),
                  CronTrigger.from_crontab(sc.feedback_loop_cron, timezone=tz),
                  id="feedback", name="feedback loop")

    # User-scheduled posts: check every 5 minutes so `scheduled_at` is honored
    # within a few minutes of the chosen time.
    from apscheduler.triggers.interval import IntervalTrigger

    sched.add_job(_job(job_post_scheduled), IntervalTrigger(minutes=5, timezone=tz),
                  id="post-scheduled", name="post user-scheduled content")

    # Fast trend pulse (free sources only) — real-time trend adaptation.
    fast_min = max(10, int(getattr(app.settings.trends, "fast_poll_minutes", 30)))
    sched.add_job(_job(job_trends_fast, needs_llm=True),
                  IntervalTrigger(minutes=fast_min, timezone=tz),
                  id="trends-fast", name="fast trend poll")

    # One posting job per (platform, optimal_time), with ± jitter to avoid bot
    # patterns and to spread posts out.
    jitter = max(0, int(sc.posting_jitter_minutes)) * 60
    for platform in app.settings.enabled_platforms():
        for t in app.settings.platform(platform).optimal_times:
            hour, minute = _parse_hhmm(t)
            sched.add_job(
                _job(job_post_platform, extra_args=(platform,)),
                CronTrigger(hour=hour, minute=minute, timezone=tz, jitter=jitter),
                id=f"post-{platform}-{t}", name=f"post {platform} @ {t}",
            )
    return sched


def _parse_hhmm(t: str) -> tuple[int, int]:
    parts = t.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def run_once(app: App, llm: LLM) -> None:
    """Fire the core jobs once (useful for external cron or a smoke test)."""
    _safe(job_trends, app, llm)
    _safe(job_generate, app, llm)
    if app.settings.approval.auto_approve:
        for platform in app.settings.enabled_platforms():
            _safe(job_post_platform, app, platform)
    _safe(job_collect_analytics, app)


def upcoming(app: App, llm: LLM, limit: int = 12) -> list[dict]:
    """Next run times for all jobs (without starting the scheduler)."""
    sched = build_scheduler(app, llm)
    out = []
    for job in sched.get_jobs():
        nxt = job.trigger.get_next_fire_time(None, datetime.now(_tz(app)))
        out.append({"id": job.id, "name": job.name,
                    "next": nxt.strftime("%Y-%m-%d %H:%M") if nxt else "—"})
    out.sort(key=lambda x: x["next"])
    return out[:limit]


def _tz(app: App):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(app.settings.scheduling.timezone)
    except Exception:
        return None
