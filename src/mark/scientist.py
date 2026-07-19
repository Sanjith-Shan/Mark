"""The scientist — creative experiments that isolate WHY content lands or flops.

The taste channel (taste.py) answers "what does the owner dislike"; this module
answers "which specific choice fixes it". It runs attribute-level A/B tests:

  * an experiment varies exactly ONE aspect (pacing, hook length, voiceover
    energy, ...) across 2-3 variants, each a directive injected into the writer
    prompt at generation time;
  * assignment is deterministic round-robin (fewest-assigned variant first) and
    recorded in ``strategy_context.experiment`` so every owner rating is a
    per-variant sample;
  * conclusion is computed in CODE (min samples per variant + a mean-rating
    margin), never vibes: a clear winner becomes a "prefer" taste lesson, a
    wash is recorded honestly as no-difference;
  * an LLM scientist agent decides WHICH experiments are worth running. It
    reads the evidence (per-aspect rating table, active lessons, running
    experiments, recent reviews) plus its own lab notebook — the notebook is
    its memory across runs, so investigations build on each other instead of
    restarting from zero.

Runs after review bursts (debounced) and in the weekly feedback loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from . import db as db_module
from . import prompts, taste
from .app import App
from .constants import TASTE_ASPECTS
from .llm import LLM
from .schemas import (ExperimentProposal, ExperimentVariant, ScientistPlan)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Experiment CRUD + assignment
# --------------------------------------------------------------------------- #
def running_experiments(app: App, product_id: str) -> list[dict]:
    rows = db_module.query(
        app.conn,
        "SELECT * FROM creative_experiments WHERE product_id = ? AND status = 'running' "
        "ORDER BY started_at", (product_id,))
    return [_exp_out(r) for r in rows]


def get_experiment(app: App, experiment_id: int) -> Optional[dict]:
    row = db_module.query_one(app.conn, "SELECT * FROM creative_experiments WHERE id = ?",
                              (experiment_id,))
    return _exp_out(row) if row else None


def _exp_out(row) -> dict:
    out = dict(row)
    out["variants"] = db_module.loads(out.get("variants"), []) or []
    out["assignments"] = db_module.loads(out.get("assignments"), {}) or {}
    return out


def create_experiment(app: App, product_id: str, proposal: ExperimentProposal) -> Optional[int]:
    variants = [v for v in proposal.variants if v.key.strip() and v.directive.strip()]
    if len(variants) < 2:
        return None
    aspect = proposal.aspect if proposal.aspect in TASTE_ASPECTS else "other"
    exp_id = db_module.insert(
        app.conn, "creative_experiments",
        product_id=product_id, aspect=aspect,
        hypothesis=proposal.hypothesis.strip() or f"{aspect} variation test",
        variants=[v.model_dump() for v in variants],
        scope_platform=proposal.scope_platform or None,
        scope_strategy=proposal.scope_strategy or None,
        scope_content_type=proposal.scope_content_type or None,
        min_samples=max(1, int(app.settings.learning.experiment_min_samples)),
        assignments={v.key: 0 for v in variants},
        rationale=proposal.rationale.strip(),
    )
    db_module.log_activity(app.conn, "experiment",
                           f"Opened experiment #{exp_id}: {proposal.hypothesis[:100]}",
                           product_id=product_id, level="success")
    return exp_id


def assign_variant(app: App, product: dict, platform: str,
                   strategy_id: Optional[str],
                   content_type: Optional[str]) -> Optional[dict]:
    """Pick the matching running experiment with the fewest total assignments,
    then its least-assigned variant. Returns the strategy_context tag + the
    writer directive, or None when no experiment applies."""
    matching = [
        e for e in running_experiments(app, product["id"])
        if (not e["scope_platform"] or e["scope_platform"] == platform)
        and (not e["scope_strategy"] or e["scope_strategy"] == (strategy_id or ""))
        and (not e["scope_content_type"] or e["scope_content_type"] == (content_type or ""))
    ]
    if not matching:
        return None
    exp = min(matching, key=lambda e: sum(e["assignments"].values()))
    counts = {v["key"]: int(exp["assignments"].get(v["key"], 0)) for v in exp["variants"]}
    variant_key = min(counts, key=lambda k: counts[k])
    directive = next(v["directive"] for v in exp["variants"] if v["key"] == variant_key)
    counts[variant_key] += 1
    db_module.update(app.conn, "creative_experiments", exp["id"], assignments=counts)
    return {"id": exp["id"], "variant": variant_key, "aspect": exp["aspect"],
            "hypothesis": exp["hypothesis"], "directive": directive}


# --------------------------------------------------------------------------- #
# Measurement + deterministic conclusion
# --------------------------------------------------------------------------- #
def variant_stats(app: App, experiment: dict) -> dict[str, dict]:
    """Per-variant owner-rating samples for one experiment. Engagement reward is
    reported alongside when available (secondary evidence, never the decider)."""
    rows = db_module.query(
        app.conn,
        """
        SELECT json_extract(c.strategy_context, '$.experiment.variant') AS variant,
               r.rating, p.reward
        FROM content c
        LEFT JOIN reviews r ON r.content_id = c.id
        LEFT JOIN posts p ON p.content_id = c.id
        WHERE json_extract(c.strategy_context, '$.experiment.id') = ?
        """, (experiment["id"],))
    stats: dict[str, dict] = {
        v["key"]: {"generated": int(experiment["assignments"].get(v["key"], 0)),
                   "ratings": [], "rewards": []}
        for v in experiment["variants"]}
    for r in rows:
        s = stats.get(r["variant"])
        if s is None:
            continue
        if r["rating"] is not None:
            s["ratings"].append(r["rating"])
        if r["reward"] is not None:
            s["rewards"].append(r["reward"])
    for s in stats.values():
        s["n"] = len(s["ratings"])
        s["mean_rating"] = round(sum(s["ratings"]) / s["n"], 2) if s["n"] else None
        s["mean_reward"] = (round(sum(s["rewards"]) / len(s["rewards"]), 3)
                            if s["rewards"] else None)
        del s["ratings"], s["rewards"]
    return stats


def conclude_ready(app: App, llm: LLM, product: dict) -> list[dict]:
    """Conclude every running experiment whose variants all reached min_samples.
    Deterministic: winner iff the top-vs-runner-up mean-rating gap ≥ margin."""
    margin = float(app.settings.learning.experiment_margin)
    concluded = []
    for exp in running_experiments(app, product["id"]):
        stats = variant_stats(app, exp)
        # max(1, …) guards a legacy/edited min_samples of 0 — a zero-rating
        # variant has mean_rating None and must never reach the ranking.
        if not stats or any(s["n"] < max(1, exp["min_samples"]) for s in stats.values()):
            continue
        ranked = sorted(stats.items(),
                        key=lambda kv: kv[1]["mean_rating"] or 0, reverse=True)
        (best_key, best), (second_key, second) = ranked[0], ranked[1]
        gap = round(best["mean_rating"] - second["mean_rating"], 2)
        if gap >= margin:
            winner = best_key
            conclusion = (
                f"“{best_key}” won: mean owner rating {best['mean_rating']} vs "
                f"{second['mean_rating']} for “{second_key}” (gap {gap}, "
                f"n={best['n']}/{second['n']}). Hypothesis: {exp['hypothesis']}")
        else:
            winner = None
            conclusion = (
                f"No meaningful difference (top gap {gap} < {margin} between "
                f"“{best_key}” {best['mean_rating']} and “{second_key}” "
                f"{second['mean_rating']}). The {exp['aspect']} choice tested here "
                "doesn't drive the owner's rating — look elsewhere.")
        db_module.update(app.conn, "creative_experiments", exp["id"],
                         status="concluded", winner=winner, conclusion=conclusion,
                         ended_at=_now())
        db_module.log_activity(app.conn, "experiment",
                               f"Concluded experiment #{exp['id']}: {conclusion[:140]}",
                               product_id=product["id"], level="success")
        # A clear winner becomes a durable "prefer" lesson so the finding keeps
        # steering generation after the experiment closes.
        if winner:
            directive = next(v["directive"] for v in exp["variants"] if v["key"] == winner)
            try:
                vec = llm.embed_one(directive, product_id=product["id"])
                db_module.insert(
                    app.conn, "taste_lessons",
                    product_id=product["id"], aspect=exp["aspect"] or "other",
                    polarity="prefer", directive=directive,
                    scope_platform=exp["scope_platform"],
                    scope_strategy=exp["scope_strategy"],
                    scope_content_type=exp["scope_content_type"],
                    confidence=0.65, support=max(2, best["n"]),
                    contradictions=0,
                    source_review_ids=[],
                    embedding=vec.astype("float32").tobytes(),
                    updated_at=_now(), last_evidence_at=_now())
            except Exception:
                pass
        concluded.append({**exp, "status": "concluded", "winner": winner,
                          "conclusion": conclusion, "stats": stats})
    return concluded


# --------------------------------------------------------------------------- #
# The scientist agent
# --------------------------------------------------------------------------- #
def notebook(app: App, product_id: str, limit: int = 8) -> list[dict]:
    rows = db_module.query(
        app.conn,
        "SELECT * FROM lab_notebook WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
        (product_id, limit))
    return [dict(r) for r in rows]


def _recent_reviews(app: App, product_id: str, limit: int = 15) -> list[dict]:
    rows = db_module.query(
        app.conn,
        """
        SELECT r.rating, r.feedback, r.watch_seconds, r.video_duration, r.completed,
               c.platform, c.hook, c.strategy_context
        FROM reviews r JOIN content c ON c.id = r.content_id
        WHERE r.product_id = ? AND (r.rating IS NOT NULL OR r.feedback IS NOT NULL)
        ORDER BY r.updated_at DESC LIMIT ?
        """, (product_id, limit))
    out = []
    for r in rows:
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        out.append({"rating": r["rating"], "feedback": r["feedback"],
                    "platform": r["platform"], "hook": r["hook"],
                    "strategy": sctx.get("strategy"), "tone": sctx.get("tone"),
                    "hook_style": sctx.get("hook_style"),
                    "watch_pct": round(100 * (r["watch_seconds"] or 0)
                                       / max(r["video_duration"] or 0, 1e-9), 1)
                    if r["video_duration"] else None,
                    "experiment": sctx.get("experiment")})
    return out


def should_run(app: App, product_id: str) -> bool:
    """Debounce: run once enough NEW reviewed evidence accumulated."""
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM reviews WHERE product_id = ? "
        "AND (rating IS NOT NULL OR feedback IS NOT NULL)", (product_id,))
    n = row["n"] if row else 0
    last = int(db_module.get_meta(app.conn, f"scientist_reviews_at:{product_id}", "0") or 0)
    return (n - last) >= int(app.settings.learning.scientist_min_new_reviews)


def run(app: App, llm: LLM, product: dict, force: bool = False) -> Optional[dict]:
    """One investigation step: conclude what's ready, then let the scientist
    read the evidence + its notebook and decide what to test next."""
    product_id = product["id"]
    if not force and not should_run(app, product_id):
        return None

    concluded = conclude_ready(app, llm, product)
    running = running_experiments(app, product_id)
    for e in running:
        e["stats"] = variant_stats(app, e)
    evidence = {
        "aspect_report": taste.aspect_report(app, product_id),
        "recent_reviews": _recent_reviews(app, product_id),
        "active_lessons": [
            {k: l[k] for k in ("id", "aspect", "polarity", "directive", "confidence",
                               "support", "contradictions")}
            # any_scope: scoped lessons must be visible as evidence or the
            # scientist could never audit or retire them.
            for l in taste.active_lessons(app, product_id, limit=20, any_scope=True)],
        "running_experiments": [
            {k: e[k] for k in ("id", "aspect", "hypothesis", "variants",
                               "scope_platform", "stats")}
            for e in running],
        "just_concluded": [
            {k: c[k] for k in ("id", "hypothesis", "winner", "conclusion")}
            for c in concluded],
        "rating_trend": taste.rating_trend(app, product_id, days=60),
    }
    plan = llm.parse(
        prompts.scientist_system(product),
        prompts.scientist_user(evidence, notebook(app, product_id)),
        ScientistPlan,
        model=app.settings.llm.judge_model,
        temperature=0.4,
        product_id=product_id,
        mock_factory=lambda: _mock_plan(evidence, running),
    )

    opened: list[int] = []
    slots = int(app.settings.learning.max_active_experiments) - len(running)
    for proposal in plan.proposals[:max(0, slots)]:
        exp_id = create_experiment(app, product_id, proposal)
        if exp_id:
            opened.append(exp_id)
    for ab in plan.abandon:
        exp = get_experiment(app, ab.experiment_id)
        if exp and exp["product_id"] == product_id and exp["status"] == "running":
            db_module.update(app.conn, "creative_experiments", exp["id"],
                             status="abandoned",
                             conclusion=f"Abandoned: {ab.reason}"[:400], ended_at=_now())
    for lesson_id in plan.retire_lesson_ids:
        row = db_module.query_one(
            app.conn, "SELECT id FROM taste_lessons WHERE id = ? AND product_id = ?",
            (lesson_id, product_id))
        if row:
            db_module.update(app.conn, "taste_lessons", lesson_id,
                             status="retired",
                             retired_reason="scientist: contradicted by rating data",
                             updated_at=_now())

    entry = plan.notebook_entry.strip() or "Reviewed evidence; no changes warranted."
    db_module.insert(app.conn, "lab_notebook", product_id=product_id, entry=entry,
                     payload=json.dumps({
                         "opened": opened,
                         "abandoned": [a.experiment_id for a in plan.abandon],
                         "retired_lessons": plan.retire_lesson_ids,
                         "concluded": [c["id"] for c in concluded]}))
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM reviews WHERE product_id = ? "
        "AND (rating IS NOT NULL OR feedback IS NOT NULL)", (product_id,))
    db_module.set_meta(app.conn, f"scientist_reviews_at:{product_id}",
                       str(row["n"] if row else 0))
    db_module.log_activity(app.conn, "experiment", f"Scientist: {entry[:140]}",
                           product_id=product_id)
    return {"notebook_entry": entry, "opened": opened,
            "concluded": [c["id"] for c in concluded]}


def _mock_plan(evidence: dict, running: list[dict]) -> ScientistPlan:
    """Offline scientist: one deterministic, defensible move — if a dimension
    value is clearly under-performing with enough samples and no experiment is
    already running, open a two-variant test on the weakest aspect proxy."""
    if running:
        return ScientistPlan(notebook_entry="Experiments already running; waiting "
                                            "for samples before opening more.")
    weak = [a for a in evidence.get("aspect_report", [])
            if a["n"] >= 3 and (a["avg_rating"] or 10) <= 5]
    if not weak:
        return ScientistPlan(notebook_entry="Not enough rated evidence to justify "
                                            "a new experiment yet.")
    w = weak[0]
    return ScientistPlan(
        notebook_entry=(f"{w['dimension']}={w['value']} averages "
                        f"{w['avg_rating']}/10 over {w['n']} ratings — opening a "
                        "pacing/energy A/B to isolate whether execution (not the "
                        "category) is the problem."),
        proposals=[ExperimentProposal(
            aspect="pacing",
            hypothesis=(f"Low ratings on {w['value']} come from slow pacing, "
                        "not the content lane itself"),
            variants=[
                ExperimentVariant(key="fast_cuts",
                                  directive="Keep the video under 20 seconds, cut "
                                            "every 1-2 seconds, no dead air, land the "
                                            "hook inside the first second."),
                ExperimentVariant(key="steady_story",
                                  directive="Let the story breathe: 30-40 seconds, "
                                            "calm delivery, one clear narrative arc "
                                            "with a payoff at the end."),
            ],
            rationale=f"{w['dimension']}={w['value']} rated {w['avg_rating']}/10 (n={w['n']})",
        )],
    )
