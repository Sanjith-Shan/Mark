"""Graduated autonomy — approval that is earned per (strategy, platform).

The vision: full autonomy is the destination, but it must be TRUSTED autonomy.
So instead of one global auto-approve switch, approval authority is granted
where the system has proof it deserves it:

  * the draft's own QA scores (judge + humor gates, persisted on content.qa)
    clear the configured bar, AND
  * this strategy on this platform has a track record: ≥ min_track_record
    rewarded posts whose average graded reward is at/above the account
    baseline (0.5 on the graded scale).

Because bandit evidence decays and rewards are graded, a strategy that stops
working loses its track record — and its autonomy — automatically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import db as db_module
from . import store
from .app import App


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def approval_mode(app: App) -> str:
    cfg = app.settings.approval
    if cfg.mode in ("manual", "graduated", "full"):
        return cfg.mode
    return "full" if cfg.auto_approve else "manual"


def qa_passes(app: App, qa: Optional[dict]) -> bool:
    """The draft's own quality evidence. Judge scores are 0-10; a draft with no
    recorded scores (single-variant, judge skipped) passes on the humor gates
    alone if humor ran, else is treated as unscored (fails the graduated bar —
    no evidence, no autonomy)."""
    qa = qa or {}
    bar = float(app.settings.approval.qa_bar)
    judge_scores = [qa.get(k) for k in ("hook_strength", "brand_fit", "scroll_stopping")]
    judge_scores = [s for s in judge_scores if isinstance(s, (int, float)) and s > 0]
    if judge_scores:
        return sum(judge_scores) / len(judge_scores) >= bar
    if qa.get("humor_applied"):
        # Humor QA already gated on violation strength + benignness.
        return True
    return False


def track_record(app: App, product_id: str, platform: str,
                 strategy_id: Optional[str]) -> dict:
    """Evidence that this strategy earns baseline-or-better on this platform.
    Uses the bandit arm (decayed pulls + avg graded reward), so a shift that
    tanks performance automatically revokes autonomy as evidence fades."""
    if not strategy_id:
        return {"pulls": 0, "avg_reward": 0.0}
    row = db_module.query_one(
        app.conn,
        "SELECT pulls, avg_reward FROM bandit_arms WHERE arm_type = 'strategy' "
        "AND arm_value = ? AND platform = ? AND product_id = ?",
        (strategy_id, platform, product_id))
    if not row:
        return {"pulls": 0, "avg_reward": 0.0}
    return {"pulls": row["pulls"] or 0, "avg_reward": row["avg_reward"] or 0.0}


def maybe_auto_approve(app: App, product: dict, content_id: int, platform: str,
                       content_type: str, strategy=None,
                       qa: Optional[dict] = None) -> bool:
    """Decide and (if earned) apply auto-approval. Returns True if approved."""
    cfg = app.settings.approval
    if strategy is not None and getattr(strategy, "never_auto_approve", False):
        return False
    from . import monitor

    if monitor.is_paused(app, product["id"], platform):
        return False  # a collapsed/paused platform never self-approves

    mode = approval_mode(app)
    approve = False
    reason = ""
    if content_type in (cfg.auto_approve_types or []):
        approve, reason = True, f"type {content_type} is always auto-approved"
    elif mode == "full":
        approve, reason = True, "approval mode: full"
    elif mode == "graduated":
        record = track_record(app, product["id"], platform,
                              getattr(strategy, "id", None) if strategy else None)
        if (qa_passes(app, qa)
                and record["pulls"] >= int(cfg.min_track_record)
                and record["avg_reward"] >= 0.5):
            approve = True
            reason = (f"earned: QA passed, {getattr(strategy, 'id', '?')} on {platform} has "
                      f"{record['pulls']} rewarded posts at avg {record['avg_reward']:.2f}")
    if approve:
        store.set_content_status(app.conn, content_id, "approved", approved_at=_now())
        db_module.log_activity(app.conn, "approve",
                               f"Auto-approved #{content_id} ({reason})",
                               product_id=product["id"], content_id=content_id)
    return approve
