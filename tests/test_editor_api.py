"""Editor API tests — the clip/caption editor (Contract 6).

Exercises the EDL round-trip (GET/POST /api/edit), invalid-EDL rejection, and a
REAL proxy render (ffmpeg, lavfi test sources — no API keys) producing a smaller
480p file than a full render. Reuses the module-scoped TestClient from
test_api.py so the offline (mock) app + temp home are shared.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mark import store
from mark.media import edl as edl_mod
from mark.media import render as render_mod

from .test_api import client, make_campaign, wait_job  # noqa: F401 (fixture reuse)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg required for EDL rendering")


def _lavfi_clip(path: Path, color: str, dur: float = 2.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:size=640x360:rate=30:duration={dur}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True)


def _sine(path: Path, dur: float = 4.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={dur}",
         "-q:a", "5", str(path)],
        check=True, capture_output=True)


def _seed_editable(client, cid_hint: str = "editco") -> tuple[int, Path]:
    """Create a campaign + a content row with a real edit.json + clip assets in
    its media dir, wired via content.edl_path. Returns (content_id, edl_dir)."""
    camp = make_campaign(client, cid_hint, platforms=["tiktok"])
    app = client.app.state.runtime.app()
    content_id = store.insert_content(
        app.conn, product_id=camp, platform="tiktok", content_type="video",
        caption="editable clip", hook="watch this", status="draft", media_paths=[])
    edl_dir = app.paths.media_dir / camp / "edit" / str(content_id)
    edl_dir.mkdir(parents=True, exist_ok=True)

    _lavfi_clip(edl_dir / "clip1.mp4", "red")
    _lavfi_clip(edl_dir / "clip2.mp4", "blue")
    _sine(edl_dir / "vo.mp3")

    edl = edl_mod.EDL.model_validate({
        "version": 1,
        "ai_generated": True,
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "clips": [
            {"id": "c1", "src": "clip1.mp4", "in": 0.0, "out": 2.0, "order": 0, "mute": True},
            {"id": "c2", "src": "clip2.mp4", "in": 0.0, "out": 2.0, "order": 1, "mute": True},
        ],
        "captions": {"mode": "karaoke", "style": "hormozi", "words": [
            {"w": "watch", "t0": 0.0, "t1": 0.6},
            {"w": "this", "t0": 0.6, "t1": 1.2},
        ]},
        "audio": [{"src": "vo.mp3", "kind": "voiceover", "gain_db": 0.0}],
    })
    ejp = edl_mod.edl_path_for(edl_dir)
    edl_mod.save(edl, ejp)
    store.update_content(app.conn, content_id, edl_path=str(ejp),
                         media_paths=[str(edl_dir / f"{content_id}_tiktok_video.mp4")])
    return content_id, edl_dir


def test_edit_get_returns_edl_styles_fonts(client):
    cid, _ = _seed_editable(client, "editco-get")
    resp = client.get(f"/api/edit/{cid}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content_id"] == cid
    assert len(data["edl"]["clips"]) == 2
    # clips use the "in" alias, not "in_"
    assert data["edl"]["clips"][0]["in"] == 0.0
    assert data["edl"]["captions"]["mode"] == "karaoke"
    assert any(s["id"] == "hormozi" for s in data["styles"])
    assert any(f["family"] == "Montserrat ExtraBold" for f in data["fonts"])
    assert data["audio_url"] and data["audio_url"].endswith("vo.mp3")
    # sfx_available reflects whether the (parallel) SFX engine has shipped a
    # manifest — either way the editor degrades gracefully.
    assert isinstance(data["sfx_available"], bool)


def test_edit_get_404_when_no_edl(client):
    camp = make_campaign(client, "editco-noedl", platforms=["x"])
    app = client.app.state.runtime.app()
    cid = store.insert_content(app.conn, product_id=camp, platform="x",
                               content_type="text", caption="no edl", status="draft")
    resp = client.get(f"/api/edit/{cid}")
    assert resp.status_code == 404


def test_edit_save_roundtrip(client):
    cid, _ = _seed_editable(client, "editco-save")
    data = client.get(f"/api/edit/{cid}").json()
    edl = data["edl"]
    # Reorder the two clips and nudge a caption word.
    edl["clips"][0]["order"] = 5
    edl["clips"][1]["order"] = 1
    edl["captions"]["words"][0]["t1"] = 0.8
    resp = client.post(f"/api/edit/{cid}", json=edl)
    assert resp.status_code == 200, resp.text

    reloaded = client.get(f"/api/edit/{cid}").json()["edl"]
    # EDL validator sorts by order, so c2 (order 1) now precedes c1 (order 5).
    assert [c["id"] for c in reloaded["clips"]] == ["c2", "c1"]
    assert reloaded["captions"]["words"][0]["t1"] == 0.8


def test_edit_save_rejects_invalid(client):
    cid, _ = _seed_editable(client, "editco-invalid")
    edl = client.get(f"/api/edit/{cid}").json()["edl"]
    edl["clips"] = []  # EDL needs at least one clip
    resp = client.post(f"/api/edit/{cid}", json=edl)
    assert resp.status_code == 400

    edl2 = client.get(f"/api/edit/{cid}").json()["edl"]
    edl2["clips"][0]["out"] = edl2["clips"][0]["in"]  # out must be > in
    resp2 = client.post(f"/api/edit/{cid}", json=edl2)
    assert resp2.status_code == 400


def test_edit_proxy_render_is_smaller(client):
    cid, edl_dir = _seed_editable(client, "editco-proxy")
    # Full render as a size baseline (same EDL, captions burned, canvas-size).
    app = client.app.state.runtime.app()
    edl = edl_mod.load(edl_mod.edl_path_for(edl_dir))
    final = edl_dir / "final_baseline.mp4"
    render_mod.render_edl(app, edl, edl_dir, final, proxy=False)

    resp = client.post(f"/api/edit/{cid}/proxy")
    assert resp.status_code == 200, resp.text
    job = wait_job(client, resp.json()["job_id"])
    proxy = edl_dir / "proxy.mp4"
    assert proxy.is_file()
    assert job["result"]["proxy_url"].endswith("proxy.mp4")

    # Proxy is 480-wide ultrafast CRF30 → materially smaller than the final.
    assert proxy.stat().st_size < final.stat().st_size
    w = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width", "-of", "csv=p=0", str(proxy)],
        capture_output=True, text=True).stdout.strip()
    assert w == "480"


def test_sfx_endpoint_and_fonts_served(client):
    # SFX library is a list (empty when the engine hasn't shipped a manifest;
    # populated otherwise). Every item, if any, carries a slug + name.
    sfx = client.get("/api/sfx").json()
    assert isinstance(sfx, list)
    for item in sfx:
        assert item.get("slug") and item.get("name")
    resp = client.get("/api/fonts/Montserrat-ExtraBold.ttf")
    assert resp.status_code == 200
    assert len(resp.content) > 1000
    # Only allowlisted font files are served.
    assert client.get("/api/fonts/secret.ttf").status_code == 404
