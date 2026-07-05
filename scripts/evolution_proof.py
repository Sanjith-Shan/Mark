#!/usr/bin/env python3
"""Run the full evolution proof and print a report.

Usage: python scripts/evolution_proof.py [--cycles 140] [--shift-at 70]

Plants a known audience taste in the offline world, runs the complete
production loop for N cycles, inverts the taste mid-run, and reports:
convergence, holdout lift, and post-shift re-convergence.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mark.simulate import PLANTED_TASTE, WATCH_ARM, run_proof  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=140)
    ap.add_argument("--shift-at", type=int, default=70)
    ap.add_argument("--posts-per-cycle", type=int, default=3)
    ap.add_argument("--holdout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    arm_type, best, worst = WATCH_ARM
    print(f"Planted taste: {json.dumps(PLANTED_TASTE, indent=2)}")
    print(f"Watching arm '{arm_type}': best={best!r}, post-shift best={worst!r}\n")

    t0 = time.time()

    def on_cycle(cycle: int, share: float) -> None:
        if cycle % 10 == 0:
            bar = "#" * int(share * 40)
            print(f"  cycle {cycle:>4}  best-arm share {share:0.2f}  {bar}")

    r = run_proof(cycles=args.cycles, shift_at=args.shift_at,
                  holdout_pct=args.holdout, posts_per_cycle=args.posts_per_cycle,
                  seed=args.seed, on_cycle=on_cycle)
    dt = time.time() - t0

    print(f"\n=== EVOLUTION PROOF ({args.cycles} cycles in {dt:.1f}s) ===")
    print(json.dumps(r.summary(), indent=2))

    ok = True
    chance = 1.0 / 6.0
    checks = [
        ("convergence (pre-shift best-arm share ≥ 2x chance)",
         r.converged_share_pre_shift >= chance * 2),
        ("lift (bandit beats random holdout)",
         bool(r.lift and r.lift["lift_pct"] > 0)),
        ("adaptation (post-shift new-best share ≥ 2x chance)",
         args.shift_at is None or r.converged_share_end >= chance * 2),
    ]
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\nVERDICT:", "the learning loop demonstrably converges, lifts, and adapts."
          if ok else "FAILED — see numbers above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
