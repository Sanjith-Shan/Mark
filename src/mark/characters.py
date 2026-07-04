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
    """The character content should be fronted by (newest active one)."""
    row = db_module.query_one(
        app.conn,
        "SELECT * FROM characters WHERE product_id = ? AND active = 1 "
        "ORDER BY created_at DESC LIMIT 1",
        (product_id,),
    )
    return _decode(db_module.row_to_dict(row))


def update(app: App, character_id: int, **fields) -> Optional[dict]:
    if fields:
        db_module.update(app.conn, "characters", character_id, **fields)
    return get(app, character_id)


def _decode(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    row["catchphrases"] = db_module.loads(row.get("catchphrases"), []) or []
    return row


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


def resolve_for_content(app: App, product: dict, strategy) -> Optional[dict]:
    """The character to front this piece of content, if the strategy calls for one."""
    if strategy is None or not getattr(strategy, "uses_character", False):
        return None
    return active_character(app, product["id"])
