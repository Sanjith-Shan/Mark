"""Sourcing layer: stock search/download (mock mode produces REAL playable
clips, cached), yt-dlp wrapper mock path, and twitch mock shapes. Live smoke
tests are skipped unless the relevant keys are present."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mark.sourcing import stock, twitch, ytdlp


def ffprobe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"ffprobe failed: {proc.stderr[-300:]}"
    return json.loads(proc.stdout)


def video_stream(info: dict) -> dict:
    return next(s for s in info["streams"] if s["codec_type"] == "video")


# --------------------------------------------------------------------------- #
# Stock — mock mode
# --------------------------------------------------------------------------- #
def test_stock_mock_search_shape(app):
    items = stock.search_videos(app, "boxing gym rain", provider="pexels")
    assert 2 <= len(items) <= 3
    for item in items:
        for key in ("id", "provider", "url", "width", "height", "duration",
                    "preview_image", "download_url"):
            assert key in item, f"missing {key}"
        assert item["provider"] == "pexels"
        assert item["height"] > item["width"], "portrait orientation expected"
    # Deterministic: same query → same ids.
    assert [i["id"] for i in items] == \
        [i["id"] for i in stock.search_videos(app, "boxing gym rain")]


def test_stock_mock_search_landscape_and_pixabay(app):
    items = stock.search_videos(app, "city night", orientation="landscape",
                                provider="pixabay")
    assert items and all(i["width"] > i["height"] for i in items)
    assert all(i["provider"] == "pixabay" for i in items)


def test_stock_unknown_provider_rejected(app):
    with pytest.raises(ValueError):
        stock.search_videos(app, "lions", provider="shutterstock")


def test_stock_mock_download_is_real_playable_video(app):
    item = stock.search_videos(app, "mountain sunrise")[0]
    path = stock.download_video(app, item)
    assert path.exists() and path.suffix == ".mp4"
    # Cached under data/assets/stock/{provider}/{id}.mp4
    assert path == app.paths.data_dir / "assets" / "stock" / "pexels" / f"{item['id']}.mp4"
    info = ffprobe(path)
    vs = video_stream(info)
    assert (vs["width"], vs["height"]) == (1080, 1920)
    assert abs(float(info["format"]["duration"]) - 8.0) < 1.0
    assert any(s["codec_type"] == "audio" for s in info["streams"])


def test_stock_download_cache_hit(app):
    item = stock.search_videos(app, "rowing crew")[0]
    first = stock.download_video(app, item)
    mtime = first.stat().st_mtime_ns
    second = stock.download_video(app, item)
    assert second == first
    assert second.stat().st_mtime_ns == mtime, "cache miss — file regenerated"


# --------------------------------------------------------------------------- #
# yt-dlp — mock path
# --------------------------------------------------------------------------- #
def test_ytdlp_mock_download(app, tmp_path):
    out = ytdlp.download("mock:Test Clip 1", tmp_path / "clips")
    assert out.exists() and out.suffix == ".mp4"
    vs = video_stream(ffprobe(out))
    assert (vs["width"], vs["height"]) == (1080, 1920)
    # Idempotent: re-download reuses the file.
    assert ytdlp.download("mock:Test Clip 1", tmp_path / "clips") == out


def test_ytdlp_mock_probe():
    meta = ytdlp.probe("mock:Test Clip 1")
    assert meta["id"] == "test-clip-1"
    assert meta["duration"] == 8.0
    assert meta["mock"] is True


# --------------------------------------------------------------------------- #
# Twitch — mock shapes
# --------------------------------------------------------------------------- #
def test_twitch_mock_streams_shape(app):
    streams = twitch.get_streams(app, logins=["mockstreamer", "pixelqueen"])
    assert streams
    for s in streams:
        for key in ("id", "user_id", "user_login", "user_name", "game_id",
                    "game_name", "title", "viewer_count", "started_at",
                    "language", "thumbnail_url"):
            assert key in s
        assert isinstance(s["viewer_count"], int)


def test_twitch_mock_clips_shape_and_pagination(app):
    clips, cursor = twitch.get_clips(app, "41001", first=5)
    assert clips and cursor
    views = [c["view_count"] for c in clips]
    assert views == sorted(views, reverse=True), "Helix returns descending views"
    for c in clips:
        for key in ("id", "url", "broadcaster_id", "broadcaster_name",
                    "creator_name", "video_id", "game_id", "title",
                    "view_count", "created_at", "duration", "vod_offset",
                    "thumbnail_url"):
            assert key in c
        assert c["broadcaster_id"] == "41001"
    # Cursor round-trips; the mock has one page.
    more, end = twitch.get_clips(app, "41001", after=cursor)
    assert more == [] and end is None


def test_twitch_mock_users_shape(app):
    users = twitch.get_users(app, ["mockstreamer", "someoneelse"])
    assert len(users) == 2
    for u in users:
        for key in ("id", "login", "display_name", "description",
                    "profile_image_url", "created_at"):
            assert key in u
    assert twitch.get_users(app, []) == []


# --------------------------------------------------------------------------- #
# Live smoke tests — run only when keys are present (absent in CI/dev here)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not os.environ.get("PEXELS_API_KEY"),
                    reason="PEXELS_API_KEY not set")
def test_live_pexels_search(app):
    app.force_mock = False
    items = stock.search_videos(app, "ocean waves", per_page=3)
    assert items and all(i["download_url"].startswith("http") for i in items)


@pytest.mark.skipif(not os.environ.get("PIXABAY_API_KEY"),
                    reason="PIXABAY_API_KEY not set")
def test_live_pixabay_search(app):
    app.force_mock = False
    items = stock.search_videos(app, "ocean waves", per_page=3,
                                provider="pixabay")
    assert items and all(i["download_url"].startswith("http") for i in items)


@pytest.mark.skipif(
    not (os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET")),
    reason="TWITCH_CLIENT_ID/SECRET not set")
def test_live_twitch_streams(app):
    app.force_mock = False
    streams = twitch.get_streams(app, first=5)
    assert streams and all(s["viewer_count"] >= 0 for s in streams)
