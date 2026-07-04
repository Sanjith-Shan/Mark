"""The humor engine — makes drafts genuinely funny, not "funny"-labeled.

Pipeline (each step grounded in docs/research/humor-mechanics.md):

  1. VIOLATION SEARCH — list candidate "benign violations" about the topic and
     keep the strongest one that is both wrong enough and safe enough (BVT:
     laughs need simultaneous violation + benignness; corporate content dies
     because the violation gets sanded off).
  2. SCAFFOLDED FAN-OUT — one candidate per comedic persona, all built on the
     chosen violation with an explicit joke structure (target assumption /
     connector / reinterpretation / punch word). Personas force generation out
     of the model's safe high-probability center.
  3. PAIRWISE RANKING — winner-stays pairwise comparisons (pairwise preference
     beats absolute 1-10 scoring for humor). The judge also gates the winner on
     violation_strength and benignness — kills both failure modes (bland and
     off-brand).
  4. PREDICTABILITY FILTER — a model tries to complete the setup without seeing
     the punchline; if it guesses the ending, the joke is dead (surprisal is
     the measurable core of funny).
  5. APPLY — the surviving candidate replaces the draft's hook/caption/script.
     If nothing survives, the straight draft is returned unchanged: no joke
     beats a dead joke.

The chosen mechanism and persona are recorded on the draft so the bandit learns
which comedy structures actually land with this audience on each platform.
"""

from __future__ import annotations

import re
from typing import Optional

from . import db as db_module
from . import prompts
from .app import App
from .constants import HUMOR_MECHANISMS, HUMOR_PERSONAS
from .llm import LLM
from .schemas import (ContentDraft, GuessCheck, JokeCandidate, JokeCandidates,
                      PairwiseVerdict, Violation, ViolationSearch)


def specificity_bank(product: dict) -> list[str]:
    """Concrete artifacts of the audience's life (per-product, from YAML/DB).
    Specificity is the cheapest surprisal injector — vague input, vague comedy."""
    return db_module.loads(product.get("specificity_bank"), []) or []


def punch_up(
    app: App,
    llm: LLM,
    product: dict,
    platform: str,
    plan,
    draft: ContentDraft,
    *,
    level: str = "full",
    bandit_picks: Optional[dict] = None,
    character: Optional[dict] = None,
    content_id: Optional[int] = None,
) -> ContentDraft:
    """Run the comedy pipeline over a draft. Returns the funnier draft, or the
    original unchanged if no candidate survives QA."""
    cfg = app.settings.humor
    if not cfg.enabled or level == "none":
        return draft
    bandit_picks = bandit_picks or {}
    model = cfg.model or app.settings.llm.text_model
    n = max(2, int(cfg.candidates if level == "full" else cfg.candidates_light))
    bank = specificity_bank(product)

    # 1) Violation search.
    violation = _find_violation(app, llm, product, platform, plan, bank, model,
                                content_id=content_id)
    if violation is None:
        return draft

    # 2) Scaffolded fan-out across personas (bandit-picked persona always included).
    mechanism = _choose(bandit_picks.get("humor_mechanism"), HUMOR_MECHANISMS, plan.topic)
    personas = _persona_lineup(bandit_picks.get("humor_persona"), n)
    candidates = _fanout(app, llm, product, platform, plan, draft, violation,
                         personas, mechanism, bank, model, content_id=content_id)
    candidates = [c for c in candidates if _scaffold_complete(c)]
    if not candidates:
        return draft

    # 3) Pairwise winner-stays ranking with BVT gating on the champion.
    winner, verdict = _rank(app, llm, product, platform, candidates,
                            content_id=content_id, product_id=product["id"])
    if winner is None or verdict is None:
        return draft
    if verdict.violation_strength < cfg.min_violation or verdict.benignness < cfg.min_benignness:
        return draft  # bland or off-brand — ship the straight version instead

    # 4) Predictability filter: if the punchline is guessable, the joke is dead.
    if cfg.predictability_filter and _is_guessable(app, llm, winner, model,
                                                   content_id=content_id,
                                                   product_id=product["id"]):
        survivors = [c for c in candidates if c is not winner]
        winner = None
        for c in survivors:
            if not _is_guessable(app, llm, c, model, content_id=content_id,
                                 product_id=product["id"]):
                winner = c
                break
        if winner is None:
            return draft

    return _apply(draft, winner, plan)


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def _find_violation(app, llm, product, platform, plan, bank, model,
                    content_id=None) -> Optional[Violation]:
    result = llm.parse(
        prompts.violation_search_system(product, platform, bank),
        prompts.violation_search_user(plan.topic, plan.angle),
        ViolationSearch, model=model, temperature=0.95,
        product_id=product["id"], content_id=content_id,
        mock_factory=lambda: _mock_violations(plan),
    )
    cfg = app.settings.humor
    viable = [v for v in result.items
              if v.strength >= cfg.min_violation and v.benignness >= cfg.min_benignness]
    pool = viable or result.items
    if not pool:
        return None
    # Strongest violation that is still safe: maximize the BVT product.
    return max(pool, key=lambda v: v.strength * v.benignness)


def _persona_lineup(bandit_persona: Optional[str], n: int) -> list[str]:
    lineup = list(HUMOR_PERSONAS)
    if bandit_persona in lineup:
        lineup.remove(bandit_persona)
        lineup.insert(0, bandit_persona)
    return lineup[:n]


def _choose(bandit_value: Optional[str], pool: list[str], seed_text: str) -> str:
    if bandit_value in pool:
        return bandit_value
    return pool[abs(hash(seed_text)) % len(pool)]


