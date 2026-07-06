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
    from .. import monitor, pipeline

    if monitor.generation_frozen(app):
        log.warning("generation frozen (daily spend cap) — skipping")
        return
    for product in _active_products(app):
        cadence = db_module.loads(product["posting_cadence"], {}) or {}
        # Only platforms actually present in config get drafts: an unknown
        # platform would generate forever with no posting job to drain it.
        platforms = [p for p in pipeline.product_platforms(product)
                     if p in app.settings.platforms
                     and app.settings.platform(p).enabled]
        for platform in platforms:
            count = int(cadence.get(platform, 1))
            if count <= 0:
                continue  # cadence 0 = platform deliberately quiet
            if monitor.is_paused(app, product["id"], platform):
                continue  # collapse cool-down: don't stack drafts either
            # Backlog guard: generating faster than posting just queues stale
            # content. Skip when the unposted pile is already 3 days of cadence.
            row = db_module.query_one(
                app.conn,
                "SELECT COUNT(*) AS n FROM content WHERE product_id = ? AND platform = ? "
                "AND status IN ('draft', 'approved')", (product["id"], platform))
            if row and row["n"] >= max(3, count * 3):
                log.info("backlog guard: %s/%s has %s unposted items — skipping",
                         product["id"], platform, row["n"])
                continue
            _safe(pipeline.generate_all, app, llm, product, [platform], count)
        log.info("generated drafts for %s", product["id"])


def _slot_preferred(app: App, product_id: str, platform: str,
                    current_slot: Optional[str]) -> bool:
    """Should this campaign's post go out at THIS optimal-time slot?

    The post_time bandit arm was previously write-only — learned timing never
    changed behavior because posting slots were pure cron. Now: sample the
    bandit's post_time preference; if it prefers a LATER slot today, hold the
    post for that slot. An earlier (already passed) preference posts now —
    holding for tomorrow would starve throughput.
    """
    if not current_slot:
        return True
    times = app.settings.platform(platform).optimal_times or []
    if len(times) <= 1:
        return True
    try:
        from ..learning import bandit

        pick = bandit.recommend(app, product_id, platform).get("post_time")
    except Exception:
        return True
    if not pick or pick == current_slot or pick not in times:
        return True
    # Post now unless the preferred slot is still ahead of us today.
    return not (pick > current_slot)


def job_post_platform(app: App, platform: str, slot: Optional[str] = None) -> None:
    from .. import monitor
    from ..posting import manager

    # Fair rotation across campaigns: order candidates by how recently their
    # campaign last posted on this platform (never-posted first), then oldest
    # draft first. Caps and pauses are evaluated PER CANDIDATE because each
    # campaign may post through its own account (multi-account test lab).
    # scheduled_at IS NULL: user-scheduled content belongs exclusively to
    # job_post_scheduled — otherwise it would post early at the next optimal
    # slot (and could double-post via a race between the two jobs).
    rows = db_module.query(
        app.conn,
        "SELECT c.*, (SELECT MAX(p2.posted_at) FROM posts p2 "
        "  JOIN content c2 ON c2.id = p2.content_id "
        "  WHERE c2.product_id = c.product_id AND p2.platform = c.platform) AS last_post "
        "FROM content c JOIN products pr ON pr.id = c.product_id "
        "WHERE c.status = 'approved' AND c.platform = ? "
        "AND c.scheduled_at IS NULL "
        "AND (c.expires_at IS NULL OR c.expires_at > datetime('now')) "
        "AND pr.active = 1 AND COALESCE(pr.archived, 0) = 0 "
        "ORDER BY COALESCE(last_post, '') ASC, c.created_at ASC LIMIT 20", (platform,))
    cap = app.settings.platform(platform).max_posts_per_day
    for row in rows:
        if monitor.is_paused(app, row["product_id"], platform):
            continue
        if manager.posts_today(app, platform, product_id=row["product_id"]) >= cap:
            continue
        if not _slot_preferred(app, row["product_id"], platform, slot):
            continue  # the bandit prefers a later slot today — hold for it
        manager.post_content(app, dict(row))
        log.info("posted content %s to %s", row["id"], platform)
        return


def job_collect_analytics(app: App, llm: Optional[LLM] = None) -> None:
    from .. import monitor
    from ..analytics import collector
    from ..learning import feedback

    for product in _all_products(app):
        _safe(collector.collect, app, product["id"])
    # Fresh comments just landed — draft in-voice replies for one-tap approval
    # (author-reply velocity is a major ranking signal on every platform).
    if llm is not None:
        from .. import replies

        for product in _active_products(app):
            _safe(replies.draft_replies, app, llm, product)
    # Rewards are idempotent (each post credited exactly once at maturity), so
    # the bandit learns every few hours instead of waiting for the weekly pass.
    for product in _active_products(app):
        _safe(feedback.apply_rewards, app, product["id"])
        _safe(monitor.check_engagement_collapse, app, product)
    _safe(monitor.check_spend, app)
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
    from .. import humor_radar
    from ..trends import aggregator

    for product in _active_products(app):
        _safe(aggregator.refresh_fast, app, llm, product)
        if app.settings.trends.auto_react:
            _safe(aggregator.react, app, llm, product)
    # Humor radar rides the same pulse: memes move on the same clock as trends.
    if app.settings.humor_radar.enabled:
        _safe(humor_radar.refresh, app, llm)
        for product in _active_products(app):
            _safe(humor_radar.auto_draft, app, llm, product)
    _safe(aggregator.expire_stale_content, app)
    _safe(aggregator.purge_old_trends, app)
    log.info("fast trend poll done")


