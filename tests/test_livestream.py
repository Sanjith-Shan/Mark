"""Livestream clipping template — discovery, ranking, and the stacked-9:16
produce pipeline. Runs fully offline (twitch mock + yt-dlp lavfi mock + align
even-spacing); the produce test renders a REAL playable MP4 with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mark import db as db_module
from mark import store
from mark.schemas import ContentPlan, ContentDraft
from mark.templates import livestream

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


# --------------------------------------------------------------------------- #
# Strategy shape
# --------------------------------------------------------------------------- #
def test_strategy_never_auto_approves():
    assert livestream.STRATEGY.id == "stream-clips"
    assert livestream.STRATEGY.never_auto_approve is True
    assert livestream.STRATEGY.requires_product is False
    assert "video" in livestream.STRATEGY.content_types


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_refresh_populates_stream_finds(app, llm):
    stored = livestream.refresh(app, llm)
    assert stored, "mock twitch roster produced no clips"
    rows = db_module.query(app.conn, "SELECT * FROM stream_finds")
    assert len(rows) >= len(stored)
    for r in rows:
        assert r["external_id"].startswith("twitch:")
        assert 0.0 <= (r["keep"] or 0) <= 1.0
        assert r["stage"] in ("new", "rising", "mature", "declining")
        assert r["streamer"]


def test_velocity_and_stage_on_second_refresh(app, llm):
    livestream.refresh(app, llm)
    # Backdate first sightings 3h and lower their view_count, then re-sight
    # with today's (higher) counts → positive velocity + a rising stage.
    db_module.execute(app.conn,
                      "UPDATE stream_finds SET collected_at = datetime('now', '-3 hours')")
    db_module.execute(app.conn, "UPDATE stream_finds SET view_count = view_count - 2000")
    livestream.refresh(app, llm)
    row = db_module.query_one(
        app.conn,
        "SELECT velocity, stage FROM stream_finds ORDER BY collected_at DESC, id DESC LIMIT 1")
    assert row["velocity"] is not None and row["velocity"] > 0
    assert row["stage"] == "rising"


def test_radar_ranks_and_vetoes(app, llm):
    livestream.refresh(app, llm)
    finds = livestream.radar(app, llm, limit=20)
    assert finds
    scores = [f["radar_score"] for f in finds]
    assert scores == sorted(scores, reverse=True), "radar not ranked"

    # Unsafe (licensed music) and declining finds are hard-vetoed.
    ext = finds[0]["external_id"]
    db_module.execute(app.conn, "UPDATE stream_finds SET safe = 0 WHERE external_id = ?", (ext,))
    assert ext not in {f["external_id"] for f in livestream.radar(app, llm, limit=20)}


# --------------------------------------------------------------------------- #
# Produce — real stacked 9:16 render, offline
# --------------------------------------------------------------------------- #
def _make_content(app, find_id: int | None) -> int:
    sctx = {"strategy": "stream-clips"}
    if find_id is not None:
        sctx["stream_find_id"] = find_id
    return store.insert_content(
        app.conn, product_id="testco", platform="tiktok", content_type="video",
        caption="clip", hashtags=[], hook="", media_paths=[], media_urls=[],
        strategy_context=sctx, status="draft")


def _probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,codec_name", "-of", "default=nw=1", str(path)],
        capture_output=True, text=True)
    out = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_produce_renders_stacked_short(app, llm):
    livestream.refresh(app, llm)
    find = db_module.query_one(
        app.conn, "SELECT id FROM stream_finds ORDER BY keep DESC LIMIT 1")
    content_id = _make_content(app, find["id"])
    out_dir = Path(app.paths.media_dir) / "testco" / "streamtest" / str(content_id)
    plan = ContentPlan(platform="tiktok", content_type="video", topic="clip",
                       angle="", hook_style="story", tone="funny")
    draft = ContentDraft(caption="clip", script=None)

    result = livestream.produce(app, llm, {"id": "testco"}, content_id, plan, draft, out_dir)
    paths = result["media_paths"]
    assert paths and Path(paths[0]).exists()
    info = _probe(Path(paths[0]))
    assert info["codec_name"] == "h264"
    assert (int(info["width"]), int(info["height"])) == (1080, 1920)
    # The EDL was persisted and marks this as real (not AI) footage.
    from mark.media import edl as edl_mod
    saved = edl_mod.load(edl_mod.edl_path_for(out_dir))
    assert saved.ai_generated is False
    assert saved.audio and saved.audio[0].kind == "original"
    assert saved.clips[0].mute is False


def test_produce_falls_back_to_top_radar_item(app, llm):
    livestream.refresh(app, llm)
    content_id = _make_content(app, None)  # no stream_find_id → top radar item
    out_dir = Path(app.paths.media_dir) / "testco" / "streamtest2" / str(content_id)
    plan = ContentPlan(platform="youtube", content_type="video", topic="clip",
                       angle="", hook_style="story", tone="funny")
    draft = ContentDraft(caption="clip")
    result = livestream.produce(app, llm, {"id": "testco"}, content_id, plan, draft, out_dir)
    assert result["media_paths"] and Path(result["media_paths"][0]).exists()
