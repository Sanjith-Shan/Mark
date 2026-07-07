"""yt-dlp subprocess wrapper — permissioned video acquisition.

yt-dlp is the de-facto downloader for Twitch clips (it handles the GQL signed
playback-token dance; do NOT reimplement that) and also takes direct file URLs
and archive.org pages. We shell out to the installed binary rather than import
the library so version bumps are a `pip install -U yt-dlp` away and breakage is
an expected, isolated maintenance event.

POLICY — what this module may be pointed at (not negotiable):
  * Twitch clips ONLY under an active campaign permission (official clipping
    program / written OK from the broadcaster) — clips are the streamer's
    copyright, plus game-publisher and music layers.
  * Otherwise: Creative-Commons-licensed material, public-domain material
    (e.g. archive.org), or our own uploads. yt-dlp on ordinary YouTube content
    violates YouTube ToS and infringes the underlying copyright — never do it.
  * Never download segments containing licensed music / TV / sports footage;
    Content ID hits regardless of the streamer's consent.

MOCK MODE: any URL starting with ``mock:`` skips the network entirely and
generates a real playable lavfi clip in ``out_dir`` (named from the URL slug),
so tests and offline pipeline runs exercise the same code path shape.

INTEGRATION
-----------
* No API keys. Requires the ``yt-dlp`` binary on PATH (present here at
  ``/opt/anaconda3/bin/yt-dlp``) and ffmpeg for merges.
* Callers should pin/refresh yt-dlp promptly when downloads start failing —
  the error message from :func:`download` says so explicitly.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

log = logging.getLogger("mark.sourcing.ytdlp")

_KNOWN_LOCATIONS = ("/opt/anaconda3/bin/yt-dlp", "/opt/homebrew/bin/yt-dlp")
_RETRIES = 2  # additional attempts after the first, with backoff
_TIMEOUT_S = 600


def _binary() -> str:
    found = shutil.which("yt-dlp")
    if found:
        return found
    for candidate in _KNOWN_LOCATIONS:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "yt-dlp binary not found on PATH — install it (pip install yt-dlp) "
        "to enable clip downloads")


def _mock_clip(url: str, out_dir: Path) -> Path:
    from . import placeholder_clip

    slug = re.sub(r"[^a-z0-9]+", "-", url.split(":", 1)[1].lower()).strip("-") or "clip"
    dest = Path(out_dir) / f"{slug}.mp4"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    return placeholder_clip(dest, seed=sum(ord(c) for c in slug))


def download(url: str, out_dir: Path, *, fmt: str = "mp4",
             max_height: int = 1080) -> Path:
    """Download ``url`` into ``out_dir``; return the path of the finished file.

    Prefers the best streams up to ``max_height``, merged/remuxed to ``fmt``.
    Retries twice with backoff; the final error carries yt-dlp's stderr tail
    and an update hint (extractor breakage is usually fixed upstream fast).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if url.startswith("mock:"):
        return _mock_clip(url, out_dir)

    cmd = [
        _binary(),
        "--no-playlist",
        "--no-progress",
        "-f", f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "--merge-output-format", fmt,
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        "--no-simulate",
        "--print", "after_move:filepath",
        url,
    ]
    last_err = ""
    for attempt in range(_RETRIES + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            last_err = f"timed out after {_TIMEOUT_S}s"
            proc = None
        if proc is not None and proc.returncode == 0:
            # --print emits the final filepath (one line per video; we pass
            # --no-playlist so there is exactly one).
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            path = Path(lines[-1]) if lines else None
            if path and path.exists():
                log.info("yt-dlp downloaded %s → %s", url, path.name)
                return path
            last_err = "yt-dlp exited 0 but produced no file"
        elif proc is not None:
            last_err = proc.stderr.strip()[-500:]
        if attempt < _RETRIES:
            delay = 2.0 * (2 ** attempt)
            log.warning("yt-dlp attempt %d failed for %s: %s — retrying in %.0fs",
                        attempt + 1, url, last_err.splitlines()[-1] if last_err else "?",
                        delay)
            time.sleep(delay)
    raise RuntimeError(
        f"yt-dlp failed to download {url} after {_RETRIES + 1} attempts: "
        f"{last_err or 'unknown error'} — if this is an extractor error, "
        f"try updating yt-dlp (pip install -U yt-dlp)")


def probe(url: str) -> dict:
    """Fetch metadata (``yt-dlp -j``) without downloading. Returns the raw
    info dict — useful keys: id, title, duration, width, height, uploader,
    license, webpage_url. Mock URLs return a deterministic stub."""
    if url.startswith("mock:"):
        slug = re.sub(r"[^a-z0-9]+", "-", url.split(":", 1)[1].lower()).strip("-") or "clip"
        return {"id": slug, "title": f"mock clip {slug}", "duration": 8.0,
                "width": 1080, "height": 1920, "uploader": "mock",
                "license": "mock", "webpage_url": url, "mock": True}
    proc = subprocess.run(
        [_binary(), "--no-playlist", "--no-download", "-j", url],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"yt-dlp probe failed for {url}: {proc.stderr.strip()[-300:]} — "
            f"try updating yt-dlp (pip install -U yt-dlp)")
    # -j prints one JSON object per line; --no-playlist keeps it to one.
    line = next((ln for ln in proc.stdout.splitlines() if ln.strip()), "{}")
    return json.loads(line)
