"""First-class series bookkeeping — franchise compounding (vision #5, gap #9).

Episodic strategies (those with a ``series_format``) get a real series object:
a premise, an episode counter, trailing per-episode rewards, and THE KILL RULE —
a series whose last 3 consecutive episode rewards all land below 0.4 (on the
graded reward scale where 0.5 = platform baseline) is retired, alerted, and
replaced with a fresh premise for the same strategy. Franchises are the core
growth asset; underperforming ones must die fast and be reborn different.

One series per (product, strategy) for simplicity; ``platform`` stays NULL
(cross-platform) — the series row IS the franchise, wherever it airs.

Wiring: the pipeline calls :func:`on_content_generated` after each episodic
generation; the feedback loop (or ``mark series`` maintenance) calls
:func:`run_maintenance`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from . import characters as characters_mod
from . import db as db_module
from .app import App
from .llm import LLM

KILL_THRESHOLD = 0.4   # graded reward scale: 0.5 = performing exactly at baseline
KILL_STREAK = 3        # consecutive sub-threshold episodes before retirement
TRAILING_KEPT = 10     # per-episode rewards kept in last_engagement


class SeriesPremiseWire(BaseModel):
    """LLM output when proposing a replacement premise for a retired series."""

    premise: str
    rationale: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _first_sentence(text: str) -> str:
    t = " ".join((text or "").split())
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0] + sep[0]
    return t


def _decode(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    row["last_engagement"] = db_module.loads(row.get("last_engagement"), []) or []
    return row


def get_series(app: App, series_id: int) -> Optional[dict]:
    row = db_module.query_one(app.conn, "SELECT * FROM series WHERE id = ?", (series_id,))
    return _decode(db_module.row_to_dict(row))


def list_series(app: App, product_id: str, include_retired: bool = True) -> list[dict]:
    where = "product_id = ?" + ("" if include_retired else " AND status = 'active'")
    rows = db_module.query(
        app.conn,
        f"SELECT * FROM series WHERE {where} ORDER BY status = 'active' DESC, created_at",
        (product_id,))
    return [_decode(dict(r)) for r in rows]


def active_series(app: App, product_id: str, strategy_id: str) -> Optional[dict]:
    row = db_module.query_one(
        app.conn,
        "SELECT * FROM series WHERE product_id = ? AND strategy_id = ? "
        "AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (product_id, strategy_id))
    return _decode(db_module.row_to_dict(row))


def _default_premise(app: App, product: dict, strategy) -> str:
    """Character strategies: the persona's first sentence anchors the premise;
    otherwise the strategy's own series recipe does."""
    format_line = _first_sentence(
        getattr(strategy, "series_format", None) or getattr(strategy, "description", ""))
    if getattr(strategy, "uses_character", False):
        character = characters_mod.active_character(app, product["id"])
        if character and (character.get("persona") or "").strip():
            return f"{_first_sentence(character['persona'])} {format_line}".strip()
    return format_line or f"Ongoing {getattr(strategy, 'name', strategy)} series"


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def ensure_series(app: App, product: dict, strategy, platform: Optional[str] = None) -> dict:
    """Get-or-create the active series row for (product, strategy).

    ``platform`` is accepted for call-site symmetry but stored as NULL — one
    cross-platform series per strategy keeps the bookkeeping honest (episode
    numbering and lore are shared across platforms already).
    """
    existing = active_series(app, product["id"], strategy.id)
    if existing:
        return existing
    sid = db_module.insert(
        app.conn, "series",
        product_id=product["id"], strategy_id=strategy.id,
        premise=_default_premise(app, product, strategy),
        platform=None, episodes=0, status="active", updated_at=_now())
    return get_series(app, sid)


def record_episode(app: App, series_id: int) -> Optional[dict]:
    db_module.execute(
        app.conn,
        "UPDATE series SET episodes = episodes + 1, updated_at = ? WHERE id = ?",
        (_now(), series_id))
    return get_series(app, series_id)


def on_content_generated(app: App, product: dict, strategy, platform: str) -> Optional[dict]:
    """Pipeline hook: bump the franchise when an episodic piece is generated.
    Non-episodic strategies have no series — returns None."""
    if strategy is None or not getattr(strategy, "series_format", None):
        return None
    s = ensure_series(app, product, strategy, platform)
    return record_episode(app, s["id"])


# --------------------------------------------------------------------------- #
# Stats + THE KILL RULE
# --------------------------------------------------------------------------- #
def _episode_rewards(app: App, product_id: str, strategy_id: str) -> list[float]:
    """Graded rewards of this series' posted episodes, oldest → newest."""
    rows = db_module.query(
        app.conn,
        """
        SELECT p.reward FROM content c
        JOIN posts p ON p.content_id = c.id
        WHERE c.product_id = ? AND p.reward IS NOT NULL AND p.rewarded_at IS NOT NULL
          AND c.strategy_context LIKE ?
        ORDER BY p.posted_at, p.id
        """,
        (product_id, f'%"strategy": "{strategy_id}"%'))
    return [float(r["reward"]) for r in rows]


