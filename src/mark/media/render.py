"""EDL renderer — executes an edit decision list as ONE ffmpeg filtergraph.

Contract 3 of the content-templates build (docs/design/CONTENT-TEMPLATES-BUILD.md).
The whole edit — per-clip trim/speed/fit, crossfades, PNG/text overlays, audio
mix with music ducked under voiceover, caption burn-in, and the AI-disclosure
invariant — compiles to a single ffmpeg invocation (list args, no shell).

Fit modes:
  * ``cover``   — scale up + center-crop to fill the canvas (default b-roll).
  * ``contain`` — scale down + pad (pillarbox/letterbox to whatever fits).
  * ``window``  — the letterbox composer: canvas-colored 9:16 frame with the
    clip cover-cropped into a placement rect (e.g. a centered 1080x1080 window
    with ~420px bars top/bottom — the motivational-clips convention; the bars
    are part of the composition, so platforms never re-letterbox us).

Text rendering: the contract sketches drawtext, but the installed ffmpeg 8.1
(homebrew) is built WITHOUT libfreetype/libass — no drawtext, no ass/subtitles
filters. Text overlays and the disclosure label are therefore rendered as
transparent Pillow PNGs and composited with ``overlay`` + ``enable`` — fully
deterministic, identical on every ffmpeg build, and pixel-matched to the PIL
previews elsewhere in the codebase. Captions burn via the ``ass`` filter when
the build has libass; otherwise they degrade to a Pillow-rendered transparent
caption track (karaoke word-highlight preserved) overlaid on the timeline.

Safety: every EDL ``src`` must resolve under ``data/``, the EDL's own
directory, or ``src/mark/assets`` — the web editor POSTs EDLs, so all paths
are hostile input. Compliance: ``ai_generated: true`` burns a small
"AI-generated" label during t=0-5s. Not configurable off, not skipped in
proxy mode.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import textwrap
import time
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from .. import db
from ..app import App
from . import edl as edl_mod
from .images import _load_font, strip_emoji

log = logging.getLogger("mark.render")

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"

PROXY_WIDTH = 480
_AUDIO_FMT = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"

# Text overlay presets (sizes as fraction of canvas height; px at 1920 noted).
_TEXT_STYLES = {
    "hook":      {"size_frac": 0.040, "alpha": 255, "outline": 5, "wrap": 20},  # ~77px
    "quote":     {"size_frac": 0.036, "alpha": 255, "outline": 4, "wrap": 24},  # ~69px
    "watermark": {"size_frac": 0.019, "alpha": 150, "outline": 0, "wrap": 40},
    "default":   {"size_frac": 0.030, "alpha": 255, "outline": 4, "wrap": 26},
}

_CAPTION_CHUNK = 3          # words visible at once in the fallback karaoke
_CAPTION_HIGHLIGHT = (255, 255, 0, 255)   # active word — yellow, as build_ass uses
_CAPTION_Y_FRAC = {"karaoke": 0.64, "seam_band": 0.55, "static_scene": 0.50}


def render_edl(app: App, edl: "edl_mod.EDL", edl_dir: Path, out_path: Path,
               *, proxy: bool = False) -> Path:
    """Render ``edl`` to ``out_path``. Final: canvas-size H.264 CRF 18 yuv420p
    +faststart, AAC 128k. Proxy: 480-wide, ultrafast CRF 30, captions skipped
    (the web editor overlays captions client-side)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for EDL rendering")

    edl_dir = Path(edl_dir).resolve()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = edl.canvas
    fps = canvas.fps
    bg = _ff_color(canvas.background)

    clips = edl.clips  # validator sorted these by order
    durs = [edl_mod.clip_seconds(c) for c in clips]
    trans = edl_mod.transition_seconds(edl)
    total = edl_mod.visual_duration(edl)

    # Scratch dir for generated overlay/caption assets; ffmpeg runs from here
    # so any filter file args stay simple relative names (no path escaping).
    workdir = out_path.parent / f".{out_path.stem}_render"
    workdir.mkdir(parents=True, exist_ok=True)

    input_paths: list[Path] = [_resolve_src(c.src, edl_dir, app) for c in clips]
    fc: list[str] = []

    # ---- visual timeline -------------------------------------------------- #
    for i, c in enumerate(clips):
        fc.append(
            f"[{i}:v]trim=start={c.in_:.4f}:end={c.out:.4f},"
            f"setpts=(PTS-STARTPTS)/{c.speed:g},fps={fps},settb=AVTB,"
            f"{_fit_filter(c, canvas, bg)},setsar=1,format=yuv420p[v{i}]")

    vlabel, cur = "v0", durs[0]
    for i in range(1, len(clips)):
        d = trans[i - 1]
        if d > 0:
            fc.append(f"[{vlabel}][v{i}]xfade=transition=fade:duration={d:.3f}:"
                      f"offset={cur - d:.3f}[vx{i}]")
            vlabel, cur = f"vx{i}", cur + durs[i] - d
        else:
            fc.append(f"[{vlabel}][v{i}]concat=n=2:v=1:a=0[vc{i}]")
            vlabel, cur = f"vc{i}", cur + durs[i]

    # ---- overlays (master-timeline anchored) ------------------------------ #
    for j, ov in enumerate(edl.overlays):
        if ov.kind == "png":
            src = _resolve_src(ov.src, edl_dir, app)
            pos = f"x={ov.x or 0}:y={ov.y or 0}"
        else:  # text — rendered to a full-canvas transparent PNG (see module doc)
            src = _text_overlay_png(ov, canvas, workdir, j)
            pos = "x=0:y=0"
        idx = len(input_paths)
        input_paths.append(src)
        fc.append(f"[{vlabel}][{idx}:v]overlay={pos}:format=auto:"
                  f"enable='between(t,{ov.t0:.3f},{ov.t1:.3f})'[vo{j}]")
        vlabel = f"vo{j}"

    # ---- disclosure invariant: AI content is always labeled t=0-5s -------- #
    if edl.ai_generated:
        idx = len(input_paths)
        input_paths.append(_disclosure_png(canvas, workdir))
        fc.append(f"[{vlabel}][{idx}:v]overlay=x=0:y=0:format=auto:"
                  f"enable='between(t,0,5)'[vdisc]")
        vlabel = "vdisc"

    # ---- caption burn (final renders only) --------------------------------- #
    if not proxy and edl.captions.mode != "none":
        step = _caption_step(app, edl, canvas, workdir, total)
        if step is not None:
            kind, payload = step
            if kind == "ass":
                fc.append(f"[{vlabel}]{payload}[vsub]")
            else:  # transparent Pillow caption track (no libass in this build)
                idx = len(input_paths)
                input_paths.append(payload)
                fc.append(f"[{vlabel}][{idx}:v]overlay=x=0:y=0:format=auto[vsub]")
            vlabel = "vsub"

    tail = ""
    if proxy:
        ph = int(round(canvas.height * PROXY_WIDTH / canvas.width / 2) * 2)
        tail = f"scale={PROXY_WIDTH}:{ph},setsar=1,"
    fc.append(f"[{vlabel}]{tail}format=yuv420p[vout]")

    # ---- audio graph -------------------------------------------------------- #
    alabel = _audio_graph(edl, clips, durs, trans, input_paths, fc, edl_dir, app)

    # ---- one ffmpeg invocation ---------------------------------------------- #
    cmd = ["ffmpeg", "-y"]
    for p in input_paths:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", ";".join(fc),
            "-map", "[vout]", "-map", f"[{alabel}]", "-r", str(fps),
            "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if proxy:
        cmd += ["-preset", "ultrafast", "-crf", "30"]
    else:
        cmd += ["-preset", "veryfast", "-crf", "18", "-movflags", "+faststart"]
    cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-t", f"{total:.3f}", str(out_path.resolve())]

    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"EDL render failed (ffmpeg): {proc.stderr[-1200:]}")
    shutil.rmtree(workdir, ignore_errors=True)

    elapsed = time.monotonic() - started
    db.log_activity(
        app.conn, "render",
        f"EDL render {'proxy ' if proxy else ''}{out_path.name}: "
        f"{len(clips)} clips, {total:.1f}s video in {elapsed:.1f}s")
    return out_path


