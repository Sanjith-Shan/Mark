"""Feedback loop orchestrator — the weekly self-improvement pass.

  1. Collect fresh metrics.
  2. Compute the account baseline engagement rate.
  3. Normalize each post's engagement into a reward (rate / baseline, capped at 1).
  4. Update the bandit arms with those rewards.
  5. Re-index the RAG-of-winners.
  6. Analyze comment sentiment.
  7. Run the analyzer to produce insights and store them.
  8. Prune stale winners (handled inside refresh_winners).
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


def _posted_with_metrics(app: App, product_id: str, days: int) -> list[dict]:
    rows = db_module.query(
        app.conn,
        """
        SELECT c.id, c.product_id, c.platform, c.content_type, c.strategy_context,
               p.posted_at, m.engagement_rate
        FROM content c
        JOIN posts p ON p.content_id = c.id
        JOIN metrics m ON m.post_id = p.id
        WHERE c.product_id = ? AND c.status = 'posted'
          AND p.posted_at >= datetime('now', ?)
          AND m.id = (SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
                      ORDER BY m2.collected_at DESC LIMIT 1)
        """,
        (product_id, f"-{int(days)} days"),
    )
    return [dict(r) for r in rows]


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


def run(app: App, llm: LLM, product: dict, days: int = 7, collect: bool = True) -> dict:
    product_id = product["id"]

    if collect:
        collector.collect(app, product_id=product_id)

    posts = _posted_with_metrics(app, product_id, days)
    rewards_applied = 0
    baseline = 0.0
    if posts:
        rates = [p["engagement_rate"] or 0.0 for p in posts]
        baseline = (sum(rates) / len(rates)) or 1e-6
        for p in posts:
            reward = min((p["engagement_rate"] or 0.0) / baseline, 1.0)
            post_time = _nearest_time(p["posted_at"],
                                      app.settings.platform(p["platform"]).optimal_times,
                                      tz_name=app.settings.scheduling.timezone)
            bandit.update_from_content(app, p, reward, post_time=post_time)
            rewards_applied += 1

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

    report = {
        "product_id": product_id,
        "baseline_engagement": round(baseline, 5),
        "posts_evaluated": len(posts),
        "bandit_updates": rewards_applied,
        "new_winners": len(new_winners),
        "total_winners": winners.count(app, product_id),
        "media_pruned": pruned,
        "sentiment": sentiment_summary,
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
