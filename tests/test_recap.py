"""Tests for the fake-movie recap template (src/mark/templates/recap.py).

Everything runs in mock mode (no API keys, per conftest's `app` fixture): the
LLM invents nothing real, TTS writes silent WAVs sized to the estimated
narration length, and beat clips are Pillow-still placeholders. We assert the
real assembled artifact (a playable 1080x1920 H.264 mp4), that narration is the
master clock (each beat's clip length matches its narration length), that the
final beat is the product twist, and that clip_intelligence finds the cuts in a
synthetic multi-shot video.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mark.media import edl as edl_mod
from mark.media import tts
from mark.schemas import ContentDraft, ContentPlan
from mark.templates import recap


def _plan() -> ContentPlan:
    return ContentPlan(
        platform="tiktok", content_type="video",
        topic="a heist thriller", angle="beating a rigged job-application system",
        hook_style="story", tone="funny", emotional_target="recognition")


def _draft() -> ContentDraft:
    return ContentDraft(caption="the recap of the year", hook="This man had one plan.",
                        script="", video_style="ai_generated")


def _probe(path: Path, entries: str, stream: str | None = None) -> str:
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream]
    cmd += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------- #
# produce()
# --------------------------------------------------------------------------- #
@pytest.fixture
def produced(app, llm, product, tmp_path):
    out = tmp_path / "recap_out"
    result = recap.produce(app, llm, product, 4242, _plan(), _draft(), out)
    return result, out


def test_produce_returns_playable_vertical_h264(produced):
    result, _ = produced
    paths = result["media_paths"]
    assert len(paths) == 1
    mp4 = Path(paths[0])
    assert mp4.is_file() and mp4.stat().st_size > 0

    assert _probe(mp4, "stream=codec_name", "v:0") == "h264"
    assert _probe(mp4, "stream=width", "v:0") == "1080"
    assert _probe(mp4, "stream=height", "v:0") == "1920"
    # A voiceover track must be present and the video must be a real 60-90s-ish
    # recap (mock narration is shorter, but must be non-trivial).
    assert _probe(mp4, "stream=codec_type", "a:0") == "audio"
    assert float(_probe(mp4, "format=duration")) > 8.0


def test_edl_written_and_ai_flagged(produced):
    _, out = produced
    edl = edl_mod.load(edl_mod.edl_path_for(out))
    assert edl.ai_generated is True                 # disclosure invariant
    assert edl.captions.mode == "karaoke"
    assert len(edl.captions.words) > 0
    assert any(a.kind == "voiceover" for a in edl.audio)


def test_narration_is_master_clock(app, llm, product, produced):
    """Each beat's clip length must match its narration length within tolerance
    — narration is the master clock, video bends to fit it."""
    _, out = produced
    edl = edl_mod.load(edl_mod.edl_path_for(out))
    story = recap.generate_story(app, llm, product, _plan(), _draft())

    assert len(edl.clips) == len(story.beats)
    for clip, beat in zip(edl.clips, story.beats):
        expected = tts.estimate_duration(beat.narration_sentence)
        got = edl_mod.clip_seconds(clip)            # (out-in)/speed
        assert abs(got - expected) < 0.6, (
            f"beat clip {got:.2f}s vs narration {expected:.2f}s")
        assert edl_mod.SPEED_MIN <= clip.speed <= edl_mod.SPEED_MAX

    # Visual timeline (hard cuts) equals the narration timeline: no drift.
    narration = out / "4242_narration.wav"
    assert abs(edl_mod.visual_duration(edl) - tts.media_duration(narration)) < 1.0


def test_final_beat_is_product_twist(app, llm, product):
    story = recap.generate_story(app, llm, product, _plan(), _draft())
    assert story.beats[-1].is_twist is True
    assert product["name"].lower() in story.beats[-1].narration_sentence.lower()
    # …and the product stays out of the earlier beats (twist lands late).
    early = " ".join(b.narration_sentence for b in story.beats[:-2]).lower()
    assert product["name"].lower() not in early
    assert _MIN_OK(story.beats)


def _MIN_OK(beats) -> bool:
    return recap._MIN_BEATS <= len(beats) <= recap._MAX_BEATS


# --------------------------------------------------------------------------- #
# clip_intelligence()
# --------------------------------------------------------------------------- #
def _make_multishot(path: Path, colors=("red", "green", "blue"), each=1.0) -> Path:
    """Concatenate distinct-color lavfi clips into one file with hard cuts."""
    parts = []
    for i, c in enumerate(colors):
        p = path.parent / f"seg_{i}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c={c}:s=320x240:d={each}:r=25",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
            capture_output=True, text=True, check=True)
        parts.append(p)
    listing = path.parent / "concat.txt"
    listing.write_text("\n".join(f"file '{p.name}'" for p in parts) + "\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing.name,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", path.name],
        cwd=str(path.parent), capture_output=True, text=True, check=True)
    return path


def test_clip_intelligence_finds_shots(app, tmp_path):
    video = _make_multishot(tmp_path / "multishot.mp4")
    shots = recap.clip_intelligence(app, video, threshold=0.3)
    # Three distinct-color segments → two interior cuts → ~3 shots.
    assert 2 <= len(shots) <= 4, f"expected ~3 shots, got {len(shots)}"
    # Shots are ordered, contiguous, and each has a real keyframe PNG.
    prev_end = 0.0
    for s in shots:
        assert s["end"] > s["start"] >= prev_end - 0.05
        prev_end = s["end"]
        assert s["keyframe"] is not None and Path(s["keyframe"]).is_file()


def test_clip_intelligence_single_shot_no_cuts(app, tmp_path):
    """A uniform clip has no scene changes → exactly one shot spanning the file."""
    solid = _make_multishot(tmp_path / "solid.mp4", colors=("black",), each=2.0)
    shots = recap.clip_intelligence(app, solid, threshold=0.3)
    assert len(shots) == 1
    assert shots[0]["start"] == 0.0 and shots[0]["end"] > 1.0
