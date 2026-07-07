"""EDL renderer tests — real ffmpeg renders against lavfi-generated media.

These exercise the actual ffmpeg pipeline (no mocking of the render): fit modes,
crossfades, the letterbox composer, Pillow text overlays, the caption fallback
track, the AI-disclosure invariant, proxy mode, and the path-traversal guard.
Skipped cleanly if ffmpeg is absent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mark.media import edl as E
from mark.media import render

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def _lavfi(path: Path, color: str, dur: float = 4.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:d={dur}:r=30",
         "-vf", f"drawbox=t=fill:c={color}@0.4", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)


def _solid(path: Path, color: str, dur: float = 4.0) -> None:
    """A genuinely uniform-color source (unlike testsrc) so small burned-in
    text is detectable against it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d={dur}:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True)


def _sine(path: Path, freq: int = 330, dur: float = 6.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
         "-c:a", "aac", str(path)], check=True, capture_output=True)


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


def _media(app) -> Path:
    d = Path(app.paths.data_dir) / "media" / "edltest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_cover_crossfade_render(app):
    d = _media(app)
    _lavfi(d / "a.mp4", "red"); _lavfi(d / "b.mp4", "blue")
    edl = E.EDL(
        ai_generated=False,
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[
            E.Clip(id="c1", src="media/edltest/a.mp4", in_=0, out=3, order=0,
                   fit="cover", transition={"type": "crossfade", "duration": 0.5}),
            E.Clip(id="c2", src="media/edltest/b.mp4", in_=0, out=3, order=1, fit="cover"),
        ],
        captions=E.Captions(mode="none"), audio=[],
    )
    out = d / "cover.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=False)
    info = _probe(out)
    assert info["codec_name"] == "h264"
    assert (int(info["width"]), int(info["height"])) == (1080, 1920)
    # 3 + 3 - 0.5 crossfade = 5.5s
    assert abs(float(info["duration"]) - 5.5) < 0.4


def test_letterbox_window_and_overlays(app):
    d = _media(app)
    _lavfi(d / "w.mp4", "green")
    edl = E.EDL(
        ai_generated=False,
        canvas=E.Canvas(width=1080, height=1920, fps=30, background="#000000"),
        clips=[E.Clip(id="c1", src="media/edltest/w.mp4", in_=0, out=4, order=0,
                      fit="window", window=E.Window(x=0, y=420, w=1080, h=1080), mute=True)],
        overlays=[E.Overlay(kind="text", text="STAY HARD", t0=0, t1=4, y_frac=0.08, style="quote")],
        captions=E.Captions(mode="none"), audio=[],
    )
    out = d / "letterbox.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=False)
    info = _probe(out)
    assert (int(info["width"]), int(info["height"])) == (1080, 1920)
    # Sample a top-corner region — inside the black letterbox bar (y<420) and
    # away from the horizontally-centered quote text.
    frame = d / "topbar.png"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(out), "-vf",
                    "crop=150:150:20:230", "-vframes", "1", str(frame)],
                   capture_output=True)
    from PIL import Image
    im = Image.open(frame).convert("RGB")
    px = im.getpixel((20, 20))
    assert sum(px) < 60, f"expected black letterbox bar, got {px}"


def test_karaoke_caption_fallback_track(app):
    """Pillow caption track path (this ffmpeg lacks libass) must render."""
    d = _media(app)
    _lavfi(d / "k.mp4", "orange", dur=3)
    words = [("Never", 0.0, 0.4), ("apply", 0.4, 0.8), ("manually", 0.8, 1.4),
             ("again", 1.4, 2.0)]
    edl = E.EDL(
        ai_generated=False,
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[E.Clip(id="c1", src="media/edltest/k.mp4", in_=0, out=2, order=0, fit="cover")],
        captions=E.Captions(mode="karaoke", style="hormozi",
                             words=[E.CaptionWord(w=w, t0=a, t1=b) for w, a, b in words]),
        audio=[],
    )
    out = d / "karaoke.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=False)
    assert out.exists() and _probe(out)["codec_name"] == "h264"


def test_ai_disclosure_invariant(app):
    """ai_generated=True burns a label present at t<5 and gone after."""
    d = _media(app)
    _solid(d / "disc.mp4", "black", dur=8)   # genuinely black bg → white label detectable
    edl = E.EDL(
        ai_generated=True,
        canvas=E.Canvas(width=1080, height=1920, fps=30, background="#000000"),
        clips=[E.Clip(id="c1", src="media/edltest/disc.mp4", in_=0, out=8, order=0, fit="cover")],
        captions=E.Captions(mode="none"), audio=[],
    )
    out = d / "disc_out.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=False)
    from PIL import Image

    def top_ink(t: float) -> int:
        f = d / f"disc_{t}.png"
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(out), "-vf",
                        "crop=1080:130:0:20", "-vframes", "1", str(f)], capture_output=True)
        im = Image.open(f).convert("L")
        return sum(1 for p in im.get_flattened_data() if p > 120)

    early = top_ink(2.0)
    late = top_ink(6.5)
    assert early > 200, f"disclosure label should be visible at t=2 (got {early} bright px)"
    assert late < early / 3, f"disclosure should be gone after 5s (t=2:{early} t=6.5:{late})"


def test_proxy_mode_is_smaller_and_fast(app):
    d = _media(app)
    _lavfi(d / "p.mp4", "blue", dur=3)
    edl = E.EDL(
        ai_generated=True,  # disclosure still burns in proxy
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[E.Clip(id="c1", src="media/edltest/p.mp4", in_=0, out=2, order=0, fit="cover")],
        captions=E.Captions(mode="none"), audio=[],
    )
    out = d / "proxy.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=True)
    assert int(_probe(out)["width"]) == render.PROXY_WIDTH


def test_path_traversal_rejected(app):
    d = _media(app)
    _lavfi(d / "ok.mp4", "red")
    edl = E.EDL(
        ai_generated=False,
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[E.Clip(id="c1", src="/etc/passwd", in_=0, out=1, order=0, fit="cover")],
        captions=E.Captions(mode="none"), audio=[],
    )
    with pytest.raises(ValueError, match="outside allowed roots"):
        render.render_edl(app, edl, Path(app.paths.data_dir), d / "x.mp4")


def test_audio_ducking_render(app):
    d = _media(app)
    _lavfi(d / "av.mp4", "green", dur=4)
    _sine(d / "vo.m4a", 440, 4); _sine(d / "music.m4a", 220, 4)
    edl = E.EDL(
        ai_generated=False,
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[E.Clip(id="c1", src="media/edltest/av.mp4", in_=0, out=3, order=0, fit="cover", mute=True)],
        captions=E.Captions(mode="none"),
        audio=[E.AudioTrack(src="media/edltest/vo.m4a", kind="voiceover", gain_db=0),
               E.AudioTrack(src="media/edltest/music.m4a", kind="music", gain_db=-6, duck_db=-12)],
    )
    out = d / "ducked.mp4"
    render.render_edl(app, edl, Path(app.paths.data_dir), out, proxy=False)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=codec_name", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True)
    assert "aac" in r.stdout
