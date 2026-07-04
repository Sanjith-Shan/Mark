"""Contextual bandit (Thompson Sampling) over discrete content choices.

Each arm is one value of one choice (hook_style / content_type / tone / post_time)
for a given platform + product. We keep Beta(alpha, beta) per arm; selection samples
from each arm's Beta and takes the argmax; rewards (normalized engagement, 0..1)
update alpha += reward, beta += (1 - reward).

The bandit learns which choices work for THIS audience on EACH platform.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .. import db as db_module
from ..app import App
from ..constants import (EMOTIONAL_TARGETS, HOOK_STYLES, HUMOR_MECHANISMS,
                         HUMOR_PERSONAS, TONES)

_rng = np.random.default_rng()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def candidate_values(app: App, platform: str) -> dict[str, list[str]]:
    from .. import strategies as strategies_mod  # lazy: avoids import cycles

    pconf = app.settings.platform(platform)
    values = {
        "hook_style": HOOK_STYLES,
        "content_type": pconf.content_types or ["text"],
        "tone": TONES,
        "post_time": pconf.optimal_times or ["12:00"],
        "humor_mechanism": HUMOR_MECHANISMS,
        "humor_persona": HUMOR_PERSONAS,
        "emotional_target": EMOTIONAL_TARGETS,
    }
    strategy_ids = strategies_mod.candidate_ids(app, platform)
    if strategy_ids:
        values["strategy"] = strategy_ids
    return values


def _get_or_create_arm(app: App, arm_type: str, arm_value: str,
                       platform: str, product_id: str) -> dict:
    row = db_module.query_one(
        app.conn,
        "SELECT * FROM bandit_arms WHERE arm_type=? AND arm_value=? AND platform=? AND product_id=?",
        (arm_type, arm_value, platform, product_id),
    )
    if row:
        return dict(row)
    db_module.insert(app.conn, "bandit_arms", arm_type=arm_type, arm_value=arm_value,
                     platform=platform, product_id=product_id)
    return dict(db_module.query_one(
        app.conn,
        "SELECT * FROM bandit_arms WHERE arm_type=? AND arm_value=? AND platform=? AND product_id=?",
        (arm_type, arm_value, platform, product_id),
    ))


def recommend(app: App, product_id: str, platform: str) -> dict:
    """Sample the best arm for each choice type. Returns {arm_type: arm_value}."""
    picks = {}
    for arm_type, values in candidate_values(app, platform).items():
        best_value, best_sample = values[0], -1.0
        for value in values:
            arm = _get_or_create_arm(app, arm_type, value, platform, product_id)
            sample = float(_rng.beta(max(arm["alpha"], 1e-3), max(arm["beta_param"], 1e-3)))
            if sample > best_sample:
                best_sample, best_value = sample, value
        picks[arm_type] = best_value
    return picks


def update(app: App, product_id: str, platform: str, arm_type: str,
           arm_value: str, reward: float) -> None:
    """Apply a reward (clamped to [0, 1]) to one arm."""
    reward = max(0.0, min(float(reward), 1.0))
    arm = _get_or_create_arm(app, arm_type, arm_value, platform, product_id)
    pulls = arm["pulls"] + 1
    total = arm["total_reward"] + reward
    db_module.update(
        app.conn, "bandit_arms", arm["id"],
        pulls=pulls, total_reward=total, avg_reward=total / pulls,
        alpha=arm["alpha"] + reward, beta_param=arm["beta_param"] + (1.0 - reward),
        updated_at=_now(),
    )


def update_from_content(app: App, content: dict, reward: float,
                        post_time: Optional[str] = None) -> None:
    """Update all arms implied by a posted content row."""
    sctx = db_module.loads(content.get("strategy_context"), {}) or {}
    platform, product_id = content["platform"], content["product_id"]
    mapping = {
        "hook_style": sctx.get("hook_style"),
        "content_type": content.get("content_type"),
        "tone": sctx.get("tone"),
        "post_time": post_time,
        "strategy": sctx.get("strategy"),
        "humor_mechanism": sctx.get("humor_mechanism"),
        "humor_persona": sctx.get("humor_persona"),
        "emotional_target": sctx.get("emotional_target"),
    }
    for arm_type, value in mapping.items():
        if value:
            update(app, product_id, platform, arm_type, str(value), reward)


def leaderboard(app: App, product_id: str, platform: Optional[str] = None) -> list[dict]:
    clause = "WHERE product_id = ?"
    params = [product_id]
    if platform:
        clause += " AND platform = ?"
        params.append(platform)
    rows = db_module.query(
        app.conn,
        f"SELECT arm_type, arm_value, platform, pulls, avg_reward, alpha, beta_param "
        f"FROM bandit_arms {clause} AND pulls > 0 ORDER BY avg_reward DESC",
        params,
    )
    return [dict(r) for r in rows]
