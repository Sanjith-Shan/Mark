"""Knowledge self-refresh — the audience model doesn't rot (vision #1, #5).

The specificity bank and pain veins are the humor engine's raw material; they
were hand-curated at onboarding, but the system already collects the material
to maintain them itself: real audience comments and trend topics. This module
mines that material, proposes additions in the audience's own language
(verbatim-adjacent) plus retirements of entries that read as dated, and applies
them under hard caps.

HARD RULE: ``fact_base`` is never touched here — facts require human
verification before the educational strategy may cite them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .. import db as db_module
from .. import store
from ..app import App
from ..llm import LLM

SPECIFICITY_CAP = 40
PAIN_VEINS_CAP = 15
MAX_NEW_SPECIFICITY = 5
MAX_NEW_PAIN_VEINS = 3
MAX_STALE = 5
COMMENT_SAMPLE = 200
TREND_SAMPLE = 20


class KnowledgeProposalWire(BaseModel):
    """LLM proposal — typed lists only (strict structured outputs)."""

    new_specificity: list[str] = Field(default_factory=list)  # ≤5 hyper-concrete artifacts
    new_pain_veins: list[str] = Field(default_factory=list)   # ≤3 narrow pains
    stale_entries: list[str] = Field(default_factory=list)    # ≤5 entries that read dated
    reasoning: str = ""


# --------------------------------------------------------------------------- #
# Raw material
# --------------------------------------------------------------------------- #
def _recent_comments(app: App, product_id: str, limit: int = COMMENT_SAMPLE) -> list[str]:
    rows = db_module.query(
        app.conn,
        """
        SELECT cm.comment_text FROM comments cm
        JOIN posts p ON p.id = cm.post_id
        JOIN content c ON c.id = p.content_id
        WHERE c.product_id = ?
        ORDER BY cm.id DESC LIMIT ?
        """,
        (product_id, limit))
    out, seen = [], set()
    for r in rows:
        t = (r["comment_text"] or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _recent_trends(app: App, product_id: str, limit: int = TREND_SAMPLE) -> list[str]:
    rows = db_module.query(
        app.conn,
        """
        SELECT topic FROM trends
        WHERE product_id = ? OR product_id IS NULL
        ORDER BY collected_at DESC, id DESC LIMIT ?
        """,
        (product_id, limit * 3))
    out, seen = [], set()
    for r in rows:
        t = (r["topic"] or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
# Mining
# --------------------------------------------------------------------------- #
def _mock_proposal(comments: list[str]) -> KnowledgeProposalWire:
    """Deterministic offline proposal derived from how commenters actually talk."""
    new_spec = []
    for c in comments[:2]:
        t = " ".join(c.split()).rstrip(".!")
        if t:
            new_spec.append(f'"{t[:90]}" (verbatim-adjacent, from the comments)')
    pains = []
    if comments:
        t = " ".join(comments[0].split()).rstrip(".!")
        pains.append(f"the thing commenters keep saying: {t[:70]}")
    return KnowledgeProposalWire(
        new_specificity=new_spec, new_pain_veins=pains, stale_entries=[],
        reasoning="offline mining: lifted phrasing directly from recent comments")


def mine(app: App, llm: LLM, product: dict) -> dict:
    """Mine fresh audience language from collected data and refresh the pools.

    Returns the proposal plus what was actually applied.
    """
    pid = product["id"]
    comments = _recent_comments(app, pid)
    trend_topics = _recent_trends(app, pid)
    bank = db_module.loads(product.get("specificity_bank"), []) or []
    knowledge = db_module.loads(product.get("knowledge"), {}) or {}
    pain_veins = knowledge.get("pain_veins") or []

    system = (
        "You maintain the audience model for a social-content engine: a specificity "
        "bank (hyper-concrete artifacts of the audience's life — the humor engine's "
        "raw material) and a list of pain veins (narrow pains the audience comments "
        "'same' on).\n\n"
        "From REAL audience comments and current trend topics, propose:\n"
        f"1. Up to {MAX_NEW_SPECIFICITY} NEW specificity-bank entries mined from how "
        "commenters actually talk — verbatim-adjacent, named tools, precise numbers, "
        "never categories.\n"
        f"2. Up to {MAX_NEW_PAIN_VEINS} new pain veins.\n"
        f"3. Up to {MAX_STALE} existing entries to RETIRE because they read as dated "
        "(dead slang, expired references, things the comments never mention anymore). "
        "Quote them exactly as they appear.\n"
        "Never invent facts. Only propose entries grounded in the material provided."
    )
    user = (
        f"PRODUCT: {product.get('name')} — {product.get('description', '')}\n"
        f"AUDIENCE: {product.get('target_audience', '')}\n\n"
        f"RECENT AUDIENCE COMMENTS ({len(comments)}):\n"
        + "\n".join(f"- {c[:200]}" for c in comments[:COMMENT_SAMPLE])
        + f"\n\nRECENT TREND TOPICS ({len(trend_topics)}):\n"
        + "\n".join(f"- {t}" for t in trend_topics)
        + "\n\nCURRENT SPECIFICITY BANK:\n" + "\n".join(f"- {e}" for e in bank)
        + "\n\nCURRENT PAIN VEINS:\n" + "\n".join(f"- {e}" for e in pain_veins)
    )

    proposal = llm.parse(
        system, user, KnowledgeProposalWire,
        model=app.settings.llm.text_model,
        product_id=pid,
        mock_factory=lambda: _mock_proposal(comments),
    )
    # Enforce proposal caps regardless of what came back.
    proposal.new_specificity = [e.strip() for e in proposal.new_specificity if e.strip()][:MAX_NEW_SPECIFICITY]
    proposal.new_pain_veins = [e.strip() for e in proposal.new_pain_veins if e.strip()][:MAX_NEW_PAIN_VEINS]
    proposal.stale_entries = [e.strip() for e in proposal.stale_entries if e.strip()][:MAX_STALE]

    new_bank, spec_added, spec_retired = _merge(
        bank, proposal.new_specificity, proposal.stale_entries, SPECIFICITY_CAP)
    new_pains, pains_added, pains_retired = _merge(
        pain_veins, proposal.new_pain_veins, proposal.stale_entries, PAIN_VEINS_CAP)

    knowledge["pain_veins"] = new_pains
    # fact_base / take_pool pass through untouched (fact_base is human-verified only).
    store.update_product(app.conn, pid, specificity_bank=new_bank, knowledge=knowledge)

    added = len(spec_added) + len(pains_added)
    retired = len(spec_retired) + len(pains_retired)
    db_module.log_activity(
        app.conn, "knowledge",
        f"Knowledge refresh for {pid}: +{added} added, -{retired} retired "
        f"(bank {len(new_bank)}/{SPECIFICITY_CAP}, pains {len(new_pains)}/{PAIN_VEINS_CAP})",
        product_id=pid)

    return {
        "proposal": proposal.model_dump(),
        "applied": {
            "specificity_added": spec_added,
            "pain_veins_added": pains_added,
            "retired": spec_retired + pains_retired,
        },
        "specificity_bank": new_bank,
        "pain_veins": new_pains,
        "comments_mined": len(comments),
        "trends_mined": len(trend_topics),
    }


def _merge(current: list[str], additions: list[str], stale: list[str],
           cap: int) -> tuple[list[str], list[str], list[str]]:
    """Apply retirements + additions with a hard cap. Case-insensitive dedupe;
    proposed-stale entries drop first, then the oldest entries make room."""
    stale_keys = {s.strip().lower() for s in stale}
    kept = [e for e in current if (e or "").strip().lower() not in stale_keys]
    retired = [e for e in current if (e or "").strip().lower() in stale_keys]
    seen = {(e or "").strip().lower() for e in kept}
    added = []
    for a in additions:
        key = a.strip().lower()
        if key and key not in seen:
            kept.append(a.strip())
            seen.add(key)
            added.append(a.strip())
    while len(kept) > cap:
        kept.pop(0)  # oldest first — additions live at the tail
    return kept, added, retired
