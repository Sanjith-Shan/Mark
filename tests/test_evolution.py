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


def test_convergence_and_lift():
    r = run_proof(cycles=45, shift_at=None, holdout_pct=0.25,
                  posts_per_cycle=3, seed=11)
    # Convergence: final recommendation share of the planted-best arm must be
    # far above chance and clearly above where it started.
    assert r.converged_share_end >= 0.40, r.summary()
    assert r.converged_share_end > r.early_share + 0.10, r.summary()
    # Lift: learned policy beats random on graded reward.
    assert r.lift is not None, "no holdout posts — holdout policy not firing"
    assert r.lift["lift_pct"] > 0, r.summary()


def test_adaptation_to_taste_shift():
    r = run_proof(cycles=110, shift_at=55, holdout_pct=0.15,
                  posts_per_cycle=3, seed=11, decay_half_life_days=18.0)
    # Converged on the old world before the shift…
    assert r.converged_share_pre_shift >= 0.40, r.summary()
    # …and re-converged on the NEW best arm afterwards (decay lets old
    # evidence fade instead of pinning the system to a dead preference).
    assert r.converged_share_end >= 0.40, r.summary()
    assert r.converged_share_end > UNIFORM * 1.8, r.summary()
