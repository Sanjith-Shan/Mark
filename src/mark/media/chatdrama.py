"""Chat-drama video renderer (fake-text-drama strategy).

Renders a scripted message-thread conversation as a vertical video: messages
appear one by one in a chat UI, paced by length so each beat is readable
(cliffhanger pacing is the strategy's engine). Fully deterministic — Pillow
frames + ffmpeg concat, no generative models, no AI-labeling risk.

Script format (what the writer produces for this strategy): one message per
line as ``Sender: message``. Senders named me/you/us render as the blue
right-side bubbles; everyone else renders left with a name label. Bare lines
become narrator cards.

Audio: dead silence gets scrolled past, so every render carries a backing
track — a user-supplied asset at ``data/assets/chatdrama_bg.(mp3|wav|mp4)``
when present (an .mp4 also becomes the visual backdrop behind the bubbles,
the gameplay-b-roll pattern), else a quiet synthetic pad generated offline.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..app import App
from .images import _load_font, strip_emoji

WIDTH, HEIGHT, FPS = 1080, 1920, 30

BG = (16, 18, 24)
HEADER = (28, 31, 40)
HEADER_TEXT = (240, 242, 246)
BUBBLE_THEM = (44, 48, 60)
BUBBLE_ME = (37, 99, 235)
BUBBLE_TEXT = (240, 242, 246)
NAME_TEXT = (148, 155, 170)
NARRATOR = (200, 205, 216)

MINE = {"me", "you (me)", "us", "myself"}

MIN_BEAT = 0.7  # absolute floor per message when compressing to fit


def parse_script(script: str) -> list[dict]:
    msgs = []
    for raw in (script or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^([^:]{1,24}):\s*(.+)$", line)
        if m:
            sender = m.group(1).strip()
            msgs.append({"sender": sender, "text": m.group(2).strip(),
                         "mine": sender.lower() in MINE})
        else:
            msgs.append({"sender": None, "text": line, "mine": False})
    return msgs


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out or [""]


def _render_frame(title: str, visible: list[dict], translucent: bool = False) -> Image.Image:
    # Emoji render as tofu boxes in PIL truetype fonts — strip at render time
    # only; the caption/script in the DB keeps them.
    title = strip_emoji(title)
    visible = [dict(m, text=strip_emoji(m["text"]),
                    sender=strip_emoji(m["sender"]) if m["sender"] else None)
               for m in visible]
    if translucent:
        # Over a video backdrop: let the b-roll show through the chat area.
        img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG, 150))
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    font = _load_font(44)
    name_font = _load_font(30)
    title_font = _load_font(48)

    # Header.
    draw.rectangle([0, 0, WIDTH, 170], fill=HEADER)
    tw = draw.textlength(title, font=title_font)
    draw.text(((WIDTH - tw) / 2, 90), title, font=title_font, fill=HEADER_TEXT)
    draw.ellipse([WIDTH / 2 - 28, 20, WIDTH / 2 + 28, 76], fill=BUBBLE_THEM)

    # Measure bubbles bottom-up so the newest message is always on screen.
    max_bubble_w = int(WIDTH * 0.68)
    pad_x, pad_y, gap = 30, 24, 26
    line_h = 54

    blocks = []
    for m in visible:
        lines = _wrap(draw, m["text"], font, max_bubble_w - 2 * pad_x)
        bw = max(int(draw.textlength(ln, font=font)) for ln in lines) + 2 * pad_x
        bh = len(lines) * line_h + 2 * pad_y
        name_h = 40 if (m["sender"] and not m["mine"]) else 0
        blocks.append((m, lines, bw, bh, name_h))

    y = HEIGHT - 90
    drawn = []
    for block in reversed(blocks):
        m, lines, bw, bh, name_h = block
        y -= bh + name_h + gap
        if y < 210:
            break
        drawn.append((y, block))
    for y, (m, lines, bw, bh, name_h) in drawn:
        if m["sender"] is None:  # narrator card
            for i, ln in enumerate(_wrap(draw, m["text"], name_font, WIDTH - 200)):
                lw = draw.textlength(ln, font=name_font)
                draw.text(((WIDTH - lw) / 2, y + name_h + i * 40), ln,
                          font=name_font, fill=NARRATOR)
            continue
        x = WIDTH - bw - 40 if m["mine"] else 40
        if name_h:
            draw.text((x + 12, y), m["sender"], font=name_font, fill=NAME_TEXT)
        by = y + name_h
        draw.rounded_rectangle([x, by, x + bw, by + bh], radius=34,
                               fill=BUBBLE_ME if m["mine"] else BUBBLE_THEM)
        ty = by + pad_y
        for ln in lines:
            draw.text((x + pad_x, ty), ln, font=font, fill=BUBBLE_TEXT)
            ty += line_h
    return img


def _beat_seconds(text: str) -> float:
    # Readable pacing: short texts snap, long texts hold. ~8s beats max.
    return max(1.2, min(0.9 + 0.045 * len(text), 3.6))


def plan_beats(msgs: list[dict], max_duration: float) -> tuple[list[dict], list[float]]:
    """Fit ALL messages inside ``max_duration`` by compressing pacing first.

    Truncating from the end silently killed the payoff/cliffhanger message (the
    strategy's whole engine). Instead: scale every beat down (floored at
    MIN_BEAT); only if even minimum pacing can't fit, drop MIDDLE messages —
    the opener and the final payoff always survive.
    """
    durations = [_beat_seconds(m["text"]) for m in msgs]
    total = sum(durations)
    if total > max_duration:
        scale = max_duration / total
        durations = [max(d * scale, MIN_BEAT) for d in durations]
    msgs = list(msgs)
    while len(msgs) > 2 and sum(durations) > max_duration:
        mid = len(msgs) // 2
        del msgs[mid], durations[mid]
    if durations and sum(durations) > max_duration:
        # 1-2 messages still too long — hard clamp, nothing left to drop.
        scale = max_duration / sum(durations)
        durations = [d * scale for d in durations]
    return msgs, durations


def render_chat_video(app: App, script: str, out_path: Path,
                      title: str = "job hunt support group 💀",
                      max_duration: float = 120.0) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for video assembly")
    msgs = parse_script(script)
    if not msgs:
        raise ValueError("chat drama script has no messages")

    out_path = Path(out_path)
    work = out_path.parent / f"{out_path.stem}_frames"
    work.mkdir(parents=True, exist_ok=True)

    msgs, durations = plan_beats(msgs, max_duration)
    total = sum(durations)

    bg_asset = _find_bg_asset(app)
    bg_video = bg_asset if (bg_asset and bg_asset.suffix.lower() == ".mp4") else None

    frames = []
    for i in range(len(msgs)):
        frame = work / f"frame_{i:03d}.png"
        _render_frame(title, msgs[: i + 1], translucent=bg_video is not None).save(frame)
        frames.append((frame, durations[i]))

    # ffmpeg concat demuxer with per-frame durations.
    concat = work / "list.txt"
    lines = []
    for frame, d in frames:
        lines.append(f"file '{frame.name}'")
        lines.append(f"duration {d:.2f}")
    lines.append(f"file '{frames[-1][0].name}'")  # concat quirk: repeat last
    concat.write_text("\n".join(lines))

    # Audio: asset track when supplied, else a quiet synthetic pad (offline).
    if bg_asset and bg_asset.suffix.lower() in (".mp3", ".wav"):
        audio_input = ["-stream_loop", "-1", "-i", str(bg_asset.resolve())]
        audio_filter = ["-af", "volume=0.3"]  # backing track, not the show
    elif bg_video is not None and _has_audio(bg_video):
        audio_input = None  # take it from the looped backdrop video
        audio_filter = ["-af", "volume=0.3"]
    else:
        pad = work / "ambient.wav"
        _ambient_pad(pad, total)
        audio_input = ["-i", pad.name]
        audio_filter = []

    if bg_video is not None:
        # Gameplay-b-roll pattern: loop the backdrop video under translucent
        # bubble frames via overlay.
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(bg_video.resolve()),
               "-f", "concat", "-safe", "0", "-i", concat.name,
               *(audio_input or []),
               "-filter_complex",
               f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
               f"crop={WIDTH}:{HEIGHT},setsar=1[bg];[1:v]format=rgba[fg];"
               f"[bg][fg]overlay=format=auto[v]",
               "-map", "[v]", "-map", "0:a" if audio_input is None else "2:a"]
    else:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
               *(audio_input or []),
               "-map", "0:v", "-map", "1:a",
               "-vf", f"scale={WIDTH}:{HEIGHT},setsar=1"]
    cmd += [*audio_filter, "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}",
            str(out_path.resolve())]
    proc = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
    shutil.rmtree(work, ignore_errors=True)
    return out_path


def render_chat_slides(app: App, script: str, out_dir: Path, stem: str,
                       title: str = "the group chat", slides: int = 5) -> list[Path]:
    """Render the conversation at N sequential cut points as chat-screenshot
    PNGs — the carousel form of the strategy (the swipe IS the next beat).
    The final slide always shows the full conversation, payoff included."""
    msgs = parse_script(script)
    if not msgs:
        raise ValueError("chat drama script has no messages")
    n = max(min(slides, len(msgs)), 1)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in range(n):
        cut = round((k + 1) * len(msgs) / n)
        p = out_dir / f"{stem}_slide{k + 1}.png"
        _render_frame(title, msgs[:cut]).save(p)
        paths.append(p)
    return paths


# --------------------------------------------------------------------------- #
# Backing audio
# --------------------------------------------------------------------------- #
def _find_bg_asset(app: App) -> Path | None:
    """Optional user-supplied backing asset. An .mp4 doubles as the visual
    backdrop behind the bubbles (gameplay-b-roll pattern)."""
    for ext in ("mp4", "mp3", "wav"):
        p = app.paths.data_dir / "assets" / f"chatdrama_bg.{ext}"
        if p.exists():
            return p
    return None


def _has_audio(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return "audio" in out.stdout
    except Exception:
        return False


def _ambient_pad(path: Path, seconds: float, rate: int = 44100) -> None:
    """Quiet synthetic backing pad: two detuned low sines under gentle noise
    with a slow tremolo so it breathes. Fully offline — no asset, no API."""
    t = np.arange(int(max(seconds, 1.0) * rate)) / rate
    tone = 0.6 * np.sin(2 * np.pi * 110.0 * t) + 0.4 * np.sin(2 * np.pi * 164.8 * t)
    tremolo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.25 * t)
    noise = np.random.default_rng(7).standard_normal(t.size) * 0.03
    signal = (tone * tremolo + noise) * 0.05  # well under the read-along zone
    pcm = (np.clip(signal, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
