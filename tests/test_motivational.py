"""Motivational-letterbox template — real render + ffprobe assertions (mock mode).

Everything runs offline via the ``app`` fixture (forced-mock App): the LLM
returns the deterministic sample quote, stock sourcing generates a real local
lavfi clip, and TTS writes a real silent WAV — so ``produce`` builds a genuine
playable 1080x1920 H.264 mp4 with no API keys.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mark.agents.media import media_dir_for
from mark.media import edl as edl_mod
from mark.schemas import ContentDraft, ContentPlan
from mark.templates import motivational


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,codec_name", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout)["streams"][0]


def _plan(tone: str = "inspirational discipline") -> ContentPlan:
    return ContentPlan(
        platform="tiktok", content_type="video",
        topic="discipline over motivation", angle="self-reliance",
        hook_style="pain_point", tone=tone, emotional_target="determination")


def _draft() -> ContentDraft:
    return ContentDraft(caption="get up.", hook="Nobody is coming to save you")


def test_produce_returns_playable_mp4(app, llm, product):
    out_dir = media_dir_for(app, product["id"], 4201)
    result = motivational.produce(app, llm, product, 4201, _plan("harsh discipline"),
                                  _draft(), out_dir)

    paths = result["media_paths"]
    assert len(paths) == 1
    mp4 = Path(paths[0])
    assert mp4.exists() and mp4.stat().st_size > 0

    stream = _probe(mp4)
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert stream["codec_name"] == "h264"


def test_writes_valid_edl_with_letterbox_and_captions(app, llm, product):
    out_dir = media_dir_for(app, product["id"], 4202)
    motivational.produce(app, llm, product, 4202, _plan("harsh discipline"),
                         _draft(), out_dir)

    edl = edl_mod.load(edl_mod.edl_path_for(out_dir))
    # Letterbox: one windowed clip with the ~420px-bar center window.
    assert len(edl.clips) == 1
    clip = edl.clips[0]
    assert clip.fit == "window"
    assert clip.window.y == 420 and clip.window.h == 1080
    assert clip.mute is True
    # Quote overlay (top bar) + watermark (bottom bar).
    styles = {o.style for o in edl.overlays}
    assert "quote" in styles and "watermark" in styles
    quote_ov = next(o for o in edl.overlays if o.style == "quote")
    assert quote_ov.y < 420 and quote_ov.text == quote_ov.text.upper()
    wm = next(o for o in edl.overlays if o.style == "watermark")
    assert wm.y > 1500 and wm.text.startswith("@")
    # Harsh lane: spoken voiceover + karaoke captions.
    assert edl.captions.mode == "karaoke" and len(edl.captions.words) > 0
    assert any(a.kind == "voiceover" for a in edl.audio)
    assert edl.ai_generated is False


def test_hopecore_music_lane(app, llm, product):
    out_dir = media_dir_for(app, product["id"], 4203)
    result = motivational.produce(
        app, llm, product, 4203,
        _plan("hopecore soft uplifting"), _draft(), out_dir)

    mp4 = Path(result["media_paths"][0])
    stream = _probe(mp4)
    assert (stream["width"], stream["height"]) == (1080, 1920)

    edl = edl_mod.load(edl_mod.edl_path_for(out_dir))
    # Music-bed lane: a music track, no karaoke captions.
    assert any(a.kind == "music" for a in edl.audio)
    assert edl.captions.mode == "none"