def job_post_scheduled(app: App) -> None:
    """Post approved content whose explicit `scheduled_at` time has arrived.
    User-scheduled items bypass optimal-time slots but still respect daily caps.
    scheduled_at may arrive as ISO ('2026-07-05T14:00') — normalize the 'T' so
    the lexicographic comparison against datetime('now') is valid."""
    from ..posting import manager

    rows = db_module.query(
        app.conn,
        "SELECT c.* FROM content c JOIN products pr ON pr.id = c.product_id "
        "WHERE c.status = 'approved' AND c.scheduled_at IS NOT NULL "
        "AND replace(c.scheduled_at, 'T', ' ') <= datetime('now') "
        "AND (c.expires_at IS NULL OR c.expires_at > datetime('now')) "
        "AND pr.active = 1 AND COALESCE(pr.archived, 0) = 0 "
        "ORDER BY c.scheduled_at ASC")
    for row in rows:
        platform = row["platform"]
        if manager.posts_today(app, platform, product_id=row["product_id"]) \
                >= app.settings.platform(platform).max_posts_per_day:
            continue
        _safe(manager.post_content, app, dict(row))
        log.info("posted scheduled content %s to %s", row["id"], platform)


# Winners on a source platform get a second life on lagged platforms — the
# platform-lag arbitrage from the research (Reels trends run 3-7 days behind
# TikTok; every TikTok winner deserves a Reels/Shorts retry, X winners a
# Threads echo).
CASCADE_LADDER = {"tiktok": ["instagram", "youtube"], "x": ["threads"]}


def _already_cascaded(app: App, product_id: str, source_id: int, target: str) -> bool:
    """True if this winner already has an adaptation on the target platform.
    Candidates are narrowed with LIKE, then confirmed by decoding the JSON —
    a bare substring match would prefix-match larger ids (12 vs 123) and
    other campaigns' content."""
    rows = db_module.query(
        app.conn,
        "SELECT strategy_context FROM content WHERE product_id = ? AND platform = ? "
        "AND strategy_context LIKE '%cascaded_from%'",
        (product_id, target))
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        if sctx.get("cascaded_from") == source_id:
            return True
    return False


def job_cascade(app: App, llm: LLM) -> None:
    """Daily: find posts from 2-5 days ago that beat their platform baseline by
    ≥1.5x and re-express them natively on the ladder's lagged platforms."""
    from .. import pipeline

    for product in _active_products(app):
        for src_platform, targets in CASCADE_LADDER.items():
            rows = db_module.query(
                app.conn,
                """
                SELECT c.id, m.engagement_rate,
                       (SELECT AVG(m3.engagement_rate) FROM metrics m3
                        JOIN posts p3 ON p3.id = m3.post_id
                        JOIN content c3 ON c3.id = p3.content_id
                        WHERE c3.platform = ? AND c3.product_id = ?) AS baseline
                FROM content c
                JOIN posts p ON p.content_id = c.id
                JOIN metrics m ON m.post_id = p.id
                WHERE c.product_id = ? AND c.platform = ? AND c.status = 'posted'
                  AND p.posted_at BETWEEN datetime('now', '-5 days')
                                      AND datetime('now', '-2 days')
                  AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                              ORDER BY m2.collected_at DESC LIMIT 1)
                ORDER BY m.engagement_rate DESC LIMIT 3
                """,
                (src_platform, product["id"], product["id"], src_platform))
            for row in rows:
                baseline = row["baseline"] or 0.0
                if baseline <= 0 or (row["engagement_rate"] or 0) < 1.5 * baseline:
                    continue
                for target in targets:
                    if not app.settings.platform(target).enabled:
                        continue
                    if _already_cascaded(app, product["id"], row["id"], target):
                        continue
                    _safe(pipeline.adapt_content, app, llm, row["id"], target)
    log.info("cascade pass done")


def job_feedback(app: App, llm: LLM) -> None:
    from .. import series as series_mod
    from ..learning import feedback, knowledge

    for product in _active_products(app):
        _safe(feedback.run, app, llm, product)
        # Franchise bookkeeping: per-series stats + the kill rule (retire a
        # series underperforming 3 episodes running, spawn a fresh premise).
        _safe(series_mod.run_maintenance, app, llm, product)
        # Knowledge self-refresh: mine fresh audience language from comments
        # and trends into the specificity bank / pain veins.
        _safe(knowledge.mine, app, llm, product)
    log.info("ran feedback loop")


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
    sched.add_job(_job(job_collect_analytics, needs_llm=True),
                  CronTrigger.from_crontab(sc.analytics_collection_cron, timezone=tz),
                  id="analytics", name="collect analytics + draft replies")
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

    # Daily winner cascade (platform-lag arbitrage).
    sched.add_job(_job(job_cascade, needs_llm=True),
                  CronTrigger.from_crontab("30 9 * * *", timezone=tz),
                  id="cascade", name="cascade winners cross-platform")

    # One posting job per (platform, optimal_time), with ± jitter to avoid bot
    # patterns and to spread posts out.
    jitter = max(0, int(sc.posting_jitter_minutes)) * 60
    for platform in app.settings.enabled_platforms():
        for t in app.settings.platform(platform).optimal_times:
            hour, minute = _parse_hhmm(t)
            sched.add_job(
                _job(job_post_platform, extra_args=(platform, t)),
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
