"""AI brand ambassador template tests (mock mode, real ffmpeg renders).

Covers: the no-testimonial compliance constraint in the strategy/writer briefs,
identity-pack minting idempotency, the identity QC gate degrading to skipped when
insightface is absent, and a full offline produce() that emits a playable
1080x1920 H.264 talking-head video with an EDL sidecar.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mark import characters as characters_mod
from mark import store
from mark.media import identity
from mark.schemas import ContentDraft, ContentPlan
from mark.templates import ambassador

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def _character(app):
    product = store.get_active_product(app.conn)
    return characters_mod.create(
        app, product["id"], name="Mia", role="ambassador",
        persona="A friendly spokesperson who demonstrates the product to camera.",
        visual_desc=("A poised 24-year-old woman with warm skin, dark almond eyes, "
                     "long black hair, cream knit top; photorealistic, fully synthetic."),
        voice="nova")


def _plan_draft():
    plan = ContentPlan(
        platform="tiktok", content_type="video",
        topic="how the app autofills job applications",
        angle="spokesperson demo", hook_style="bold_claim", tone="educational")
    draft = ContentDraft(
        caption="Watch this app fill out a whole job application in one click.",
        hook="Watch this app do the boring part for you.",
        script=("Watch what this app does. It reads the job posting, then it fills "
                "the whole application for you. You did not have to type any of that. "
                "That is the whole point."),
        video_prompt="ambassador speaking to camera in a bright modern room",
        video_style="talking_head")
    return plan, draft


def _probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,codec_name:format=duration", "-of", "default=nw=1",
         str(path)], capture_output=True, text=True)
    out = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Compliance
# --------------------------------------------------------------------------- #
def test_briefs_ban_testimonials():
    """The no-first-person-testimonial FTC constraint must be present in both the
    strategist and writer briefs (compliance is baked into the prompts)."""
    for brief in (ambassador.STRATEGY.strategist_brief, ambassador.STRATEGY.writer_brief):
        low = brief.lower()
        assert "testimonial" in low
        assert "spokesperson" in low or "demonstration" in low or "demonstrat" in low
    assert ambassador.STRATEGY.uses_character is True
    assert ambassador.STRATEGY.id == "ai-ambassador"


# --------------------------------------------------------------------------- #
# Identity QC gate
# --------------------------------------------------------------------------- #
def test_check_frames_skips_without_insightface(app, tmp_path):
    """With insightface absent (not installed) or no canonical embedding, the QC
    gate must return skipped=True/passed=True and never crash."""
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=1:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
        check=True, capture_output=True)
    result = identity.check_frames(clip, canonical_emb=None)
    assert result["passed"] is True
    assert result["skipped"] is True
    # arcface_embedding on a real image also degrades to None when unavailable.
    if not identity.available():
        assert identity.arcface_embedding(clip) is None
    # cosine helper is total: missing embeddings → 0.0, never an exception.
    assert identity.identity_similarity(None, None) == 0.0


# --------------------------------------------------------------------------- #
# Identity pack minting
# --------------------------------------------------------------------------- #
def test_ensure_identity_is_idempotent(app, llm):
    character = _character(app)
    pack1 = ambassador.ensure_identity(app, llm, character)
    canonical = Path(pack1["canonical_face"])
    assert canonical.exists()
    assert pack1["refs"] and all(Path(r).exists() for r in pack1["refs"])
    assert pack1["voice_id"] == "nova"
    mtime1 = canonical.stat().st_mtime_ns

    # Second call must NOT regenerate the immutable pack (re-read from DB).
    pack2 = ambassador.ensure_identity(app, llm, characters_mod.get(app, character["id"]))
    assert pack2["canonical_face"] == pack1["canonical_face"]
    assert pack2["minted_at"] == pack1["minted_at"]
    assert canonical.stat().st_mtime_ns == mtime1  # file untouched


# --------------------------------------------------------------------------- #
# Full produce (offline talking-head render)
# --------------------------------------------------------------------------- #
def test_produce_emits_playable_video(app, llm, tmp_path):
    character = _character(app)
    plan, draft = _plan_draft()
    out_dir = Path(app.paths.data_dir) / "media" / "amb"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = ambassador.produce(app, llm, store.get_active_product(app.conn),
                                content_id=4242, plan=plan, draft=draft,
                                out_dir=out_dir, character=character)
    paths = result["media_paths"]
    assert paths and Path(paths[0]).exists()
    info = _probe(Path(paths[0]))
    assert info["codec_name"] == "h264"
    assert (int(info["width"]), int(info["height"])) == (1080, 1920)
    assert float(info["duration"]) > 1.0

    # EDL sidecar persisted, AI-generated (disclosure invariant), karaoke captions.
    from mark.media import edl as E

    edl = E.load(E.edl_path_for(out_dir))
    assert edl.ai_generated is True
    assert edl.captions.mode == "karaoke"
    assert len(edl.captions.words) > 0
