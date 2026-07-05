"""Persistent AI characters — brand ambassadors / mascots that front content.

A character is a stable identity: a persona (lore, personality, speech style), a
canonical visual description, an optional TTS voice, and a reference image
("character sheet") that conditions every image/video generation for visual
consistency. Strategies opt in via ``uses_character``; the writer then speaks in
the character's voice and the media pipeline keeps the face/outfit consistent by
passing the reference image to reference-conditioned generation.

Consistency pipeline (the technique virtual-influencer creators use):
  1. Generate ONE canonical character sheet (neutral pose, clean background).
  2. Every subsequent image = reference-conditioned edit of that sheet
     (OpenAI images.edit with the sheet as input image).
  3. Every video = scene still (step 2) → image-to-video, so the first frame
     already has the right identity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import db as db_module
from .app import App
from .llm import LLM


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def create(app: App, product_id: str, *, name: str, persona: str, visual_desc: str,
           role: str = "ambassador", voice: Optional[str] = None,
           catchphrases: Optional[list[str]] = None) -> dict:
    cid = db_module.insert(
        app.conn, "characters",
        product_id=product_id, name=name, role=role, persona=persona,
        visual_desc=visual_desc, voice=voice, catchphrases=catchphrases or [],
    )
    db_module.log_activity(app.conn, "character", f"Created character “{name}”",
                           product_id=product_id)
    return get(app, cid)


def create_from_concept(app: App, product_id: str, concept: dict) -> dict:
    """Create a character from an onboarding character-concept dict, initializing
    lore_state the way the shipped bibles (config/characters/*.yaml) do: episode
    counter at zero, empty NPC roster and arc list — the persona text carries the
    off-screen antagonist until episodes make it canon."""
    character = create(
        app, product_id,
        name=(concept.get("name") or "Mascot").strip(),
        persona=(concept.get("persona") or "").strip(),
        visual_desc=(concept.get("visual_desc") or "").strip(),
        role=concept.get("role") or "ambassador",
        voice=concept.get("voice"),
        catchphrases=concept.get("catchphrases") or [],
    )
    db_module.update(app.conn, "characters", character["id"],
                     lore_state={"episodes_posted": 0, "npcs": {}, "active_arcs": []})
    return get(app, character["id"])


def get(app: App, character_id: int) -> Optional[dict]:
    row = db_module.query_one(app.conn, "SELECT * FROM characters WHERE id = ?",
                              (character_id,))
    return _decode(db_module.row_to_dict(row))


def list_for_product(app: App, product_id: str, include_inactive: bool = False) -> list[dict]:
    where = "product_id = ?" + ("" if include_inactive else " AND active = 1")
    rows = db_module.query(app.conn,
                           f"SELECT * FROM characters WHERE {where} ORDER BY created_at",
                           (product_id,))
    return [_decode(dict(r)) for r in rows]


def active_character(app: App, product_id: str) -> Optional[dict]:
    """The character content should be fronted by. One active character → that
    one. Several → rotate by fewest episodes posted (the newcomer catches up,
    the established one keeps its cadence) instead of the old newest-wins rule,
    which silently retired the primary the moment a second was switched on."""
    rows = db_module.query(
        app.conn,
        "SELECT * FROM characters WHERE product_id = ? AND active = 1 "
        "ORDER BY created_at ASC",
        (product_id,),
    )
    characters = [_decode(dict(r)) for r in rows]
    if not characters:
        return None
    if len(characters) == 1:
        return characters[0]
    return min(characters,
               key=lambda c: int((c.get("lore_state") or {}).get("episodes_posted") or 0))


def update(app: App, character_id: int, **fields) -> Optional[dict]:
    if fields:
        db_module.update(app.conn, "characters", character_id, **fields)
    return get(app, character_id)


def _decode(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    row["catchphrases"] = db_module.loads(row.get("catchphrases"), []) or []
    row["lore_state"] = db_module.loads(row.get("lore_state"), {}) or {}
    return row


# --------------------------------------------------------------------------- #
# Config sync (config/characters/*.yaml → characters table)
# --------------------------------------------------------------------------- #
def sync_from_config(app: App) -> list[dict]:
    """Upsert character bibles from ``config/characters/*.yaml`` (keyed by
    product_id + name). YAML is the bible; DB rows carry live lore state — an
    existing row keeps its lore_state and reference_image."""
    import yaml

    char_dir = app.paths.config_dir / "characters"
    if not char_dir.exists():
        return []
    synced = []
    for path in sorted(char_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except Exception:
            continue
        if not raw.get("product_id") or not raw.get("name"):
            continue
        existing = db_module.query_one(
            app.conn,
            "SELECT * FROM characters WHERE product_id = ? AND name = ?",
            (raw["product_id"], raw["name"]))
        fields = dict(
            role=raw.get("role") or "ambassador",
            persona=(raw.get("persona") or "").strip(),
            visual_desc=(raw.get("visual_desc") or "").strip(),
            voice=raw.get("voice"),
            catchphrases=raw.get("catchphrases") or [],
            active=1 if raw.get("active", True) else 0,
        )
        if existing:
            db_module.update(app.conn, "characters", existing["id"], **fields)
            synced.append(get(app, existing["id"]))
        else:
            cid = db_module.insert(app.conn, "characters",
                                   product_id=raw["product_id"], name=raw["name"],
                                   lore_state=raw.get("lore_state") or {}, **fields)
            synced.append(get(app, cid))
    return [s for s in synced if s]


# --------------------------------------------------------------------------- #
# Reference image (character sheet)
# --------------------------------------------------------------------------- #
def sheet_prompt(character: dict) -> str:
    return (
        f"Character reference sheet: {character['visual_desc']}. "
        "Single subject, front-facing medium shot, neutral friendly expression, "
        "soft even studio lighting, plain light-gray background, photorealistic, "
        "no text, no watermark."
    )


def ensure_reference_image(app: App, llm: LLM, character: dict) -> Path:
    """Generate (once) and return the canonical character-sheet image."""
    existing = character.get("reference_image")
    if existing and Path(existing).exists():
        return Path(existing)

    from .media import images

    out_dir = app.paths.media_dir / "characters"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"character_{character['id']}.png"
    images.generate_image(app, llm, sheet_prompt(character), path,
                          size="1024x1536", product_id=character["product_id"])
    db_module.update(app.conn, "characters", character["id"],
                     reference_image=str(path))
    character["reference_image"] = str(path)
    db_module.log_activity(app.conn, "character",
                           f"Generated reference sheet for “{character['name']}”",
                           product_id=character["product_id"])
    return path


def scene_prompt(character: dict, scene: str) -> str:
    """Compose a media prompt that keeps the character's identity canonical."""
    return (f"{character['visual_desc']} — the SAME person as the reference image, "
            f"identical face, hair and outfit. Scene: {scene}")


def on_content_approved(app: App, content_row: dict) -> None:
    """Shared approval hook (web + CLI): advance lore when character-fronted
    content is approved. Callers must guard against re-approval themselves."""
    sctx = db_module.loads(content_row.get("strategy_context"), {}) or {}
    if sctx.get("character_id"):
        on_episode_approved(app, sctx["character_id"])


def on_episode_approved(app: App, character_id: int) -> None:
    """Advance the character's lore when an episode is approved — the universe
    must move forward or callbacks have nothing to call back to."""
    character = get(app, character_id)
    if not character:
        return
    lore = character.get("lore_state") or {}
    lore["episodes_posted"] = int(lore.get("episodes_posted") or 0) + 1
    # Signature counters creep upward with every episode. Not hardcoded to one
    # bible's key names: EVERY top-level integer counter advances (Poli's
    # applications_submitted + rejections_survived, any future character's
    # counters) — a frozen signature counter kills the lore's forward motion.
    for key, value in list(lore.items()):
        if key != "episodes_posted" and isinstance(value, int):
            lore[key] = value + 1 + (lore["episodes_posted"] % 7)
    db_module.update(app.conn, "characters", character_id, lore_state=lore)


def recent_comments(app: App, character_id: int, limit: int = 8) -> list[str]:
    """Audience comments on this character's recent episodes — mined as canon
    fuel (the Nutter Butter loop: 'you're all saying it has beef with Workday —
    it does now'). Top comments become next-episode material."""
    rows = db_module.query(
        app.conn,
        """
        SELECT cm.comment_text, c.strategy_context FROM comments cm
        JOIN posts p ON p.id = cm.post_id
        JOIN content c ON c.id = p.content_id
        WHERE c.strategy_context LIKE '%character_id%'
        ORDER BY cm.collected_at DESC LIMIT ?
        """,
        (limit * 5,))
    seen, out = set(), []
    for r in rows:
        # Decode-confirm: a bare LIKE on numeric ids prefix-matches (1 vs 12).
        sctx = db_module.loads(r["strategy_context"], {}) or {}
        if sctx.get("character_id") != character_id:
            continue
        text = (r["comment_text"] or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def resolve_for_content(app: App, product: dict, strategy) -> Optional[dict]:
    """The character to front this piece of content, if the strategy calls for one."""
    if strategy is None or not getattr(strategy, "uses_character", False):
        return None
    character = active_character(app, product["id"])
    if character is None:
        # Lazy first-run sync from config/characters/*.yaml.
        try:
            sync_from_config(app)
        except Exception:
            return None
        character = active_character(app, product["id"])
    return character
