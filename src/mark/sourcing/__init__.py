"""Mark sourcing package — where raw video clips come from.

Three acquisition lanes, all offline-capable:
  * ``stock``  — Pexels / Pixabay licensed b-roll (free, commercial, no attribution)
  * ``ytdlp``  — subprocess wrapper around the yt-dlp binary (permissioned
                 downloads only — see the policy note in that module)
  * ``twitch`` — Helix discovery client (streams / clips / users)

Shared here: :func:`placeholder_clip`, the deterministic ffmpeg-lavfi clip
generator every mock path uses so downstream pipelines (EDL render, captions,
posting) run fully offline against REAL playable MP4 files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def placeholder_clip(out_path: Path, *, seconds: float = 8.0,
                     width: int = 1080, height: int = 1920, seed: int = 0) -> Path:
    """Generate a real, playable H.264 MP4 via ffmpeg lavfi (testsrc2 video +
    sine audio). Deterministic per ``seed`` so mock sourcing is repeatable.
    Portrait 1080x1920 by default to match the platform target spec."""
    import shutil

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required to generate placeholder clips")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    freq = 220 + (seed % 8) * 110  # audibly distinct per seed
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"testsrc2=size={width}x{height}:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"ffmpeg placeholder clip failed: {proc.stderr[-500:]}")
    return out_path
