"""Campaign A/B experiments — campaigns as variants (the "summer test lab").

An experiment groups 2+ campaigns (products) as variants under a named
hypothesis. Each variant's performance is compared on the experiment's metric
using the latest-metric-per-post pattern (same SQL style as
learning/feedback.py), and a simple leader is determined. Concluding an
experiment freezes it with a written conclusion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import db as db_module
from . import store
from .app import App


def create_experiment(app: App, name: str, hypothesis: str,
                      campaign_ids: list[str],
                      metric: str = "engagement_rate") -> int:
    """Insert a new running experiment; returns its id."""
    return db_module.insert(
        app.conn, "experiments",
        name=name, hypothesis=hypothesis,
        campaign_ids=list(campaign_ids), metric=metric,
    )


def get_experiment(app: App, experiment_id: int) -> Optional[dict]:
    row = db_module.query_one(
        app.conn, "SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    if row is None:
        return None
    out = dict(row)
    out["campaign_ids"] = db_module.loads(out.get("campaign_ids"), [])
    return out


def list_experiments(app: App) -> list[dict]:
    rows = db_module.query(
        app.conn, "SELECT * FROM experiments ORDER BY started_at DESC, id DESC")
    out = []
    for r in rows:
        d = dict(r)
        d["campaign_ids"] = db_module.loads(d.get("campaign_ids"), [])
        out.append(d)
    return out


def _variant_stats(app: App, product_id: str) -> dict:
    """Per-variant aggregates using each post's LATEST metric (feedback.py style)."""
    perf = db_module.query_one(
        app.conn,
        """
        SELECT COUNT(DISTINCT p.id) AS posts,
               COALESCE(AVG(m.engagement_rate), 0) AS avg_engagement,
               COALESCE(SUM(m.views), 0) AS views,
               COALESCE(SUM(m.likes), 0) AS likes
        FROM posts p
        JOIN content c ON c.id = p.content_id
        LEFT JOIN metrics m ON m.id = (
            SELECT m2.id FROM metrics m2 WHERE m2.post_id = p.id
            ORDER BY m2.collected_at DESC LIMIT 1)
        WHERE c.product_id = ?
        """,
        (product_id,))
    reward = db_module.query_one(
        app.conn,
        """
        SELECT AVG(p.reward) AS avg_reward, COUNT(p.reward) AS rewarded_posts
        FROM posts p JOIN content c ON c.id = p.content_id
        WHERE c.product_id = ? AND p.reward IS NOT NULL
        """,
        (product_id,))
    product = store.get_product(app.conn, product_id)
    return {
        "campaign_id": product_id,
        "campaign_name": product["name"] if product else product_id,
        "posts": perf["posts"] if perf else 0,
        "avg_engagement": round(perf["avg_engagement"], 5) if perf else 0.0,
        "views": perf["views"] if perf else 0,
        "likes": perf["likes"] if perf else 0,
        "avg_reward": (round(reward["avg_reward"], 5)
                       if reward and reward["avg_reward"] is not None else None),
        "rewarded_posts": reward["rewarded_posts"] if reward else 0,
    }


def experiment_report(app: App, experiment_id: int) -> Optional[dict]:
    """Compare the experiment's variants and pick a simple leader.

    Leader = the variant with the highest value on the experiment's metric
    ("reward" → avg_reward, anything else → avg_engagement) among variants
    that actually have posts. None while no variant has data or on a tie.
    """
    exp = get_experiment(app, experiment_id)
    if exp is None:
        return None
    variants = [_variant_stats(app, pid) for pid in exp["campaign_ids"]]

    def metric_value(v: dict) -> float:
        if exp["metric"] == "reward":
            return v["avg_reward"] or 0.0
        return v["avg_engagement"] or 0.0

    leader = None
    scored = [(metric_value(v), v["campaign_id"]) for v in variants if v["posts"] > 0]
    if scored:
        scored.sort(reverse=True)
        best = scored[0]
        # A tie (or a single variant with a zero score) is not a leader.
        if best[0] > 0 and (len(scored) == 1 or best[0] > scored[1][0]):
            leader = best[1]
    return {**exp, "variants": variants, "leader": leader}


def conclude_experiment(app: App, experiment_id: int, conclusion: str) -> Optional[dict]:
    """Mark an experiment concluded with a written conclusion."""
    if get_experiment(app, experiment_id) is None:
        return None
    db_module.update(
        app.conn, "experiments", experiment_id,
        status="concluded", conclusion=conclusion,
        ended_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    return get_experiment(app, experiment_id)
