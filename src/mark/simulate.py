"""Evolution proof — closed-loop simulation that PROVES the learning works.

The offline mock world has a hidden audience-taste model (see
analytics/collector._taste_multiplier): engagement depends on what each post
actually was (hook style, tone, strategy, persona, emotion). This module plants
a KNOWN taste, runs the full production loop — generate → post → collect →
feedback → bandit update — for N cycles, and measures:

  1. CONVERGENCE — does the bandit's recommendation concentrate on the planted
     best arms as evidence accumulates?
  2. LIFT — do bandit-policy posts earn higher rewards than the random-policy
     holdout posts running alongside them?
  3. ADAPTATION — when the planted taste is inverted mid-run (an "algorithm
     shift"), does the system un-learn the dead preference and re-converge?

No step is mocked out: this exercises the same strategist/writer/humor/posting/
metrics/feedback code paths production uses. `mark evolve-proof` runs it from
the CLI; tests/test_evolution.py runs a shorter version in CI.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import db as db_module
from . import pipeline, store
from .app import App, get_app
from .config import ProductConfig
from .llm import LLM

# The taste we plant: "question hooks and dark absurdist comedy win; stories
# and inspiration die." Phase 2 inverts it.
PLANTED_TASTE = {
    "hook_style:question": 2.4,
    "hook_style:story": 0.45,
    "tone:funny": 1.9,
    "tone:inspirational": 0.5,
    "emotional_target:dark_laughter": 1.6,
    "emotional_target:hope": 0.6,
}

WATCH_ARM = ("hook_style", "question", "story")  # (arm_type, best, worst)


def _invert(taste: dict) -> dict:
    """The mid-run world shift: winners become losers and vice versa."""
    out = {}
    for k, v in taste.items():
        out[k] = round(1.0 / v, 3)
    return out


@dataclass
class ProofResult:
    cycles: int
    shift_at: Optional[int]
    # Per-cycle: probability the bandit currently recommends the planted-best
    # watch arm (sampled), and the planted-best's posterior mean.
    recommend_share: list[float] = field(default_factory=list)
    rewards_by_policy: dict = field(default_factory=lambda: {"bandit": [], "holdout": []})
    lift: Optional[dict] = None
    converged_share_pre_shift: float = 0.0
    converged_share_end: float = 0.0
    early_share: float = 0.0

    def summary(self) -> dict:
        return {
            "cycles": self.cycles,
            "shift_at": self.shift_at,
            "early_best_arm_share": round(self.early_share, 3),
            "pre_shift_best_arm_share": round(self.converged_share_pre_shift, 3),
            "post_shift_new_best_share": round(self.converged_share_end, 3),
            "holdout_lift": self.lift,
        }


def _recommend_share(app: App, product_id: str, platform: str,
                     arm_type: str, value: str, samples: int = 30) -> float:
    """How often Thompson sampling currently picks `value` for `arm_type`."""
    from .learning import bandit

    hits = 0
    for _ in range(samples):
        picks = bandit.recommend(app, product_id, platform)
        if picks.get(arm_type) == value:
            hits += 1
    return hits / samples


def _write_sim_config(home: Path, holdout_pct: float) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    cfg = {
        "platforms": {
            "x": {"enabled": True, "max_posts_per_day": 999,
                  "content_types": ["text", "image"],
                  "optimal_times": ["09:00", "12:00", "18:00"], "hashtag_count": 3},
        },
        "llm": {"variants": 1, "self_critique": False,
                "novelty_threshold": 2.0},  # novelty guard off: sim reuses mock copy
        "humor": {"enabled": True, "candidates": 3, "candidates_light": 2,
                  "predictability_filter": False},
        "learning": {"reward_maturity_hours": 0, "min_baseline_posts": 1,
                     "holdout_pct": holdout_pct, "decay_half_life_days": 45.0},
        "approval": {"auto_approve": True},
    }
    import yaml

    (home / "config" / "default.yaml").write_text(yaml.safe_dump(cfg))


def _sim_product() -> ProductConfig:
    return ProductConfig(
        id="simco", name="SimCo",
        description="A tool that automates boring repetitive work for builders.",
        target_audience="indie builders shipping side projects",
        brand_voice="casual, punchy, no corporate-speak",
        platforms=["x"], posting_cadence={"x": 1},
    )


def run_proof(cycles: int = 90, shift_at: Optional[int] = 60,
              holdout_pct: float = 0.25, home: Optional[Path] = None,
              posts_per_cycle: int = 2, seed: int = 7,
              sim_days_per_cycle: float = 1.0, decay_half_life_days: float = 21.0,
              on_cycle=None) -> ProofResult:
    """Run the closed-loop proof. Returns measurements; caller judges them."""
    import numpy as np

    from .learning import bandit as bandit_mod
    from .learning import feedback

    bandit_mod._rng = np.random.default_rng(seed)  # deterministic sampling

    tmpdir: Optional[str] = None
    if home is None:
        tmpdir = tempfile.mkdtemp(prefix="mark-evolution-proof-")
        home = Path(tmpdir)
    try:
        _write_sim_config(home, holdout_pct)
        app = get_app(home=home, force_mock=True)
        llm = LLM(app)
        product_cfg = _sim_product()
        store.upsert_product(app.conn, product_cfg, active=True)
        product = store.get_product(app.conn, product_cfg.id)

        db_module.set_meta(app.conn, "mock_taste", json.dumps(PLANTED_TASTE))
        arm_type, best, worst = WATCH_ARM
        result = ProofResult(cycles=cycles, shift_at=shift_at)
        platform = "x"

        from .posting import manager

        for cycle in range(cycles):
            if shift_at is not None and cycle == shift_at:
                db_module.set_meta(app.conn, "mock_taste",
                                   json.dumps(_invert(PLANTED_TASTE)))
            for _ in range(posts_per_cycle):
                row = pipeline.generate_one(app, llm, product, platform)
                # auto_approve already set status; post whatever is approved
                if row["status"] == "approved":
                    manager.post_content(app, row)
            # Metrics + learning — the production feedback pass, minus the
            # LLM-analyzer frills that don't affect the bandit.
            from .analytics import collector

            collector.collect(app, product_id=product["id"])
            feedback.apply_rewards(app, product["id"])
            # Step simulated time: each cycle is a "day", so the evidence
            # half-life actually operates (wall-clock decay can't fire inside
            # a seconds-long simulation). This is the mechanism under test in
            # the adaptation phase — without it, re-convergence provably stalls.
            if decay_half_life_days > 0:
                gamma = 0.5 ** (sim_days_per_cycle / decay_half_life_days)
                bandit_mod.decay_arms(app, product["id"], gamma)

            share = _recommend_share(app, product["id"], platform, arm_type,
                                     best if (shift_at is None or cycle < shift_at) else worst)
            result.recommend_share.append(share)
            if on_cycle:
                on_cycle(cycle, share)

        # Rewards by policy (for the lift measurement).
        rows = db_module.query(
            app.conn,
            "SELECT c.strategy_context, p.reward FROM content c "
            "JOIN posts p ON p.content_id = c.id WHERE p.reward IS NOT NULL")
        for r in rows:
            sctx = db_module.loads(r["strategy_context"], {}) or {}
            key = "holdout" if sctx.get("policy") == "holdout" else "bandit"
            result.rewards_by_policy[key].append(r["reward"])
        result.lift = feedback.holdout_lift(app, product["id"], days=365)

        n = len(result.recommend_share)
        early_end = max(1, min(8, n))
        result.early_share = sum(result.recommend_share[:early_end]) / early_end
        if shift_at is not None and shift_at <= n:
            pre = result.recommend_share[max(0, shift_at - 10):shift_at]
            result.converged_share_pre_shift = sum(pre) / max(len(pre), 1)
            tail = result.recommend_share[-10:]
            result.converged_share_end = sum(tail) / max(len(tail), 1)
        else:
            tail = result.recommend_share[-10:]
            result.converged_share_pre_shift = sum(tail) / max(len(tail), 1)
            result.converged_share_end = result.converged_share_pre_shift
        app.close()
        return result
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
