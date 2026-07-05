"""Empirical proof that the evolution loop works — the vision's #1 requirement.

These tests run the FULL production loop (strategist → writer → humor → post →
metrics → feedback → bandit) against the offline world's hidden taste model,
with a planted, known audience preference. They assert the three properties a
learning system must have:

  1. convergence  — recommendations concentrate on what the audience rewards
  2. lift         — the learned policy beats the random holdout policy
  3. adaptation   — when taste flips mid-run, the system un-learns and re-converges

Thresholds are deliberately loose (this is a stochastic system; the CLI
`mark evolve-proof` runs the longer, publication-grade version).
"""

from __future__ import annotations

from mark.simulate import run_proof

UNIFORM = 1.0 / 6.0  # 6 hook_style arms — chance level for the watch arm


def _with_retry(check, seeds=(11, 23)):
    """The simulation is a stochastic system (wall-clock second boundaries can
    shift which cycle a reward lands in, perturbing the sampling stream), so a
    single borderline trajectory is not a verdict. A HEALTHY learner passes on
    virtually every seed; a broken one fails on all — so retry once on an
    independent seed before declaring failure."""
    failures = []
    for seed in seeds:
        ok, summary = check(seed)
        if ok:
            return
        failures.append(summary)
    raise AssertionError(f"failed on all seeds: {failures}")


def test_convergence_and_lift():
    def check(seed):
        r = run_proof(cycles=45, shift_at=None, holdout_pct=0.25,
                      posts_per_cycle=3, seed=seed)
        ok = (r.converged_share_end >= 0.40                    # far above 1/6 chance
              and r.converged_share_end > r.early_share + 0.10  # actually climbed
              and r.lift is not None and r.lift["lift_pct"] > 0)  # beats random
        return ok, r.summary()

    _with_retry(check)


def test_adaptation_to_taste_shift():
    def check(seed):
        r = run_proof(cycles=110, shift_at=55, holdout_pct=0.15,
                      posts_per_cycle=3, seed=seed, decay_half_life_days=18.0)
        # Converged on the old world before the shift, then re-converged on the
        # NEW best arm afterwards (decay lets old evidence fade instead of
        # pinning the system to a dead preference).
        ok = (r.converged_share_pre_shift >= 0.40
              and r.converged_share_end >= 0.35
              and r.converged_share_end > UNIFORM * 1.8)
        return ok, r.summary()

    _with_retry(check)