def _fanout(app, llm, product, platform, plan, draft, violation, personas,
            mechanism, bank, model, content_id=None) -> list[JokeCandidate]:
    result = llm.parse(
        prompts.humor_fanout_system(product, platform, plan, violation,
                                    personas, mechanism, bank),
        prompts.humor_fanout_user(plan, draft),
        JokeCandidates, model=model, temperature=0.95,
        product_id=product["id"], content_id=content_id,
        mock_factory=lambda: _mock_candidates(draft, personas, mechanism),
    )
    return result.items


def _scaffold_complete(c: JokeCandidate) -> bool:
    """A candidate that can't name its own joke structure isn't a joke yet."""
    return bool(c.hook.strip() and c.caption.strip() and c.punch_word.strip()
                and c.target_assumption.strip() and c.reinterpretation.strip())


def _rank(app, llm, product, platform, candidates,
          content_id=None, product_id=None):
    """Winner-stays pairwise tournament. N-1 cheap judge calls. The judge is
    calibrated with real preference pairs mined from this account's own
    engagement history (the documented expert-level-ranking lever)."""
    from .learning import calibration

    calib = calibration.calibration_block(app, product["id"], platform)
    champion = candidates[0]
    verdict: Optional[PairwiseVerdict] = None
    for challenger in candidates[1:]:
        v = llm.parse(
            prompts.pairwise_judge_system(product, platform, calibration=calib),
            prompts.pairwise_judge_user(champion, challenger),
            PairwiseVerdict,
            model=app.settings.llm.judge_model, temperature=0.2,
            product_id=product_id, content_id=content_id,
            mock_factory=lambda: PairwiseVerdict(winner=0, violation_strength=0.7,
                                                 benignness=0.8, guessable=False,
                                                 reasoning="offline: keep champion"),
        )
        if v.winner == 1:
            champion = challenger
        verdict = v
    if verdict is None:  # single candidate — judge it against itself for the gate scores
        verdict = llm.parse(
            prompts.pairwise_judge_system(product, platform, calibration=calib),
            prompts.pairwise_judge_user(champion, champion),
            PairwiseVerdict,
            model=app.settings.llm.judge_model, temperature=0.2,
            product_id=product_id, content_id=content_id,
            mock_factory=lambda: PairwiseVerdict(winner=0, violation_strength=0.7,
                                                 benignness=0.8, guessable=False),
        )
    return champion, verdict


def _is_guessable(app, llm, candidate: JokeCandidate, model,
                  content_id=None, product_id=None) -> bool:
    """Have a model complete the setup without seeing the punch. If any
    completion lands on the punchline, the surprise is gone."""
    setup = _setup_without_punch(candidate)
    if not setup:
        return False
    result = llm.parse(
        prompts.guess_check_system(),
        f"SETUP:\n{setup}\n\nPredict 3 plausible final lines.",
        GuessCheck, model=model, temperature=0.9,
        product_id=product_id, content_id=content_id,
        mock_factory=lambda: GuessCheck(completions=["something predictable",
                                                     "a generic ending",
                                                     "an expected close"]),
    )
    punch = _normalize(candidate.punch_word or _last_line(candidate.caption))
    if not punch:
        return False
    punch_tokens = set(punch.split())
    for completion in result.completions:
        tokens = set(_normalize(completion).split())
        if punch_tokens and len(punch_tokens & tokens) / len(punch_tokens) >= 0.6:
            return True
    return False


def _apply(draft: ContentDraft, winner: JokeCandidate, plan) -> ContentDraft:
    draft.hook = winner.hook or draft.hook
    draft.caption = winner.caption or draft.caption
    if plan.content_type == "video" and winner.script:
        # A beat before the punch: keep the final line separated so TTS/captions
        # naturally pause before it (timing is half the mechanism).
        draft.script = _ensure_punch_beat(winner.script)
    draft.humor_mechanism = winner.mechanism or None
    draft.humor_persona = winner.persona or None
    return draft


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _last_line(text: str) -> str:
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _setup_without_punch(c: JokeCandidate) -> str:
    lines = [ln for ln in (c.caption or "").strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""
    return "\n".join(lines[:-1])


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def _ensure_punch_beat(script: str) -> str:
    lines = [ln for ln in script.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return script.strip()
    return "\n".join(lines[:-1]) + "\n\n" + lines[-1]


# --------------------------------------------------------------------------- #
# Offline mock factories (keep the whole pipeline exercised in tests)
# --------------------------------------------------------------------------- #
def _mock_violations(plan) -> ViolationSearch:
    return ViolationSearch(items=[
        Violation(violation=f"everyone pretends {plan.topic.lower()} is fine when it is "
                            "objectively absurd", strength=0.7, benignness=0.8,
                  target="the process"),
        Violation(violation="the system demands passion for things nobody is passionate about",
                  strength=0.6, benignness=0.9, target="the system"),
    ])


def _mock_candidates(draft: ContentDraft, personas: list[str],
                     mechanism: str) -> JokeCandidates:
    items = []
    for i, persona in enumerate(personas):
        items.append(JokeCandidate(
            persona=persona, mechanism=mechanism,
            hook=f"{draft.hook}".strip() or "This is fine.",
            caption=(draft.caption or "").strip()
                    + f"\n\n(offline {persona} punch-up, beat {i + 1})",
            script=(draft.script and (draft.script.strip() + "\n\n...the punchline.")) or None,
            target_assumption="the reader expects sincerity",
            connector="the premise",
            reinterpretation="it was absurd all along",
            punch_word=f"beat {i + 1}",
        ))
    return JokeCandidates(items=items)
