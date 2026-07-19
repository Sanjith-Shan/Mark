"""Owner-taste learning — the human-feedback half of the evolution loop.

The mobile review feed (web /review) produces three signals per video:
a 1-10 rating, optional free-text feedback, and watch telemetry. This module
turns those into durable improvement, on three channels at once:

1. **Reward channel** — the rating becomes a graded reward ((rating-1)/9) fed
   into the SAME bandit arms engagement rewards hit, weighted by
   ``learning.human_reward_weight``. Credited once per content item (first
   rating), so re-rating never double-counts.
2. **Taste profile** — an LLM interpreter does attribute-level credit
   assignment ("the voiceover was flat", never "motivational videos are bad")
   and merges the resulting directives into ``taste_lessons``: evidence-
   weighted, embedding-deduped, contradiction-aware. The top lessons are
   injected into the strategist/writer/judge prompts on every generation.
3. **Experiment evidence** — ratings on experiment-tagged content accumulate
   per-variant; scientist.py opens/concludes the A/B tests.

Balance guarantee: a terrible rating lowers arm rewards *proportionally* and
adds *aspect-scoped* lessons — nothing here can delete a category. Bandit decay
plus experiment exploration re-opens any lane the owner's taste shifts back to.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from . import db as db_module
from . import prompts, store
from .app import App
from .constants import TASTE_ASPECTS
from .llm import LLM
from .schemas import AspectSignal, ReviewInterpretation
from .vectors import cosine_to_matrix


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Review recording (one row per content item, upserted)
# --------------------------------------------------------------------------- #
def get_review(app: App, content_id: int) -> Optional[dict]:
    row = db_module.query_one(app.conn, "SELECT * FROM reviews WHERE content_id = ?",
                              (content_id,))
    return dict(row) if row else None


def record_review(app: App, content: dict, *, rating: Optional[int] = None,
                  feedback: Optional[str] = None, action: Optional[str] = None,
                  watch_seconds: Optional[float] = None,
                  video_duration: Optional[float] = None,
                  replays: Optional[int] = None,
                  completed: Optional[bool] = None) -> tuple[dict, bool]:
    """Upsert the owner's review of one content item — ATOMICALLY.

    Concurrent submissions are the normal case (a telemetry flush racing a
    rating POST from the phone, or a double-tap sending two rating requests),
    so every step is a single conflict-safe SQL statement rather than
    check-then-act in Python:

    * the row is created with ``ON CONFLICT DO NOTHING`` (no IntegrityError
      race on UNIQUE(content_id));
    * ``first_rating`` — the exactly-once bandit-credit gate — is derived from
      the rowcount of a conditional ``UPDATE … WHERE rating IS NULL``, which
      only ONE writer can ever win.

    Returns (review, first_rating).
    """
    if rating is not None:
        rating = max(1, min(int(rating), 10))
    now = _now()
    conn = app.conn
    conn.execute(
        "INSERT INTO reviews (content_id, product_id, platform, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(content_id) DO NOTHING",
        (content["id"], content["product_id"], content["platform"], now))

    first_rating = False
    if rating is not None:
        cur = conn.execute(
            "UPDATE reviews SET rating = ?, rated_at = ?, updated_at = ? "
            "WHERE content_id = ? AND rating IS NULL",
            (rating, now, now, content["id"]))
        first_rating = cur.rowcount == 1
        if not first_rating:  # re-rate: latest value wins, no re-credit
            conn.execute(
                "UPDATE reviews SET rating = ?, rated_at = ?, updated_at = ? "
                "WHERE content_id = ?",
                (rating, now, now, content["id"]))

    sets: list[str] = []
    params: list = []
    if feedback is not None and feedback.strip():
        # Append rather than overwrite — every note the owner wrote matters.
        note = feedback.strip()
        sets.append("feedback = CASE WHEN feedback IS NULL OR feedback = '' "
                    "THEN ? ELSE feedback || char(10) || ? END")
        params += [note, note]
    if action is not None:
        sets.append("action = ?")
        params.append(action)
    if watch_seconds is not None:
        sets.append("watch_seconds = MAX(COALESCE(watch_seconds, 0), ?)")
        params.append(float(watch_seconds))
    if video_duration:
        sets.append("video_duration = ?")
        params.append(float(video_duration))
    if replays is not None:
        sets.append("replays = MAX(COALESCE(replays, 0), ?)")
        params.append(int(replays))
    if completed:
        sets.append("completed = 1")
    if sets:
        sets.append("updated_at = ?")
        params.append(now)
        conn.execute(f"UPDATE reviews SET {', '.join(sets)} WHERE content_id = ?",
                     params + [content["id"]])
    conn.commit()
    return get_review(app, content["id"]), first_rating


# --------------------------------------------------------------------------- #
# Channel 1: rating → bandit reward
# --------------------------------------------------------------------------- #
def rating_reward(rating: int) -> float:
    """Map 1..10 to [0, 1]. 5-6 straddles baseline (0.5), matching the graded
    engagement-reward scale so both channels move the same posteriors."""
    return (max(1, min(int(rating), 10)) - 1) / 9.0


def credit_bandit(app: App, content: dict, rating: int) -> float:
    from .learning import bandit

    reward = rating_reward(rating)
    weight = float(app.settings.learning.human_reward_weight)
    if weight > 0:
        bandit.update_from_content(app, content, reward, weight=weight)
    return reward


# --------------------------------------------------------------------------- #
# Channel 2: feedback text → interpreter → taste lessons
# --------------------------------------------------------------------------- #
def interpret_review(app: App, llm: LLM, product: dict, content: dict,
                     review: dict, note: Optional[str] = None) -> ReviewInterpretation:
    """Interpret ONE review submission. ``note`` is the NEW note to interpret;
    earlier accumulated notes are shown as already-processed context only, so
    re-submitting feedback never double-counts old evidence into lessons."""
    sctx = db_module.loads(content.get("strategy_context"), {}) or {}
    interp = llm.parse(
        prompts.taste_interpreter_system(product),
        prompts.taste_interpreter_user(content, review, sctx, note=note),
        ReviewInterpretation,
        model=app.settings.llm.judge_model,
        temperature=0.2,
        product_id=product["id"], content_id=content["id"],
        mock_factory=lambda: _mock_interpretation(review, note),
    )
    # Vocabulary guard — free-typed aspects would fragment the profile.
    for s in interp.signals:
        if s.aspect not in TASTE_ASPECTS:
            s.aspect = "other"
        if s.polarity not in ("avoid", "prefer"):
            s.polarity = "avoid"
    interp.signals = [s for s in interp.signals if s.directive.strip()]
    return interp


def _mock_interpretation(review: dict, note: Optional[str] = None) -> ReviewInterpretation:
    """Offline path: carry the owner's literal note as one un-generalized signal
    so the full loop (record → learn → inject) works without an API key."""
    text = (note or review.get("feedback") or "").strip()
    if not text:
        return ReviewInterpretation(summary="Rating recorded; no text feedback.")
    rating = review.get("rating")
    polarity = "prefer" if (rating or 0) >= 7 else "avoid"
    return ReviewInterpretation(
        summary=f"Owner note: {text[:120]}",
        signals=[AspectSignal(aspect="other", polarity=polarity,
                              directive=f"Owner said: {text[:200]}",
                              severity=0.6, generalizable=True)],
    )


def merge_lessons(app: App, llm: LLM, product_id: str, review: dict,
                  interp: ReviewInterpretation) -> list[dict]:
    """Fold interpreter signals into the persistent taste profile.

    Same-direction near-duplicates gain support; opposite-direction near-
    duplicates gain contradictions (and retire once contradictions outweigh
    support) — that's how the profile tracks a taste that CHANGES.
    """
    threshold = float(app.settings.learning.taste_merge_threshold)
    changed: list[dict] = []
    active = [dict(r) for r in db_module.query(
        app.conn,
        "SELECT * FROM taste_lessons WHERE product_id = ? AND status = 'active'",
        (product_id,))]

    for sig in interp.signals:
        if not sig.generalizable:
            continue
        vec = llm.embed_one(sig.directive, product_id=product_id)
        match, match_sim = None, 0.0
        # Same aspect AND same embedding dimension (mock vs live vectors mix
        # freely in a dev database — never stack mismatched dims).
        candidates = [l for l in active
                      if l["aspect"] == sig.aspect and l["embedding"]
                      and len(l["embedding"]) == vec.nbytes]
        if candidates:
            mat = np.stack([np.frombuffer(l["embedding"], dtype=np.float32)
                            for l in candidates])
            sims = cosine_to_matrix(vec, mat)
            i = int(np.argmax(sims))
            if float(sims[i]) >= threshold:
                match, match_sim = candidates[i], float(sims[i])

        if match is not None:
            src = db_module.loads(match.get("source_review_ids"), []) or []
            if review["id"] not in src:
                src.append(review["id"])
            if match["polarity"] == sig.polarity:
                support = match["support"] + 1
                contradictions = match["contradictions"]
            else:
                support = match["support"]
                contradictions = match["contradictions"] + 1
            confidence = support / (support + contradictions + 1)
            fields = dict(support=support, contradictions=contradictions,
                          confidence=round(confidence, 3),
                          source_review_ids=src,
                          updated_at=_now(), last_evidence_at=_now())
            # Retire once disagreement catches up with agreement (2+ each):
            # contradictions are newer evidence by construction, so an even
            # split means the owner's taste has moved on.
            if contradictions >= support and contradictions >= 2:
                fields["status"] = "retired"
                fields["retired_reason"] = "contradicted by newer owner feedback"
            db_module.update(app.conn, "taste_lessons", match["id"], **fields)
            changed.append({**match, **fields, "merged": True, "similarity": match_sim})
        else:
            confidence = round(min(0.6, 0.25 + 0.35 * sig.severity), 3)
            lesson_id = db_module.insert(
                app.conn, "taste_lessons",
                product_id=product_id, aspect=sig.aspect, polarity=sig.polarity,
                directive=sig.directive.strip(),
                scope_platform=sig.scope_platform or None,
                scope_strategy=sig.scope_strategy or None,
                scope_content_type=sig.scope_content_type or None,
                confidence=confidence, support=1, contradictions=0,
                source_review_ids=[review["id"]],
                embedding=vec.astype(np.float32).tobytes(),
                updated_at=_now(), last_evidence_at=_now(),
            )
            changed.append({"id": lesson_id, "aspect": sig.aspect,
                            "polarity": sig.polarity, "directive": sig.directive,
                            "confidence": confidence, "merged": False})
    return changed


def decay_stale_lessons(app: App, product_id: str, stale_days: int = 60) -> int:
    """Weekly maintenance: lessons with no fresh evidence slowly lose confidence
    and retire below 0.15 — the profile stays current, never a fossil record."""
    rows = db_module.query(
        app.conn,
        "SELECT id, confidence FROM taste_lessons "
        "WHERE product_id = ? AND status = 'active' "
        "AND COALESCE(last_evidence_at, created_at) <= datetime('now', ?)",
        (product_id, f"-{int(stale_days)} days"))
    retired = 0
    for r in rows:
        conf = round(float(r["confidence"]) * 0.9, 3)
        fields: dict = {"confidence": conf, "updated_at": _now()}
        if conf < 0.15:
            fields["status"] = "retired"
            fields["retired_reason"] = "stale — no supporting evidence in months"
            retired += 1
        db_module.update(app.conn, "taste_lessons", r["id"], **fields)
    return retired


# --------------------------------------------------------------------------- #
# Prompt injection
# --------------------------------------------------------------------------- #
def active_lessons(app: App, product_id: str, platform: Optional[str] = None,
                   strategy_id: Optional[str] = None,
                   content_type: Optional[str] = None,
                   limit: Optional[int] = None,
                   any_scope: bool = False) -> list[dict]:
    """Active lessons for a generation slot.

    Generation semantics: a None scope arg means "this dimension is unknown",
    so lessons scoped on it are EXCLUDED (a carousel-scoped lesson must not
    steer a video draft). Evidence semantics (``any_scope=True``, used by the
    scientist/dashboard): no scope filtering at all — scoped lessons must be
    visible or they could never be audited or retired.
    """
    limit = limit or int(app.settings.learning.taste_max_lessons)
    scope_sql = ("" if any_scope else
                 "AND (scope_platform IS NULL OR scope_platform = ?) "
                 "AND (scope_strategy IS NULL OR scope_strategy = ?) "
                 "AND (scope_content_type IS NULL OR scope_content_type = ?) ")
    params: list = [product_id]
    if not any_scope:
        params += [platform or "", strategy_id or "", content_type or ""]
    rows = db_module.query(
        app.conn,
        f"SELECT * FROM taste_lessons WHERE product_id = ? AND status = 'active' "
        f"{scope_sql}ORDER BY confidence DESC, support DESC LIMIT ?",
        params + [limit])
    return [dict(r) for r in rows]


def prompt_block(app: App, product: dict, platform: Optional[str] = None,
                 strategy_id: Optional[str] = None,
                 content_type: Optional[str] = None) -> str:
    """The OWNER TASTE PROFILE block injected into strategist/writer/judge."""
    lessons = active_lessons(app, product["id"], platform=platform,
                             strategy_id=strategy_id, content_type=content_type)
    if not lessons:
        return ""
    lines = []
    for l in lessons:
        tag = "PREFER" if l["polarity"] == "prefer" else "AVOID"
        conf = "strong" if l["confidence"] >= 0.6 else "moderate" if l["confidence"] >= 0.35 else "tentative"
        lines.append(f"- [{tag} · {l['aspect']} · {conf}] {l['directive']}")
    return ("\nOWNER TASTE PROFILE (learned from the owner's direct ratings and "
            "notes on past drafts — this is the person who approves everything; "
            "weigh these heavily, strongest first):\n" + "\n".join(lines))


# --------------------------------------------------------------------------- #
# Orchestration — called by the learn job after every review submission
# --------------------------------------------------------------------------- #
def process_review(app: App, llm: LLM, content_id: int,
                   new_rating: bool = False,
                   new_feedback: Optional[str] = None) -> dict:
    """Turn one review submission into learning. Returns a plain-language
    summary of what changed (shown in the app as "what the AI took away")."""
    content = store.get_content(app.conn, content_id)
    review = get_review(app, content_id)
    if not content or not review:
        return {"learned": []}
    product = store.get_product(app.conn, content["product_id"])
    learned: list[str] = []
    payload: dict = {"summary": "", "signals": [], "reward": None,
                     "experiment": None, "lessons_changed": []}

    # 1) Reward channel — first rating only (re-rates never double-credit).
    if new_rating and review.get("rating") is not None:
        reward = credit_bandit(app, content, review["rating"])
        payload["reward"] = round(reward, 3)
        sctx = db_module.loads(content.get("strategy_context"), {}) or {}
        credited = [str(v) for v in (
            sctx.get("strategy"), sctx.get("hook_style"), sctx.get("tone"),
            sctx.get("humor_mechanism"), sctx.get("emotional_target")) if v]
        learned.append(
            f"Rated {review['rating']}/10 → reward {reward:.2f} credited to "
            f"{content['platform']} arms ({', '.join(credited[:5]) or 'content choices'}).")

        # Experiment attribution — the rating is a sample for its variant.
        exp = sctx.get("experiment") or {}
        if exp.get("id"):
            payload["experiment"] = exp
            learned.append(
                f"Counted toward experiment #{exp['id']} "
                f"(variant “{exp.get('variant')}” — {exp.get('aspect', 'creative')} test).")

    # 2) Interpreter channel — only when there's text to interpret. Only the
    # NEW note becomes evidence; prior notes ride along as context.
    if new_feedback and new_feedback.strip():
        interp = interpret_review(app, llm, product, content, review,
                                  note=new_feedback.strip())
        db_module.insert(app.conn, "review_learnings",
                         review_id=review["id"], content_id=content_id,
                         product_id=product["id"],
                         payload=json.dumps(interp.model_dump()))
        payload["summary"] = interp.summary
        payload["signals"] = [s.model_dump() for s in interp.signals]
        if interp.summary:
            learned.append(interp.summary)
        changed = merge_lessons(app, llm, product["id"], review, interp)
        payload["lessons_changed"] = [
            {k: c.get(k) for k in ("id", "aspect", "polarity", "directive",
                                   "confidence", "merged", "status")}
            for c in changed]
        for c in changed:
            verb = ("reinforced" if c.get("merged") and c.get("status") != "retired"
                    else "retired" if c.get("status") == "retired" else "added")
            learned.append(f"Taste lesson {verb} [{c['aspect']}]: {c['directive'][:120]}")
        if interp.experiment_worthy:
            payload["experiment_worthy"] = interp.experiment_worthy

    db_module.log_activity(app.conn, "learn",
                           "Review processed: " + (learned[0] if learned else "telemetry only"),
                           product_id=product["id"], content_id=content_id)
    return {"learned": learned, "payload": payload}


# --------------------------------------------------------------------------- #
# Dashboard queries
# --------------------------------------------------------------------------- #
def rating_trend(app: App, product_id: Optional[str] = None,
                 days: int = 120) -> list[dict]:
    """Weekly average owner rating — the "is it getting better?" line."""
    where = "AND product_id = ?" if product_id else ""
    params: list = [f"-{int(days)} days"] + ([product_id] if product_id else [])
    rows = db_module.query(
        app.conn,
        f"""
        SELECT strftime('%Y-%W', COALESCE(rated_at, created_at)) AS week,
               MIN(date(COALESCE(rated_at, created_at))) AS week_start,
               AVG(rating) AS avg_rating, COUNT(*) AS n
        FROM reviews
        WHERE rating IS NOT NULL
          AND COALESCE(rated_at, created_at) >= datetime('now', ?) {where}
        GROUP BY week ORDER BY week
        """, params)
    return [{"week": r["week"], "week_start": r["week_start"],
             "avg_rating": round(r["avg_rating"], 2), "n": r["n"]} for r in rows]


def aspect_report(app: App, product_id: str) -> list[dict]:
    """Mean rating grouped by the creative choices recorded in strategy_context —
    the scientist's raw evidence table."""
    out = []
    for field in ("strategy", "hook_style", "tone", "humor_mechanism",
                  "emotional_target"):
        rows = db_module.query(
            app.conn,
            f"""
            SELECT json_extract(c.strategy_context, '$.{field}') AS value,
                   AVG(r.rating) AS avg_rating, COUNT(*) AS n
            FROM reviews r JOIN content c ON c.id = r.content_id
            WHERE r.product_id = ? AND r.rating IS NOT NULL
              AND json_extract(c.strategy_context, '$.{field}') IS NOT NULL
            GROUP BY value HAVING n >= 1 ORDER BY avg_rating DESC
            """, (product_id,))
        for r in rows:
            out.append({"dimension": field, "value": r["value"],
                        "avg_rating": round(r["avg_rating"], 2), "n": r["n"]})
    return out
