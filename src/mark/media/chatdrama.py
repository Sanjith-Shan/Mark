"""Chat-drama video renderer (fake-text-drama strategy).

Renders a scripted message-thread conversation as a vertical video: messages
appear one by one in a chat UI, paced by length so each beat is readable
(cliffhanger pacing is the strategy's engine). Fully deterministic — Pillow
frames + ffmpeg concat, no generative models, no AI-labeling risk.

Script format (what the writer produces for this strategy): one message per
line as ``Sender: message``. Senders named me/you/us render as the blue
right-side bubbles; everyone else renders left with a name label. Bare lines
become narrator cards.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from ..app import App
from .images import _load_font

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


def _render_frame(title: str, visible: list[dict]) -> Image.Image:
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

    durations, total = [], 0.0
    for i in range(len(msgs)):
        d = _beat_seconds(msgs[i]["text"])
        if total + d > max_duration:
            msgs = msgs[: i]
            break
        durations.append(d)
        total += d
    frames = []
    for i in range(len(msgs)):
        frame = work / f"frame_{i:03d}.png"
        _render_frame(title, msgs[: i + 1]).save(frame)
        frames.append((frame, durations[i]))

    # ffmpeg concat demuxer with per-frame durations; silent AAC track so every
    # platform accepts the file.
    concat = work / "list.txt"
    lines = []
    for frame, d in frames:
        lines.append(f"file '{frame.name}'")
        lines.append(f"duration {d:.2f}")
    lines.append(f"file '{frames[-1][0].name}'")  # concat quirk: repeat last
    concat.write_text("\n".join(lines))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat.name,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-map", "0:v", "-map", "1:a",
        "-vf", f"scale={WIDTH}:{HEIGHT},setsar=1", "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(out_path.resolve()),
    ]
    proc = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
    shutil.rmtree(work, ignore_errors=True)
    return out_path
