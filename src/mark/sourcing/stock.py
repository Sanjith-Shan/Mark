"""Stock video sourcing — Pexels + Pixabay search and cached download.

Both licenses are free for commercial use with no attribution and allow
modification, which makes stock b-roll the one fully rights-clean clip source
(vs reposted speech/movie/stream footage). Pexels supports a native
``orientation=portrait`` filter; Pixabay's video API has no orientation param,
so we filter portrait client-side by the largest variant's aspect ratio.

Normalized item shape (both providers):
    {id, provider, url, width, height, duration, preview_image, download_url}

Downloads are cached at ``data/assets/stock/{provider}/{id}.mp4`` keyed by the
provider video id, so repeated template runs never re-fetch the same clip.

MOCK MODE (no key for the chosen provider, or ``app.force_mock``): search
returns deterministic fake items and ``download_video`` generates a REAL
playable portrait clip via ffmpeg lavfi (also cached) so downstream pipelines
run fully offline.

INTEGRATION
-----------
* Env keys (read from ``os.environ``, populated by ``.env`` via
  ``config.load_dotenv``): ``PEXELS_API_KEY`` (free — pexels.com/api, 200
  req/hr / 20k req/mo) and ``PIXABAY_API_KEY`` (free — pixabay.com/api/docs).
  Neither is in ``config.Keys`` — this module checks the env directly, same as
  humor_radar's ``TENOR_API_KEY``. If ``Keys`` ever grows stock fields,
  ``_provider_key`` is the single place to switch.
* Suggested config (not required — sane defaults in code): a
  ``sourcing.stock`` block with a curated query vocabulary per register
  (boxing, running-in-rain, lions, mountains, city-at-night, rowing).
* Rate limits: Pexels 200 req/hr — templates should search once per produce
  call, not per candidate.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .. import db as db_module
from ..app import App

log = logging.getLogger("mark.sourcing.stock")

PROVIDERS = ("pexels", "pixabay")

_PEXELS_SEARCH = "https://api.pexels.com/videos/search"
_PIXABAY_SEARCH = "https://pixabay.com/api/videos/"

_ENV_KEYS = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}


def _provider_key(provider: str) -> str | None:
    return os.environ.get(_ENV_KEYS.get(provider, "")) or None


def _is_mock(app: App, provider: str) -> bool:
    return app.force_mock or _provider_key(provider) is None


def _cache_dir(app: App, provider: str) -> Path:
    return app.paths.data_dir / "assets" / "stock" / provider


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def search_videos(app: App, query: str, *, orientation: str = "portrait",
                  per_page: int = 15, provider: str = "pexels") -> list[dict]:
    """Search stock videos. Returns normalized dicts (see module docstring);
    empty list on any provider failure (graceful degradation, like the trend
    fetchers) — callers must handle 'no stock found'."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown stock provider {provider!r} (want one of {PROVIDERS})")
    if _is_mock(app, provider):
        return _mock_items(query, provider, orientation)
    try:
        items = (_search_pexels if provider == "pexels" else _search_pixabay)(
            query, orientation, per_page)
        db_module.log_activity(
            app.conn, "sourcing",
            f"Stock search [{provider}] {query!r} → {len(items)} videos")
        return items
    except Exception as exc:
        log.warning("%s search failed for %r: %s", provider, query, exc)
        return []


def _search_pexels(query: str, orientation: str, per_page: int) -> list[dict]:
    import httpx

    with httpx.Client(timeout=20) as client:
        resp = client.get(
            _PEXELS_SEARCH,
            headers={"Authorization": _provider_key("pexels")},
            params={"query": query, "orientation": orientation,
                    "per_page": str(min(per_page, 80)), "size": "medium"})
        resp.raise_for_status()
        data = resp.json()
    out = []
    for v in data.get("videos") or []:
        best = _best_pexels_file(v.get("video_files") or [])
        if not best:
            continue
        out.append({
            "id": str(v["id"]),
            "provider": "pexels",
            "url": v.get("url"),
            "width": best.get("width") or v.get("width") or 0,
            "height": best.get("height") or v.get("height") or 0,
            "duration": float(v.get("duration") or 0),
            "preview_image": v.get("image"),
            "download_url": best["link"],
        })
    return out


def _best_pexels_file(files: list[dict]) -> dict | None:
    """Highest-resolution mp4 that still fits our 1080x1920 target (avoids
    pulling 4K originals we'd downscale anyway)."""
    mp4s = [f for f in files if (f.get("file_type") or "").endswith("mp4")
            and f.get("link")]
    if not mp4s:
        return None
    fitting = [f for f in mp4s if max(f.get("width") or 0, f.get("height") or 0) <= 1920]
    pool = fitting or mp4s
    return max(pool, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))


def _search_pixabay(query: str, orientation: str, per_page: int) -> list[dict]:
    import httpx

    with httpx.Client(timeout=20) as client:
        resp = client.get(
            _PIXABAY_SEARCH,
            params={"key": _provider_key("pixabay"), "q": query,
                    "per_page": str(min(max(per_page, 3), 200)),
                    "safesearch": "true", "video_type": "film"})
        resp.raise_for_status()
        data = resp.json()
    out = []
    for h in data.get("hits") or []:
        variants = h.get("videos") or {}
        best = (variants.get("large") or variants.get("medium")
                or variants.get("small") or {})
        if not best.get("url"):
            continue
        w, ht = best.get("width") or 0, best.get("height") or 0
        # Pixabay's video API has no orientation param — filter client-side.
        if orientation == "portrait" and not ht > w:
            continue
        if orientation == "landscape" and not w > ht:
            continue
        out.append({
            "id": str(h["id"]),
            "provider": "pixabay",
            "url": h.get("pageURL"),
            "width": w,
            "height": ht,
            "duration": float(h.get("duration") or 0),
            "preview_image": best.get("thumbnail"),
            "download_url": best["url"],
        })
    return out


# --------------------------------------------------------------------------- #
# Mock search — deterministic, and downloadable offline
# --------------------------------------------------------------------------- #
def _mock_items(query: str, provider: str, orientation: str) -> list[dict]:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "clip"
    w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)
    return [{
        "id": f"mock-{slug}-{i}",
        "provider": provider,
        "url": f"https://example.com/{provider}/{slug}/{i}",
        "width": w,
        "height": h,
        "duration": 8.0,
        "preview_image": None,
        "download_url": f"mock://{provider}/{slug}-{i}.mp4",
        "mock": True,
    } for i in range(1, 4)]


# --------------------------------------------------------------------------- #
# Download (cached)
# --------------------------------------------------------------------------- #
def download_video(app: App, item: dict) -> Path:
    """Download a search-result item to the stock cache; return the cached path
    immediately when it already exists. Mock items generate a real lavfi clip."""
    provider = item.get("provider") or "pexels"
    dest = _cache_dir(app, provider) / f"{item['id']}.mp4"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    url = item.get("download_url") or ""
    if item.get("mock") or url.startswith("mock://") or _is_mock(app, provider):
        from . import placeholder_clip

        seed = sum(ord(c) for c in str(item["id"]))
        portrait = (item.get("height") or 1920) >= (item.get("width") or 1080)
        w, h = (1080, 1920) if portrait else (1920, 1080)
        return placeholder_clip(dest, seconds=float(item.get("duration") or 8.0),
                                width=w, height=h, seed=seed)

    import httpx

    tmp = dest.with_suffix(".part")
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in resp.iter_bytes(1024 * 256):
                        f.write(chunk)
        tmp.rename(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    db_module.log_activity(
        app.conn, "sourcing",
        f"Stock download [{provider}] {item['id']} → {dest.name}")
    return dest
