"""Caption engine tests: alignment fallbacks + script snapping (align.py), ASS
generation for all three modes and style presets (ass_captions.py), vendored
fonts, and the legacy captions.py facade. A real speech end-to-end test (macOS
`say` → faster-whisper alignment → ASS burn → frame checks) is opt-in via
MARK_CAPTIONS_E2E=1 since it downloads the whisper model."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import ImageFont

from mark.media import align, ass_captions, captions

REPO_ROOT = Path(__file__).resolve().parents[1]
FONTS = REPO_ROOT / "src" / "mark" / "assets" / "fonts"

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"),
                                  reason="ffmpeg not installed")


# --------------------------------------------------------------------------- #
# align: offline fallback + script snapping
# --------------------------------------------------------------------------- #
def test_even_spacing_offline_with_duration_hint(app, tmp_path):
    words = align.word_timestamps(app, tmp_path / "missing.wav", "a bb ccc",
                                  duration=6.0)
    assert [w for w, _s, _e in words] == ["a", "bb", "ccc"]
    assert words[0][1] == 0.0
    assert words[-1][2] == pytest.approx(6.0)
    # longer words get proportionally more time
    assert (words[2][2] - words[2][1]) > (words[0][2] - words[0][1])


def test_even_spacing_estimates_duration_without_hint(app, tmp_path):
    words = align.word_timestamps(app, tmp_path / "missing.wav", "one two three")
    assert len(words) == 3
    assert words[-1][2] >= 3.0  # tts.estimate_duration floor


def test_no_script_no_asr_returns_empty(app, tmp_path):
    assert align.word_timestamps(app, tmp_path / "missing.wav") == []


def test_snap_to_script_keeps_script_verbatim():
    # ASR misheard "SudoApply" and dropped "brave" — script text must win.
    asr = [("never", 0.0, 0.3), ("apply", 0.35, 0.7), ("with", 0.75, 0.9),
           ("pseudo", 0.95, 1.3), ("supply", 1.3, 1.7)]
    script = ["Never", "apply", "brave", "with", "SudoApply"]
    out = align.snap_to_script(asr, script)
    assert [w for w, _s, _e in out] == script  # verbatim, ASR typos never shown
    # matched anchors take ASR timing
    assert out[0][1] == pytest.approx(0.0)
    assert out[1][1] == pytest.approx(0.35)
    # interpolated word sits between its neighbors
    assert out[1][2] <= out[2][1] < out[3][1]
    # strictly monotonic, non-overlapping
    for (_, _, e1), (_, s2, _) in zip(out, out[1:]):
        assert s2 >= e1 - 1e-9


def test_snap_to_script_all_unmatched_interpolates_over_audio_span():
    asr = [("completely", 0.5, 1.0), ("different", 1.0, 2.0)]
    out = align.snap_to_script(asr, ["alpha", "beta"])
    assert [w for w, _s, _e in out] == ["alpha", "beta"]
    assert out[0][1] == pytest.approx(0.5)  # spans the ASR audio window
    assert out[-1][2] == pytest.approx(2.0)


def test_snap_to_script_empty_inputs():
    assert align.snap_to_script([], ["hi"]) == []
    assert align.snap_to_script([("hi", 0, 1)], []) == []


# --------------------------------------------------------------------------- #
# ass_captions: styles
# --------------------------------------------------------------------------- #
def test_style_presets_load_from_yaml_and_are_distinct():
    hormozi = ass_captions.load_style("hormozi")
    clean = ass_captions.load_style("clean")
    meme = ass_captions.load_style("meme")
    assert hormozi["font"] == "Montserrat ExtraBold" and hormozi["uppercase"]
    assert clean["uppercase"] is False and clean["font_size"] < hormozi["font_size"]
    assert meme["font"] == "Anton"
    assert len({s["highlight_color"] for s in (hormozi, clean, meme)}) == 3


def test_unknown_style_falls_back_to_safe_defaults():
    style = ass_captions.load_style("no-such-preset")
    assert style["font"] == "Montserrat ExtraBold"
    assert style["chunk_size"] == 3


def test_inline_style_dict_merges_over_defaults():
    style = ass_captions.load_style({"font": "Arial", "chunk_size": 2})
    assert style["font"] == "Arial" and style["chunk_size"] == 2
    assert style["outline"] == 5  # default retained


def test_available_styles_lists_shipped_presets():
    names = ass_captions.available_styles()
    assert {"hormozi", "clean", "meme"} <= set(names)


# --------------------------------------------------------------------------- #
# ass_captions: the three modes
# --------------------------------------------------------------------------- #
WORDS = [
    {"w": "never", "t0": 0.0, "t1": 0.4, "emphasize": False, "emoji": None},
    {"w": "apply", "t0": 0.4, "t1": 0.8, "emphasize": True, "emoji": None},
    {"w": "manually", "t0": 0.8, "t1": 1.3, "emphasize": False, "emoji": "🔥"},
    {"w": "again", "t0": 1.3, "t1": 1.8, "emphasize": False, "emoji": None},
]
CANVAS = {"width": 1080, "height": 1920, "fps": 30}


def test_karaoke_mode_builds_word_state_events(tmp_path):
    out = ass_captions.build_ass(
        {"mode": "karaoke", "style": "hormozi", "words": WORDS},
        CANVAS, tmp_path / "k.ass")
    text = out.read_text()
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert text.count("Dialogue:") == len(WORDS)  # one event per word state
    assert r"\pos(540,1229)" in text or r"\pos(540,1230)" in text  # safe-zone anchor
    assert r"\t(0,120,\fscx128\fscy128)" in text          # pop in
    assert r"\t(120,220,\fscx100\fscy100)" in text        # settle back
    assert r"{\c&H00D7FF&}NEVER{\c&HFFFFFF&}" in text     # gold highlight, BGR, CAPS
    assert r"{\c&H00D7FF&}APPLY" in text                  # emphasized word stays gold
    assert r"\fscx140" in text                            # emphasized word pops bigger
    assert "MANUALLY 🔥" in text                          # emoji appended
    assert r"{\k" not in text                             # no inverted karaoke


def test_static_scene_mode_centers_events(tmp_path):
    events = [{"text": "he waited all day", "t0": 0.0, "t1": 4.1},
              {"text": "then it happened", "t0": 4.1, "t1": 8.0}]
    out = ass_captions.build_ass(
        {"mode": "static_scene", "style": "clean", "events": events},
        CANVAS, tmp_path / "s.ass")
    text = out.read_text()
    assert text.count("Dialogue:") == 2
    assert r"\pos(540,960)" in text          # dead center
    assert r"\fad(120,120)" in text          # soft fade
    assert "he waited all day" in text       # clean = mixed case
    assert r"\t(" not in text                # no pop in static mode


def test_seam_band_mode_places_karaoke_at_seam(tmp_path):
    out = ass_captions.build_ass(
        {"mode": "seam_band", "style": "hormozi", "words": WORDS},
        CANVAS, tmp_path / "seam.ass")
    text = out.read_text()
    assert r"\pos(540,960)" in text          # seam_y_frac 0.5 → mid-seam
    assert text.count("Dialogue:") == len(WORDS)


def test_none_mode_writes_header_only(tmp_path):
    out = ass_captions.build_ass({"mode": "none", "words": WORDS}, CANVAS,
                                 tmp_path / "n.ass")
    text = out.read_text()
    assert "Dialogue:" not in text and "[Events]" in text


def test_words_accepted_as_tuples(tmp_path):
    out = ass_captions.build_ass(
        {"mode": "karaoke", "style": "meme",
         "words": [("hello", 0.0, 0.5), ("world", 0.5, 1.0)]},
        CANVAS, tmp_path / "t.ass")
    text = out.read_text()
    assert text.count("Dialogue:") == 2
    assert "HELLO" in text  # meme is uppercase


def test_font_size_scales_with_canvas(tmp_path):
    small = ass_captions.build_ass(
        {"mode": "karaoke", "style": "hormozi", "words": WORDS},
        {"width": 540, "height": 960}, tmp_path / "small.ass").read_text()
    assert "Style: Mark,Montserrat ExtraBold,42," in small  # 84 * 960/1920


# --------------------------------------------------------------------------- #
# Fonts: vendored, non-empty, loadable
# --------------------------------------------------------------------------- #
def test_vendored_fonts_exist_and_load():
    expected = {"Montserrat-ExtraBold.ttf": "Montserrat",
                "Anton-Regular.ttf": "Anton",
                "BebasNeue-Regular.ttf": "Bebas Neue"}
    assert ass_captions.fonts_dir() == FONTS
    for fname, family in expected.items():
        p = FONTS / fname
        assert p.exists() and p.stat().st_size > 10_000, fname
        assert ImageFont.truetype(str(p), 40).getname()[0] == family
    assert (FONTS / "OFL-LICENSE.txt").exists()


# --------------------------------------------------------------------------- #
# Legacy facade (captions.py) — video.py must keep working unchanged
# --------------------------------------------------------------------------- #
def test_legacy_word_timestamps_signature(app, tmp_path):
    words = captions.word_timestamps(app, tmp_path / "missing.wav", "a bb ccc", 6.0)
    assert len(words) == 3
    assert words[-1][2] == pytest.approx(6.0)


def test_legacy_build_ass_keeps_word_case_and_highlight(tmp_path):
    out = captions.build_ass([("one", 0.0, 0.5), ("two", 0.5, 1.0)],
                             1080, 1920, tmp_path / "c.ass")
    text = out.read_text()
    assert text.count("Dialogue:") == 2
    assert r"{\c&H00FFFF&}one" in text  # default yellow highlight, verbatim case
    assert r"{\k" not in text


# --------------------------------------------------------------------------- #
# verify_sync plumbing (mock mode: even-spacing round trip on a rendered clip)
# --------------------------------------------------------------------------- #
@needs_ffmpeg
def test_verify_sync_round_trip_mock(app, tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15",
         "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
        capture_output=True, check=True)
    script = "hello brave new world"
    words = align.even_spacing(script.split(), 4.0)
    report = align.verify_sync(app, video, words)
    assert report["word_count"] == 4
    assert report["method"] == "mock"
    # mock realign = same even spacing over ~the same duration → tiny offsets
    assert report["median_offset_ms"] is not None
    assert report["median_offset_ms"] < 100


def test_verify_sync_empty_words(app, tmp_path):
    report = align.verify_sync(app, tmp_path / "nope.mp4", [])
    assert report["passed"] is False and report["word_count"] == 0


# --------------------------------------------------------------------------- #
# REAL end-to-end (opt-in: downloads the faster-whisper model, uses macOS say)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not os.environ.get("MARK_CAPTIONS_E2E"),
                    reason="set MARK_CAPTIONS_E2E=1 (downloads whisper model, needs macOS say)")
@needs_ffmpeg
def test_real_alignment_and_burn(app, tmp_path):
    app.force_mock = False  # local faster-whisper needs no API key
    script = "Never apply to jobs manually again. SudoApply fills every form for you."
    aiff = tmp_path / "vo.aiff"
    wav = tmp_path / "vo.wav"
    subprocess.run(["say", "-o", str(aiff), script], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ac", "1", "-ar", "16000",
                    str(wav)], capture_output=True, check=True)

    words = align.word_timestamps(app, wav, script)
    assert [w for w, _s, _e in words] == script.split()  # script verbatim
    assert words[0][1] < 1.0 and words[-1][2] > 2.0
    for (_, _, e1), (_, s2, _) in zip(words, words[1:]):
        assert s2 >= e1 - 1e-9

    from mark.media.tts import media_duration
    dur = media_duration(wav)
    ass = ass_captions.build_ass(
        {"mode": "karaoke", "style": "hormozi",
         "words": [{"w": w, "t0": s, "t1": e} for w, s, e in words]},
        {"width": 1080, "height": 1920}, tmp_path / "cap.ass")
    out = tmp_path / "out.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"testsrc2=size=1080x1920:rate=30:duration={dur:.2f}",
         "-i", str(wav), "-map", "0:v", "-map", "1:a",
         "-vf", f"ass={ass.name}:fontsdir={ass_captions.fonts_dir()}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
        capture_output=True, check=True, cwd=str(tmp_path))
    assert out.exists() and out.stat().st_size > 0

    report = align.verify_sync(app, out, words)
    assert report["passed"], report
