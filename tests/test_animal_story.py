"""Animal-story template — offline (mock) end-to-end render tests.

Everything runs in forced mock mode (the ``app`` fixture strips API keys), so
these exercise the real ffmpeg pipeline: storyboard → per-beat stills → zoompan
clips → EDL → burned static-scene captions + AI-disclosure → 1080x1920 H.264.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mark import store
from mark.llm import LLM
from mark.media import edl as edl_mod
from mark.schemas import ContentDraft, ContentPlan
from mark.templates import animal_story


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.fixture
def plan_draft():
    plan = ContentPlan(
        platform="tiktok", content_type="video",
        topic="Whiskers gets lost in a storm", angle="rescue arc",
        hook_style="story", tone="emotional")
    draft = ContentDraft(
        caption="Whiskers lost everything. Part 1.", hook="Whiskers waits in the rain",
        video_prompt="a sad ginger kitten lost in a rainy city")
    return plan, draft


def test_storyboard_shape():
    """Deterministic mock board: 8-10 beats, short present-tense overlays,
    a valid arc, twist late, ends on a cliffhanger."""
    board = animal_story._mock_storyboard("rescue", _P("a lost kitten"))
    board = animal_story._sanitize_board(board, "rescue", _P("a lost kitten"))
    assert animal_story._MIN_BEATS <= len(board.beats) <= animal_story._MAX_BEATS
    assert board.arc_type in animal_story.ARC_TYPES
    assert board.cliffhanger is True
    for beat in board.beats:
        assert 1 <= len(beat.overlay_text.split()) <= 8
        assert beat.image_prompt.strip()
        assert 3.0 <= beat.duration_s <= 6.0
    # Twist should land in the back half (research: outrageous turn at beat ~6-7).
    assert board.twist_beat >= len(board.beats) - 3


def test_produce_renders_playable_vertical_mp4(app, llm, product, plan_draft):
    plan, draft = plan_draft
    content_id = store.insert_content(
        app.conn, product_id=product["id"], platform="tiktok",
        content_type="video", caption=draft.caption)
    out_dir = app.paths.media_dir / product["id"] / "test" / str(content_id)

    result = animal_story.produce(app, llm, product, content_id, plan, draft, out_dir)

    paths = result["media_paths"]
    assert len(paths) == 1
    final = Path(paths[0])
    assert final.exists() and final.stat().st_size > 0
    assert final.name == f"{content_id}_tiktok_video.mp4"

    info = _ffprobe(final)
    v = info["streams"][0]
    assert v["codec_name"] == "h264"
    assert (v["width"], v["height"]) == (1080, 1920)
    assert float(info["format"]["duration"]) > 20  # ~37s story, 9 beats

    # EDL persisted, AI-flagged, static-scene captions, one event per beat.
    edl = edl_mod.load(edl_mod.edl_path_for(out_dir))
    assert edl.ai_generated is True
    assert edl.captions.mode == "static_scene"
    assert len(edl.clips) == len(edl.captions.events)
    assert animal_story._MIN_BEATS <= len(edl.clips) <= animal_story._MAX_BEATS
    assert any(a.kind == "music" for a in edl.audio)

    # Storyboard sidecar for the editor / INTEGRATION handoff.
    side = json.loads((out_dir / "storyboard.json").read_text())
    assert side["arc_type"] in animal_story.ARC_TYPES
    assert len(side["beats"]) == len(edl.clips)


class _P:
    """Minimal stand-in for a ContentPlan (topic/angle only) for unit calls."""

    def __init__(self, topic="", angle=""):
        self.topic = topic
        self.angle = angle
