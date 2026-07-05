"""Self-monitoring — the safety layer that makes unattended operation safe.

Two failure modes an autonomous poster must catch by itself:

  * ENGAGEMENT COLLAPSE — a platform suddenly punishing the account (algorithm
    shift, shadow suppression, audience revolt). Detector: the trailing N
    rewarded posts on a platform average far below baseline → pause that
    platform's posting AND its self-approval for a cool-down window, alert
    loudly in the activity feed. Human can resume early by clearing the pause.

  * RUNAWAY SPEND — real API spend past the daily cap → freeze generation for
    the rest of the day (posting of already-made content continues).

State lives in the meta table so it survives restarts and is visible to the
web app. Everything here is best-effort: monitoring must never crash a job.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import db as db_module
from .app import App


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Platform pause (collapse cool-down / manual kill-switch)
# --------------------------------------------------------------------------- #
def _pause_key(product_id: str, platform: str) -> str:
    return f"paused_until:{product_id}:{platform}"


def pause(app: App, product_id: str, platform: str, hours: float, reason: str) -> None:
    until = _fmt(_now_dt() + timedelta(hours=hours))
    db_module.set_meta(app.conn, _pause_key(product_id, platform), until)
    db_module.log_activity(
        app.conn, "safety",
        f"PAUSED {platform} for {product_id} until {until} UTC — {reason}",
        product_id=product_id, level="error")


def resume(app: App, product_id: str, platform: str) -> None:
    db_module.set_meta(app.conn, _pause_key(product_id, platform), "")
    db_module.log_activity(app.conn, "safety",
                           f"Resumed {platform} for {product_id}",
                           product_id=product_id, level="success")


def is_paused(app: App, product_id: str, platform: str) -> bool:
    until = db_module.get_meta(app.conn, _pause_key(product_id, platform))
    return bool(until) and until > _fmt(_now_dt())


def paused_platforms(app: App, product_id: str) -> list[dict]:
    rows = db_module.query(
        app.conn, "SELECT key, value FROM meta WHERE key LIKE ? AND value != ''",
        (f"paused_until:{product_id}:%",))
    now = _fmt(_now_dt())
    out = []
    for r in rows:
        if r["value"] > now:
            out.append({"platform": r["key"].split(":")[-1], "until": r["value"]})
    return out


# --------------------------------------------------------------------------- #
# Engagement-collapse detection
# --------------------------------------------------------------------------- #
def check_engagement_collapse(app: App, product: dict) -> list[dict]:
    """Examine each platform's trailing rewarded posts; pause on collapse.
    Returns the list of collapses found (for reporting)."""
    cfg = app.settings.safety
    window = max(3, int(cfg.collapse_window))
    collapses = []
    platforms = db_module.query(
        app.conn,
        "SELECT DISTINCT c.platform FROM content c JOIN posts p ON p.content_id = c.id "
        "WHERE c.product_id = ? AND p.reward IS NOT NULL", (product["id"],))
    for prow in platforms:
        platform = prow["platform"]
        if is_paused(app, product["id"], platform):
            continue
        rows = db_module.query(
            app.conn,
            "SELECT p.reward FROM posts p JOIN content c ON c.id = p.content_id "
            "WHERE c.product_id = ? AND c.platform = ? AND p.reward IS NOT NULL "
            "ORDER BY p.posted_at DESC LIMIT ?",
            (product["id"], platform, window))
        rewards = [r["reward"] for r in rows]
        if len(rewards) < window:
            continue
        avg = sum(rewards) / len(rewards)
        if avg < float(cfg.collapse_threshold):
            reason = (f"engagement collapse: last {window} posts avg graded reward "
                      f"{avg:.2f} (baseline = 0.50, threshold {cfg.collapse_threshold})")
            pause(app, product["id"], platform, float(cfg.pause_hours), reason)
            collapses.append({"platform": platform, "avg_reward": round(avg, 3)})
    return collapses


# --------------------------------------------------------------------------- #
# Spend guard
# --------------------------------------------------------------------------- #
def spend_today_usd(app: App) -> float:
    row = db_module.query_one(
        app.conn,
        "SELECT COALESCE(SUM(usd), 0) AS total FROM costs "
        "WHERE mocked = 0 AND date(created_at) = date('now')")
    return float(row["total"] or 0.0) if row else 0.0


def check_spend(app: App) -> Optional[float]:
    """Freeze generation for the rest of the day when real spend passes the
    cap. Returns today's spend if frozen, else None."""
    cap = float(app.settings.safety.max_daily_spend_usd)
    if cap <= 0:
        return None
    spent = spend_today_usd(app)
    if spent >= cap and not generation_frozen(app):
        db_module.set_meta(app.conn, "spend_freeze_date",
                           _now_dt().strftime("%Y-%m-%d"))
        db_module.log_activity(
            app.conn, "safety",
            f"SPEND FREEZE: ${spent:.2f} today ≥ ${cap:.2f} cap — generation "
            "paused until tomorrow (posting of existing content continues)",
            level="error")
        return spent
    return None


def generation_frozen(app: App) -> bool:
    return db_module.get_meta(app.conn, "spend_freeze_date") == \
        _now_dt().strftime("%Y-%m-%d")
