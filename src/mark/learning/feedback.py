"""Feedback loop orchestrator — the self-improvement pass.

  1. Collect fresh metrics.
  2. Decay old bandit evidence (half-life; enables adaptation to shifts).
  3. Reward every mature, not-yet-rewarded post EXACTLY ONCE:
       - baseline = this platform's trailing median engagement (never pooled
         across platforms — platform norms differ 2-4x)
       - reward   = graded, saturation-free: rate/(rate+baseline) mixed with a
         click-through component (business results, not just vanity engagement)
  4. Update the bandit arms with those rewards; stamp posts.rewarded_at.
  5. Re-index the RAG-of-winners (per-platform, freshness-windowed).
  6. Analyze comment sentiment.
  7. Run the analyzer to produce insights and store them.
  8. Compute the holdout lift report — bandit-policy posts vs random-policy
     posts — the standing empirical proof that learning is lifting performance.

Because rewards are idempotent (a post is credited once, when mature), this is
safe to run daily or even hourly; the weekly cron is just the floor.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .. import db as db_module
from ..agents import analyzer
from ..analytics import collector, sentiment
from ..app import App
from ..llm import LLM
from . import bandit, winners

BASELINE_WINDOW_DAYS = 60   # trailing window for platform baselines
CLICK_WEIGHT = 0.15         # share of the reward carried by click-through


def _unrewarded_mature_posts(app: App, product_id: str, maturity_hours: int) -> list[dict]:
    """Posts that are old enough to have stable metrics and were never credited."""
    rows = db_module.query(
        app.conn,
        """
        SELECT c.id, c.product_id, c.platform, c.content_type, c.strategy_context,
               p.id AS post_id, p.posted_at,
               m.engagement_rate, m.views, m.clicks
        FROM content c
        JOIN posts p ON p.content_id = c.id
        JOIN metrics m ON m.post_id = p.id
        WHERE c.product_id = ? AND c.status = 'posted'
          AND p.rewarded_at IS NULL
          AND p.posted_at <= datetime('now', ?)
          AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                      ORDER BY m2.collected_at DESC LIMIT 1)
        """,
        (product_id, f"-{int(maturity_hours)} hours"),
    )
    return [dict(r) for r in rows]


def _platform_baselines(app: App, product_id: str) -> dict[str, dict]:
    """Per-platform trailing medians of engagement rate and click rate.

    Uses each post's LATEST metric within the window. Returns
    {platform: {"n": count, "engagement": median_er, "clicks": median_cr}}.
    """
    rows = db_module.query(
        app.conn,
        """
        SELECT c.platform, m.engagement_rate, m.views, m.clicks
        FROM content c
        JOIN posts p ON p.content_id = c.id
        JOIN metrics m ON m.post_id = p.id
        WHERE c.product_id = ? AND c.status = 'posted'
          AND p.posted_at >= datetime('now', ?)
          AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                      ORDER BY m2.collected_at DESC LIMIT 1)
        """,
        (product_id, f"-{BASELINE_WINDOW_DAYS} days"),
    )
    by_platform: dict[str, list[dict]] = {}
    for r in rows:
        by_platform.setdefault(r["platform"], []).append(dict(r))

    def median(vals: list[float]) -> float:
        vals = sorted(vals)
        n = len(vals)
        if not n:
            return 0.0
        mid = n // 2
        return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0

    out = {}
    for platform, items in by_platform.items():
        ers = [i["engagement_rate"] or 0.0 for i in items]
        crs = [(i["clicks"] or 0) / max(i["views"] or 0, 1) for i in items]
        out[platform] = {"n": len(items), "engagement": median(ers), "clicks": median(crs)}
    return out


def graded_reward(rate: float, baseline: float,
                  click_rate: float = 0.0, click_baseline: float = 0.0) -> float:
    """Saturation-free reward in [0, 1]; performing exactly at baseline = 0.5.

    rate/(rate+baseline) preserves magnitude ordering all the way up: baseline
    → 0.5, 3x baseline → 0.75, 10x → ~0.91. A viral hit and a slightly-above-
    average post are DIFFERENT signals — the old min(rate/baseline, 1) cap made
    them identical, flattening the gradient toward greatness.
    """
    b = max(baseline, 1e-9)
    r_eng = rate / (rate + b) if (rate + b) > 0 else 0.5
    if click_baseline > 1e-9:
        r_clk = click_rate / (click_rate + click_baseline)
        return (1.0 - CLICK_WEIGHT) * r_eng + CLICK_WEIGHT * r_clk
    return r_eng


def _nearest_time(posted_at: Optional[str], times: list[str],
                  tz_name: str = "UTC") -> Optional[str]:
    """Map a UTC posted_at to the nearest configured (local wall-clock) slot."""
    if not posted_at or not times:
        return times[0] if times else None
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.strptime(str(posted_at)[:19], "%Y-%m-%d %H:%M:%S") \
            .replace(tzinfo=timezone.utc)
        hour = dt.astimezone(ZoneInfo(tz_name)).hour
    except Exception:
        return times[0]

    def to_h(t: str) -> int:
        return int(t.split(":")[0])
    # Circular distance so 23:00 is 2h from 01:00, not 22h.
    return min(times, key=lambda t: min(abs(to_h(t) - hour), 24 - abs(to_h(t) - hour)))


def apply_rewards(app: App, product_id: str) -> dict:
    """Steps 2-4: decay, then credit every mature unrewarded post exactly once."""
    lcfg = app.settings.learning
    bandit.decay(app, product_id, lcfg.decay_half_life_days)

    posts = _unrewarded_mature_posts(app, product_id, lcfg.reward_maturity_hours)
    baselines = _platform_baselines(app, product_id)
    applied, skipped = 0, 0
    for p in posts:
        base = baselines.get(p["platform"])
        if not base or base["n"] < lcfg.min_baseline_posts:
            skipped += 1  # stays unrewarded; credited once the platform has a baseline
            continue
        rate = p["engagement_rate"] or 0.0
        click_rate = (p["clicks"] or 0) / max(p["views"] or 0, 1)
        reward = graded_reward(rate, base["engagement"], click_rate, base["clicks"])
        post_time = _nearest_time(p["posted_at"],
                                  app.settings.platform(p["platform"]).optimal_times,
                                  tz_name=app.settings.scheduling.timezone)
        bandit.update_from_content(app, p, reward, post_time=post_time)
        db_module.update(app.conn, "posts", p["post_id"],
                         rewarded_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                         reward=round(reward, 5))
        applied += 1
    return {"rewards_applied": applied, "awaiting_baseline": skipped,
            "baselines": {k: round(v["engagement"], 5) for k, v in baselines.items()}}


def holdout_lift(app: App, product_id: str, days: int = 90) -> Optional[dict]:
    """Compare rewarded posts generated by the bandit policy vs the random
    holdout policy. Positive lift = empirical proof the learning loop works.
    Returns None until both groups have data."""
    rows = db_module.query(
        app.conn,
        """
        SELECT c.strategy_context, p.reward
        FROM content c JOIN posts p ON p.content_id = c.id
        WHERE c.product_id = ? AND p.reward IS NOT NULL
          AND p.posted_at >= datetime('now', ?)
        """,
        (product_id, f"-{int(days)} days"),
    )
    bandit_rs, holdout_rs = [], []
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        (holdout_rs if sctx.get("policy") == "holdout" else bandit_rs).append(r["reward"])
    if not bandit_rs or not holdout_rs:
        return None
    b = sum(bandit_rs) / len(bandit_rs)
    h = sum(holdout_rs) / len(holdout_rs)
    return {
        "bandit_posts": len(bandit_rs), "bandit_avg_reward": round(b, 4),
        "holdout_posts": len(holdout_rs), "holdout_avg_reward": round(h, 4),
        "lift_pct": round((b - h) / max(h, 1e-9) * 100.0, 1),
    }


def run(app: App, llm: LLM, product: dict, days: int = 7, collect: bool = True) -> dict:
    product_id = product["id"]

    if collect:
        collector.collect(app, product_id=product_id)

    reward_report = apply_rewards(app, product_id)

    new_winners = winners.refresh_winners(app, llm, product)

    # Housekeeping: drop generated media older than 30 days.
    from ..agents.media import prune_old_media

    pruned = prune_old_media(app, days=30)

    sentiment.analyze_unscored(app, llm, product_id=product_id)
    sentiment_summary = sentiment.summarize(app, product_id=product_id)

    insights = analyzer.analyze(app, llm, product, days=max(days, 14),
                                sentiment_summary=sentiment_summary)
    db_module.insert(app.conn, "insights", product_id=product_id,
                     payload=json.dumps(insights.model_dump()))

    # Owner-taste maintenance: conclude ripe creative experiments, let the
    # scientist take an investigation step, and age out stale taste lessons.
    taste_report: dict = {}
    try:
        from .. import scientist as scientist_mod
        from .. import taste as taste_mod

        sci = scientist_mod.run(app, llm, product, force=True) or {}
        retired = taste_mod.decay_stale_lessons(app, product_id)
        taste_report = {"scientist": sci.get("notebook_entry"),
                        "experiments_opened": len(sci.get("opened", [])),
                        "experiments_concluded": len(sci.get("concluded", [])),
                        "stale_lessons_retired": retired}
    except Exception as exc:  # taste channel must never break the loop
        db_module.log_activity(app.conn, "learn", f"taste maintenance failed: {exc}",
                               product_id=product_id, level="error")

    lift = holdout_lift(app, product_id)

    report = {
        "product_id": product_id,
        **reward_report,
        "bandit_updates": reward_report["rewards_applied"],
        "new_winners": len(new_winners),
        "total_winners": winners.count(app, product_id),
        "media_pruned": pruned,
        "sentiment": sentiment_summary,
        "taste": taste_report,
        "holdout_lift": lift,
        "insights": insights.model_dump(),
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    return report


def latest_insights(app: App, product_id: str) -> Optional[dict]:
    row = db_module.query_one(
        app.conn,
        "SELECT payload, created_at FROM insights WHERE product_id = ? "
        "ORDER BY created_at DESC LIMIT 1", (product_id,))
    if not row:
        return None
    data = db_module.loads(row["payload"], {})
    data["_created_at"] = row["created_at"]
    return data