# --------------------------------------------------------------------------- #
# Path guard
# --------------------------------------------------------------------------- #
def _resolve_src(src: str, edl_dir: Path, app: App) -> Path:
    """Resolve an EDL src (relative to the EDL dir, or absolute) and reject
    anything outside data/, the EDL dir, or the bundled assets. EDLs arrive
    from the web editor — treat every path as hostile."""
    if not str(src or "").strip():
        raise ValueError("EDL src is empty")
    p = Path(src)
    if not p.is_absolute():
        p = edl_dir / p
    rp = p.resolve()
    allowed = (Path(app.paths.data_dir).resolve(), edl_dir.resolve(), _ASSETS_DIR)
    if not any(rp == a or rp.is_relative_to(a) for a in allowed):
        raise ValueError(f"EDL src outside allowed roots: {src}")
    if not rp.is_file():
        raise FileNotFoundError(f"EDL src not found: {src}")
    return rp


# --------------------------------------------------------------------------- #
# Video helpers
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _available_filters() -> frozenset[str]:
    """Names of filters the installed ffmpeg actually has — homebrew builds
    routinely lack drawtext/ass, so capability is probed, never assumed."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=30).stdout
        return frozenset(m.group(1) for m in
                         re.finditer(r"^\s*[A-Z.]+\s+([a-z0-9_]+)\s+\S+->", out, re.M))
    except Exception:
        return frozenset()


def _ff_color(color: str) -> str:
    color = (color or "#000000").strip()
    return "0x" + color[1:] if color.startswith("#") else color


def _fit_filter(clip, canvas, bg: str) -> str:
    w, h = canvas.width, canvas.height
    if clip.fit == "contain":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}")
    if clip.fit == "window":
        win = clip.window or edl_mod.Window()
        # Cover-crop INTO the window rect, then pad out to the full canvas —
        # the letterbox bars are rendered into the file on purpose.
        return (f"scale={win.w}:{win.h}:force_original_aspect_ratio=increase,"
                f"crop={win.w}:{win.h},pad={w}:{h}:{win.x}:{win.y}:color={bg}")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


# --------------------------------------------------------------------------- #
# Pillow text rendering (overlays + disclosure)
# --------------------------------------------------------------------------- #
def _outlined(draw, xy, text, font, fill, outline_w: int,
              outline=(0, 0, 0, 255), align="center") -> None:
    x, y = xy
    if outline_w:
        for dx in range(-outline_w, outline_w + 1):
            for dy in range(-outline_w, outline_w + 1):
                if dx or dy:
                    draw.multiline_text((x + dx, y + dy), text, font=font,
                                        fill=outline, align=align, spacing=10)
    draw.multiline_text((x, y), text, font=font, fill=fill, align=align, spacing=10)


def _text_overlay_png(ov, canvas, workdir: Path, j: int) -> Path:
    """Render a text overlay as a full-canvas transparent PNG. Full-canvas so
    the overlay filter always composites at 0:0 and centering math lives here."""
    style = _TEXT_STYLES.get(ov.style or "default") or _TEXT_STYLES["default"]
    size = max(18, round(canvas.height * style["size_frac"]))
    font = _load_font(size)
    text = textwrap.fill(strip_emoji(ov.text).strip(), width=style["wrap"])

    img = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=10)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = ov.x if ov.x is not None else (canvas.width - tw) / 2
    if ov.y is not None:
        y = ov.y
    elif ov.y_frac is not None:
        y = ov.y_frac * canvas.height
    else:
        y = (canvas.height - th) / 2
    _outlined(draw, (x, y), text, font, (255, 255, 255, style["alpha"]),
              style["outline"])
    path = workdir / f"overlay_text_{j}.png"
    img.save(path)
    return path


def _disclosure_png(canvas, workdir: Path) -> Path:
    """Small, unobtrusive, NOT optional: the burned 'AI-generated' label."""
    size = max(16, round(canvas.height * 28 / 1920))
    font = _load_font(size)
    img = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    text = "AI-generated"
    tw = draw.textlength(text, font=font)
    x, y = (canvas.width - tw) / 2, round(canvas.height * 0.025)
    _outlined(draw, (x, y), text, font, (255, 255, 255, 150), 1, (0, 0, 0, 110))
    path = workdir / "disclosure.png"
    img.save(path)
    return path


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def _caption_step(app: App, edl, canvas, workdir: Path,
                  total: float) -> tuple[str, object] | None:
    """Decide how captions get burned. Returns ("ass", filter_str) when libass
    is available and the caption engine built an ASS file, ("track", Path) for
    the Pillow fallback track, or None to skip (never crash a render over
    captions — log and degrade)."""
    if "ass" in _available_filters():
        try:
            from . import ass_captions  # built by the caption-engine agent

            ass_path = ass_captions.build_ass(
                edl.captions.model_dump(), canvas.model_dump(),
                workdir / "captions.ass")
            flt = f"ass=filename={Path(ass_path).name}"
            if _FONTS_DIR.is_dir():
                flt += f":fontsdir={_FONTS_DIR}"
            return ("ass", flt)
        except ImportError:
            log.info("ass_captions not available yet — using Pillow caption track")
        except Exception as exc:
            log.warning("ASS caption build failed (%s) — using Pillow caption track", exc)
    try:
        track = _caption_track(edl.captions, canvas, workdir, total)
        return ("track", track) if track else None
    except Exception as exc:
        log.warning("caption fallback failed — rendering without captions: %s", exc)
        return None


def _caption_states(cap) -> list[tuple[float, float, list[str], int | None]]:
    """Flatten the captions block into display states:
    (t0, t1, words_on_screen, highlighted_index)."""
    if cap.mode == "static_scene":
        return [(e.t0, e.t1, [e.text], None) for e in cap.events if e.t1 > e.t0]
    states: list[tuple[float, float, list[str], int | None]] = []
    words = cap.words
    for start in range(0, len(words), _CAPTION_CHUNK):
        chunk = words[start:start + _CAPTION_CHUNK]
        texts = [w.w for w in chunk]
        for k, w in enumerate(chunk):
            t1 = chunk[k + 1].t0 if k + 1 < len(chunk) else chunk[-1].t1
            if t1 > w.t0:
                states.append((w.t0, t1, texts, k))
    return states


def _caption_track(cap, canvas, workdir: Path, total: float) -> Path | None:
    """Pillow fallback for builds without libass: pre-render caption states as
    transparent frames and pack them into an alpha-preserving PNG-codec .mov
    (the chatdrama concat pattern), which the main graph overlays. This is
    asset preparation — the render itself stays one ffmpeg invocation."""
    states = [s for s in _caption_states(cap) if s[0] < total]
    if not states:
        return None
    states.sort(key=lambda s: s[0])

    size = max(18, round(canvas.height * 0.036))
    font = _load_font(size)
    y = round(canvas.height * _CAPTION_Y_FRAC.get(cap.mode, 0.64))

    blank = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
    blank_path = workdir / "cap_blank.png"
    blank.save(blank_path)

    seq: list[tuple[str, float]] = []  # (filename, duration)
    cursor = 0.0
    for n, (t0, t1, texts, hi) in enumerate(states):
        t0, t1 = max(t0, cursor), min(t1, total)
        if t1 <= t0:
            continue
        if t0 > cursor:
            seq.append((blank_path.name, t0 - cursor))
        frame = blank.copy()
        draw = ImageDraw.Draw(frame)
        if hi is None:  # static_scene: centered wrapped text
            text = textwrap.fill(strip_emoji(texts[0]), width=28)
            bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=10)
            x = (canvas.width - (bbox[2] - bbox[0])) / 2
            _outlined(draw, (x, y), text, font, (255, 255, 255, 255), 3)
        else:  # karaoke chunk with the active word highlighted
            clean = [strip_emoji(t) or t for t in texts]
            widths = [draw.textlength(t, font=font) for t in clean]
            gap = size * 0.35
            x = (canvas.width - (sum(widths) + gap * (len(clean) - 1))) / 2
            for k, (t, w) in enumerate(zip(clean, widths)):
                color = _CAPTION_HIGHLIGHT if k == hi else (255, 255, 255, 255)
                _outlined(draw, (x, y), t, font, color, 3)
                x += w + gap
        fp = workdir / f"cap_{n:04d}.png"
        frame.save(fp)
        seq.append((fp.name, t1 - t0))
        cursor = t1
    if cursor < total:
        seq.append((blank_path.name, total - cursor))

    lines = []
    for name, d in seq:
        lines.append(f"file '{name}'")
        lines.append(f"duration {d:.3f}")
    lines.append(f"file '{blank_path.name}'")  # concat quirk: repeat last entry
    lst = workdir / "cap_list.txt"
    lst.write_text("\n".join(lines))

    track = workdir / "captions_track.mov"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst.name,
         "-c:v", "png", track.name],
        cwd=str(workdir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"caption track encode failed: {proc.stderr[-500:]}")
    return track


# --------------------------------------------------------------------------- #
# Audio graph
# --------------------------------------------------------------------------- #
def _audio_graph(edl, clips, durs, trans, input_paths: list[Path], fc: list[str],
                 edl_dir: Path, app: App) -> str:
    """Append the audio filtergraph to ``fc`` and return its output label.

    voiceover(s) + music (sidechain-ducked under voiceover) + original clip
    audio (mute=False clips, silence-gapped and crossfaded to mirror the video
    fold so it never drifts). Zero tracks -> silence.
    """
    vo_labels: list[str] = []
    music: list[tuple[str, float | None]] = []  # (label, duck_db)
    sfx_labels: list[str] = []                   # one-shot effects, placed at t0

    for k, tr in enumerate(edl.audio):
        if tr.kind == "original" or not tr.src:
            continue
        idx = len(input_paths)
        input_paths.append(_resolve_src(tr.src, edl_dir, app))
        chain = f"[{idx}:a]{_AUDIO_FMT}"
        if tr.gain_db:
            chain += f",volume={tr.gain_db:g}dB"
        if tr.t0 > 0:
            chain += f",adelay={int(tr.t0 * 1000)}:all=1"
        label = f"atr{k}"
        fc.append(f"{chain}[{label}]")
        if tr.kind == "voiceover":
            vo_labels.append(label)
        elif tr.kind == "sfx":
            sfx_labels.append(label)
        else:
            music.append((label, tr.duck_db))

    orig = _original_audio(edl, clips, durs, trans, input_paths, fc)

    # Fold voiceovers to one label.
    vo = None
    if len(vo_labels) == 1:
        vo = vo_labels[0]
    elif vo_labels:
        fc.append("".join(f"[{l}]" for l in vo_labels)
                  + f"amix=inputs={len(vo_labels)}:duration=longest:normalize=0[avo]")
        vo = "avo"

    # Fold music to one label, then duck it under the voiceover.
    mus = None
    duck_db = next((d for _, d in music if d is not None), None)
    if len(music) == 1:
        mus = music[0][0]
    elif music:
        fc.append("".join(f"[{l}]" for l, _ in music)
                  + f"amix=inputs={len(music)}:duration=longest:normalize=0[amus]")
        mus = "amus"
    if mus and vo and duck_db is not None:
        ratio = min(20.0, max(2.0, abs(duck_db) / 1.5))
        fc.append(f"[{vo}]asplit=2[avoM][avoSC]")
        fc.append(f"[{mus}][avoSC]sidechaincompress=threshold=0.05:ratio={ratio:g}:"
                  f"attack=20:release=400[amusD]")
        vo, mus = "avoM", "amusD"

    mix = [l for l in (vo, mus, orig, *sfx_labels) if l]
    if not mix:  # zero audio tracks: silent AAC track so every player is happy
        fc.append("anullsrc=channel_layout=stereo:sample_rate=44100[aout]")
        return "aout"
    if len(mix) == 1:
        fc.append(f"[{mix[0]}]anull[aout]")
        return "aout"
    fc.append("".join(f"[{l}]" for l in mix)
              + f"amix=inputs={len(mix)}:duration=longest:normalize=0[aout]")
    return "aout"


def _original_audio(edl, clips, durs, trans, input_paths: list[Path],
                    fc: list[str]) -> str | None:
    """Passthrough audio for mute=False clips: each clip contributes its own
    (speed-matched) audio or an equal-length silence, folded exactly like the
    video (concat at cuts, acrossfade at crossfades) so it stays in sync."""
    track = next((t for t in edl.audio if t.kind == "original"), None)
    if track is None:
        return None

    segs = []
    for i, c in enumerate(clips):
        label = f"oa{i}"
        if not c.mute and _has_audio(input_paths[i]):
            fc.append(f"[{i}:a]atrim=start={c.in_:.4f}:end={c.out:.4f},"
                      f"asetpts=PTS-STARTPTS,atempo={c.speed:g},{_AUDIO_FMT}[{label}]")
        else:
            fc.append(f"aevalsrc=0:s=44100:d={durs[i]:.4f},{_AUDIO_FMT}[{label}]")
        segs.append(label)

    label = segs[0]
    for i in range(1, len(segs)):
        d = trans[i - 1]
        nxt = f"oax{i}"
        if d > 0:
            fc.append(f"[{label}][{segs[i]}]acrossfade=d={d:.3f}:c1=tri:c2=tri[{nxt}]")
        else:
            fc.append(f"[{label}][{segs[i]}]concat=n=2:v=0:a=1[{nxt}]")
        label = nxt

    if track.gain_db:
        fc.append(f"[{label}]volume={track.gain_db:g}dB[oag]")
        label = "oag"
    return label


def _has_audio(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return "audio" in out.stdout
    except Exception:
        return False