def update_stats(app: App, product_id: str) -> list[dict]:
    """Refresh trailing rewards + average for every active series of the product."""
    out = []
    for s in list_series(app, product_id, include_retired=False):
        rewards = _episode_rewards(app, product_id, s["strategy_id"])
        trailing = [round(r, 5) for r in rewards[-TRAILING_KEPT:]]
        avg = round(sum(rewards) / len(rewards), 5) if rewards else 0.0
        db_module.update(app.conn, "series", s["id"],
                         last_engagement=trailing, avg_engagement=avg,
                         updated_at=_now())
        out.append(get_series(app, s["id"]))
    return out


def _propose_replacement(app: App, llm: LLM, product: dict, strategy_id: str,
                         old: dict) -> str:
    """One LLM call: a fresh premise for the same strategy (offline: deterministic)."""
    from . import strategies as strategies_mod

    strategy = strategies_mod.get(strategy_id)
    s_name = getattr(strategy, "name", strategy_id)
    recipe = getattr(strategy, "series_format", "") or getattr(strategy, "description", "")
    last = old.get("last_engagement") or []
    system = (
        "You design serialized social-content franchises. A series premise just got "
        "retired for underperforming; propose ONE fresh replacement premise for the "
        "same strategy — a genuinely different angle, not a rewording. One or two "
        "sentences, concrete enough to generate 20+ episodes."
    )
    user = (
        f"PRODUCT: {product.get('name')} — {product.get('description', '')}\n"
        f"AUDIENCE: {product.get('target_audience', '')}\n"
        f"STRATEGY: {s_name} ({strategy_id})\nSERIES RECIPE: {recipe}\n"
        f"RETIRED PREMISE: {old.get('premise')}\n"
        f"ITS LAST EPISODE REWARDS: {last[-KILL_STREAK:]} "
        f"(0.5 = platform baseline; all below {KILL_THRESHOLD})"
    )

    def _mock() -> SeriesPremiseWire:
        return SeriesPremiseWire(
            premise=(f"Rebooted {s_name} franchise: {_first_sentence(recipe)} "
                     f"— inverted angle after the previous premise stalled "
                     f"({old.get('episodes', 0)} episodes)."),
            rationale="offline replacement: previous premise underperformed "
                      f"{KILL_STREAK} episodes running")

    proposal = llm.parse(system, user, SeriesPremiseWire,
                         model=app.settings.llm.text_model,
                         product_id=product["id"], mock_factory=_mock)
    return (proposal.premise or "").strip() or _mock().premise


def apply_kill_rule(app: App, llm: LLM, product: dict) -> dict:
    """Retire series whose last KILL_STREAK episode rewards are all below
    KILL_THRESHOLD, alert, and spawn a replacement premise for each."""
    retired, spawned = [], []
    for s in list_series(app, product["id"], include_retired=False):
        last = s.get("last_engagement") or []
        if s["episodes"] < KILL_STREAK or len(last) < KILL_STREAK:
            continue
        streak = last[-KILL_STREAK:]
        if not all(r < KILL_THRESHOLD for r in streak):
            continue
        reason = (f"Last {KILL_STREAK} episode rewards {streak} all below "
                  f"{KILL_THRESHOLD} (0.5 = platform baseline) after "
                  f"{s['episodes']} episodes — franchise is not compounding.")
        db_module.update(app.conn, "series", s["id"],
                         status="retired", retired_reason=reason, updated_at=_now())
        db_module.log_activity(
            app.conn, "series",
            f"Series retired [{s['strategy_id']}]: “{(s['premise'] or '')[:70]}” — {reason}",
            product_id=product["id"], level="error")
        retired.append(get_series(app, s["id"]))

        premise = _propose_replacement(app, llm, product, s["strategy_id"], s)
        new_id = db_module.insert(
            app.conn, "series",
            product_id=product["id"], strategy_id=s["strategy_id"],
            premise=premise, platform=s.get("platform"),
            episodes=0, status="active", updated_at=_now())
        db_module.log_activity(
            app.conn, "series",
            f"Replacement series spawned [{s['strategy_id']}]: “{premise[:70]}”",
            product_id=product["id"], level="info")
        spawned.append(get_series(app, new_id))
    return {"retired": retired, "spawned": spawned}


def run_maintenance(app: App, llm: LLM, product: dict) -> dict:
    """The periodic pass: refresh stats, then apply the kill rule."""
    updated = update_stats(app, product["id"])
    result = apply_kill_rule(app, llm, product)
    result["updated"] = updated
    return result
