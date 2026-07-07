"""Contextual bandit (Thompson Sampling) over discrete content choices.

Each arm is one value of one choice (hook_style / content_type / tone / post_time
/ strategy / humor_mechanism / humor_persona / emotional_target) for a given
platform + product. We keep Beta(alpha, beta) per arm; selection samples from
each arm's Beta and takes the argmax; rewards (graded 0..1, 0.5 = baseline)
update alpha += reward, beta += (1 - reward).

Evolution guarantees built in here:

* **Decay** — evidence has a half-life (config `learning.decay_half_life_days`).
  Old posteriors relax toward the prior, so when audience taste or a platform
  algorithm shifts, the system re-opens exploration within weeks instead of
  needing months of contradicting data. Without decay, adaptation is provably
  impossible once alpha+beta grows large.
* **Informative priors** — strategy arms start from the research-derived mix
  weights instead of flat Beta(1,1), so cold-start behavior matches the
  playbook while real evidence gradually takes over.
* **Allowlist-aware selection** — strategy recommendations respect the
  campaign's strategy allowlist, so restricted campaigns still get learned
  strategy selection instead of falling back to static weights.
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


def candidate_values(app: App, platform: str,
                     product: Optional[dict] = None) -> dict[str, list[str]]:
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
        # SFX density/character for video templates (the SFX engine's style gate).
        "sfx_style": ["heavy_meme", "clean_cinematic", "minimal"],
    }
    strategy_ids = strategies_mod.candidate_ids(app, platform, product=product)
    if product is not None:
        allowlist = strategies_mod.product_allowlist(product)
        if allowlist is not None:
            strategy_ids = [s for s in strategy_ids if s in allowlist]
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
    alpha, beta = _prior_for(app, arm_type, arm_value)
    db_module.insert(app.conn, "bandit_arms", arm_type=arm_type, arm_value=arm_value,
                     platform=platform, product_id=product_id,
                     alpha=alpha, beta_param=beta)
    return dict(db_module.query_one(
        app.conn,
        "SELECT * FROM bandit_arms WHERE arm_type=? AND arm_value=? AND platform=? AND product_id=?",
        (arm_type, arm_value, platform, product_id),
    ))


def _prior_for(app: App, arm_type: str, arm_value: str) -> tuple[float, float]:
    """Informative prior for fresh arms. Strategy arms encode the research-derived
    mix weights as pseudo-observations; everything else starts flat."""
    if arm_type != "strategy":
        return 1.0, 1.0
    from .. import strategies as strategies_mod

    s = strategies_mod.get(arm_value)
    if s is None:
        return 1.0, 1.0
    strength = max(0.0, float(app.settings.learning.strategy_prior_strength))
    # Map mix_weight (~0.05..0.25) to a prior mean in [0.25, 0.7].
    p = min(0.7, max(0.25, s.mix_weight * 2.5))
    return 1.0 + strength * p, 1.0 + strength * (1.0 - p)


def recommend(app: App, product_id: str, platform: str,
              product: Optional[dict] = None) -> dict:
    """Sample the best arm for each choice type. Returns {arm_type: arm_value}."""
    picks = {}
    for arm_type, values in candidate_values(app, platform, product=product).items():
        best_value, best_sample = values[0], -1.0
        for value in values:
            arm = _get_or_create_arm(app, arm_type, value, platform, product_id)
            sample = float(_rng.beta(max(arm["alpha"], 1e-3), max(arm["beta_param"], 1e-3)))
            if sample > best_sample:
                best_sample, best_value = sample, value
        picks[arm_type] = best_value
    return picks


def random_policy(app: App, platform: str, product: Optional[dict] = None,
                  seed: Optional[str] = None) -> dict:
    """Uniform-random picks over the same choice space — the holdout control
    policy. Comparing holdout rewards against bandit rewards is the live,
    empirical proof that the learning loop is actually lifting performance."""
    import random

    rng = random.Random(seed)
    return {arm_type: rng.choice(values)
            for arm_type, values in candidate_values(app, platform, product=product).items()}


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


def decay(app: App, product_id: str, half_life_days: float) -> None:
    """Relax every posterior toward Beta(1,1) with the configured half-life.

    Applied continuously by wall-clock time (bookkept in the meta table), so
    calling this any number of times is equivalent to calling it once — the
    total decay only depends on elapsed time. This is THE mechanism that lets
    the system un-learn a dead preference when the world shifts.
    """
    if not half_life_days or half_life_days <= 0:
        return
    key = f"bandit_decay_at:{product_id}"
    now = datetime.now(timezone.utc)
    last_raw = db_module.get_meta(app.conn, key)
    db_module.set_meta(app.conn, key, now.strftime("%Y-%m-%d %H:%M:%S"))
    if not last_raw:
        return  # first call just stamps the clock
    try:
        last = datetime.strptime(last_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return
    elapsed_days = max(0.0, (now - last).total_seconds() / 86400.0)
    if elapsed_days <= 0:
        return
    gamma = 0.5 ** (elapsed_days / half_life_days)
    if gamma >= 0.9999:
        return
    decay_arms(app, product_id, gamma)


def decay_arms(app: App, product_id: str, gamma: float) -> None:
    """Rescale all of a product's posteriors toward Beta(1,1) by factor gamma.
    alpha,beta relax toward 1; pulls/total_reward relax with the same factor so
    avg_reward stays meaningful and track-record gates see decayed sample sizes.
    (Split out from decay() so simulations can step time explicitly.)"""
    db_module.execute(
        app.conn,
        "UPDATE bandit_arms SET alpha = 1.0 + (alpha - 1.0) * ?, "
        "beta_param = 1.0 + (beta_param - 1.0) * ?, "
        "pulls = CAST(pulls * ? AS INTEGER), total_reward = total_reward * ? "
        "WHERE product_id = ?",
        (gamma, gamma, gamma, gamma, product_id),
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
