"""Regression tests for the media stack: caption karaoke colors, overlay
transparency, emoji stripping, chat-drama pacing, carousel padding, and
multi-shot mock b-roll stitching."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from mark import db as db_module
from mark import store
from mark.media import captions, chatdrama, images
from mark.schemas import ContentDraft, ContentPlan

REPO_ROOT = Path(__file__).resolve().parents[1]

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"),
                                  reason="ffmpeg not installed")


def _plan(**kw) -> ContentPlan:
    base = dict(platform="instagram", content_type="carousel", topic="job hunt hacks",
                angle="the manual way wastes hours", hook_style="pain_point",
                tone="relatable")
    base.update(kw)
    return ContentPlan(**base)


# --------------------------------------------------------------------------- #
# Captions: karaoke highlight must track the CURRENT word, not the unspoken ones
# --------------------------------------------------------------------------- #
def test_karaoke_highlights_only_current_word():
    words = [("hello", 0.0, 0.4), ("brave", 0.4, 0.8), ("world", 0.8, 1.2),
             ("again", 1.2, 1.6)]
    events = captions.karaoke_events(words, chunk=3)
    assert len(events) == 4  # one event per word state
    hi = r"{\c&H00FFFF&}"

    # Event 0: "hello" is live — highlighted; the others stay plain white.
    start, end, text = events[0]
    assert text.startswith(hi + "hello")
    assert hi + "brave" not in text and hi + "world" not in text
    assert (start, end) == (0.0, 0.4)  # holds until "brave" starts

    # Event 1: highlight moved to "brave" and off "hello".
    assert hi + "brave" in events[1][2]
    assert hi + "hello" not in events[1][2]

    # Second chunk starts fresh with "again" highlighted.
    assert hi + "again" in events[3][2]


def test_build_ass_has_no_inverted_k_tags(tmp_path):
    words = [("one", 0.0, 0.5), ("two", 0.5, 1.0)]
    out = captions.build_ass(words, 1080, 1920, tmp_path / "c.ass")
    content = out.read_text()
    # \k karaoke paints unspoken words in the secondary color (inverted look) —
    # the fix uses per-word inline color overrides instead.
    assert r"{\k" not in content
    assert content.count("Dialogue:") == 2
    assert r"{\c&H00FFFF&}one" in content


def test_word_timestamps_even_spacing_offline(app, tmp_path):
    words = captions.word_timestamps(app, tmp_path / "missing.wav", "a bb ccc", 6.0)
    assert len(words) == 3
    assert words[0][1] == 0.0
    assert words[-1][2] == pytest.approx(6.0)


# --------------------------------------------------------------------------- #
# Image overlay: the darkened band must be genuinely semi-transparent
# --------------------------------------------------------------------------- #
def test_text_overlay_band_is_semi_transparent(tmp_path):
    src = tmp_path / "white.png"
    Image.new("RGB", (512, 512), (255, 255, 255)).save(src)
    out = images.add_text_overlay(src, "Hi", tmp_path / "out.png")
    arr = np.asarray(Image.open(out).convert("RGB"))
    # 180/255 black over white blends to ~75 gray. Drawing straight onto RGB
    # ignored alpha and produced a fully opaque (0) band — no such pixels then.
    band = ((arr >= 65) & (arr <= 85)).all(axis=2)
    assert band.sum() > 500, "band should be semi-transparent gray, not opaque black"


def test_mock_image_deterministic_across_processes(tmp_path):
    # builtin hash() is salted per process — hashlib seeding must not be.
    code = ("from mark.media.images import _mock_image; "
            "img = _mock_image('stable prompt', (64, 64)); "
            "print(img.getpixel((32, 8)), img.getpixel((32, 56)))")
    outs = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, env=env, cwd=str(REPO_ROOT))
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout.strip())
    assert outs[0] == outs[1]


# --------------------------------------------------------------------------- #
# Emoji stripping (render-time only — DB text keeps them)
# --------------------------------------------------------------------------- #
def test_strip_emoji():
    assert images.strip_emoji("hi 💀 there") == "hi there"
    assert images.strip_emoji("fire🔥sale") == "firesale"
    assert images.strip_emoji("keycap 1⃣ done ⭐") == "keycap 1 done"
    assert images.strip_emoji("family 👨‍👩‍👧 trip") == "family trip"  # ZWJ sequence
    assert images.strip_emoji("plain text stays") == "plain text stays"
    assert images.strip_emoji("") == ""


def test_chat_frame_and_uikit_render_emoji_without_crashing(app, tmp_path):
    from mark.media import uikit

    img = chatdrama._render_frame("group chat 💀🔥", [
        {"sender": "Sam 😅", "text": "we got the offer 🎉🎉", "mine": False},
        {"sender": "me", "text": "no way 😭", "mine": True},
    ])
    assert img.size == (chatdrama.WIDTH, chatdrama.HEIGHT)
    p = uikit.render_ui_mockup(app, ["Portal 🚀", "text: approved ✅"],
                               tmp_path / "ui.png")
    assert p.exists()


# --------------------------------------------------------------------------- #
# Chat drama: pacing compresses to keep the payoff; never truncates from the end
# --------------------------------------------------------------------------- #
def test_plan_beats_compresses_instead_of_truncating():
    msgs = [{"sender": "me", "text": f"message {i}", "mine": True} for i in range(12)]
    natural = sum(chatdrama._beat_seconds(m["text"]) for m in msgs)
    kept, durations = chatdrama.plan_beats(msgs, max_duration=12.0)
    assert natural > 12.0  # the fixture genuinely overflows
    assert len(kept) == 12  # ALL messages retained — pacing compressed
    assert sum(durations) <= 12.0 + 1e-6
    assert all(d >= chatdrama.MIN_BEAT - 1e-9 for d in durations)


def test_plan_beats_last_resort_drops_middle_not_payoff():
    msgs = [{"sender": "me", "text": f"beat number {i}", "mine": True} for i in range(12)]
    kept, durations = chatdrama.plan_beats(msgs, max_duration=3.0)
    assert sum(durations) <= 3.0 + 1e-6
    assert len(kept) < 12  # even minimum pacing couldn't fit
    assert kept[0]["text"] == "beat number 0"    # opener survives
    assert kept[-1]["text"] == "beat number 11"  # payoff/cliffhanger survives


@needs_ffmpeg
def test_chat_video_has_audio_track(app, tmp_path):
    from mark.media.tts import media_duration

    out = chatdrama.render_chat_video(
        app, "Me: hi\nSam: big news 👀\nMe: tell me", tmp_path / "drama.mp4",
        title="the chat")
    assert out.exists() and out.stat().st_size > 0
    assert media_duration(out) > 0
    assert chatdrama._has_audio(out)  # ambient pad, not a video-only file


def test_render_chat_slides_cut_points(app, tmp_path):
    script = "\n".join(f"Me: line {i}" for i in range(6))
    paths = chatdrama.render_chat_slides(app, script, tmp_path, "c1", slides=3)
    assert len(paths) == 3
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


# --------------------------------------------------------------------------- #
# Carousels: padding + franchise variants
# --------------------------------------------------------------------------- #
def test_carousel_pads_short_image_prompts(app, llm, product, tmp_path):
    from mark.agents.media import _produce_carousel

    plan = _plan()
    draft = ContentDraft(caption="cap", hook="hook",
                         slide_texts=["one", "two", "three", "four"],
                         image_prompts=["only prompt"])
    result = _produce_carousel(app, llm, product, 9001, plan, draft, tmp_path)
    # Previously zip() silently dropped slides 2-4.
    assert len(result["media_paths"]) == 4
    assert all(Path(p).exists() for p in result["media_paths"])


def test_satirical_ui_carousel_renders_one_mockup_per_slide(app, llm, product):
    from mark.agents.media import produce_media

    plan = _plan(platform="instagram", content_type="carousel")
    draft = ContentDraft(caption="cap", hook="hook", slide_texts=[
        "TalentPortal", "text: Application received.",
        "button_disabled: Autofill", "counter: applicants 2,847"])
    strategy = SimpleNamespace(id="satirical-ui-franchise")
    result = produce_media(app, llm, product, 9002, plan, draft, strategy=strategy)
    assert len(result["media_paths"]) == 3  # one per spec row, progressive reveal
    assert all("mockup" in p and Path(p).exists() for p in result["media_paths"])


def test_fake_text_drama_carousel_renders_chat_slides(app, llm, product):
    from mark.agents.media import produce_media

    plan = _plan(platform="instagram", content_type="carousel")
    draft = ContentDraft(caption="cap", hook="hook",
                         script="Me: hey\nSam: news\nMe: what\nSam: we won",
                         slide_texts=["s1", "s2", "s3"])
    strategy = SimpleNamespace(id="fake-text-drama")
    result = produce_media(app, llm, product, 9003, plan, draft, strategy=strategy)
    assert len(result["media_paths"]) == 3
    # Chat-screenshot slides, not generative images (models garble bubble text).
    assert all("chat" in Path(p).name and Path(p).exists()
               for p in result["media_paths"])


# --------------------------------------------------------------------------- #
# Multi-shot b-roll: the mock path stitches N segments like the fal path would
# --------------------------------------------------------------------------- #
def test_shot_plan_splits_long_voiceovers():
    from mark.media import video

    assert video._shot_plan("scene", 8.0) == [("scene", 8)]
    shots = video._shot_plan("scene", 35.0)
    assert len(shots) == 4  # ceil(35/10)
    assert all(3 <= sec <= 10 for _, sec in shots)
    assert len({p for p, _ in shots}) == 4  # every shot prompt varies
    assert len(video._shot_plan("scene", 300.0)) == video._MAX_SHOTS  # cost cap


@needs_ffmpeg
def test_mock_broll_stitches_multi_segment_file(app, llm, product, tmp_path):
    from mark.media import video

    out = video._mock_broll(app, llm, "office b-roll", 25.0, tmp_path / "broll.mp4",
                            9004, product["id"])
    assert out.exists() and out.stat().st_size > 0
    # 25s voiceover → 3 shots, each its own clip before the concat.
    shots = sorted(tmp_path.glob("broll_shot*.mp4"))
    assert len(shots) == 3
    from mark.media.tts import media_duration
    assert media_duration(out) >= 20  # stitched length ≈ 3 × 8s, not a 10s loop


# --------------------------------------------------------------------------- #
# Degradation recording
# --------------------------------------------------------------------------- #
def test_record_degradation_writes_activity_and_error(app, product):
    from mark.agents.media import record_degradation

    cid = store.insert_content(
        app.conn, product_id=product["id"], platform="x", content_type="video",
        caption="c", hashtags=[], hook="h", media_paths=[], media_urls=[],
        strategy_context={}, status="draft")
    record_degradation(app, "fal video failed → static background",
                       content_id=cid, product_id=product["id"])
    row = store.get_content(app.conn, cid)
    assert "degraded: fal video failed" in (row["error"] or "")
    assert row["status"] == "draft"  # status untouched
    acts = db_module.query(app.conn,
                           "SELECT * FROM activity WHERE kind = 'media_degraded'")
    assert len(acts) == 1
    # Idempotent: the same reason isn't appended twice.
    record_degradation(app, "fal video failed → static background",
                       content_id=cid, product_id=product["id"])
    row = store.get_content(app.conn, cid)
    assert row["error"].count("degraded:") == 1
