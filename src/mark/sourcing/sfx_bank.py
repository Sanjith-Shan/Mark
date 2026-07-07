"""SFX bank — curate-once sourcing + transient analysis for the placement engine.

Fills every slug in ``config/sfx_library.yaml`` from a *monetization-safe* source
and records the result in ``data/sfx/manifest.json`` (slug -> file, provenance,
loudness-normalized duration, and the precomputed ``onset_ms``/``peak_ms`` the
placement engine aligns to). Curated ONCE via ``mark sfx sync``; at render time
the engine only reads the manifest — zero network.

Sourcing priority (Contract 7 / research spec), each license-gated:
  1. Kenney CC0 packs vendored at ``data/sfx/kenney/{slug}.*`` (offline, no API) —
     the reliable path for the whole UI/pop/ding/impact family.
  2. Freesound APIv2 with a hard ``license:"Creative Commons 0"`` filter
     (``Authorization: Token FREESOUND_API_KEY``; HQ preview transcode carries
     the source's CC0 rights, so no OAuth needed for a bot).
  3. Mixkit Free-License static scrape (commercial + monetized use OK, no
     attribution) for named effects missing from CC0 sources.
  4. OFFLINE/MOCK synthesis: a distinct ffmpeg-lavfi placeholder per family
     (whoosh=filtered noise sweep, boom=low sine burst, pop=short click,
     ding=sine, riser=rising sweep, …) so the whole engine + tests run with zero
     network and zero keys.

LICENSE GATE (enforced, not advisory): only ``{CC0, Mixkit-Free,
Pixabay-Content}`` may back a slug. Zapsplat / Uppbeat / BBC-RemArc are rejected;
the meme originals (real Vine Boom, branded MLG airhorn) are never fetched — the
library's ``query`` keywords deliberately pull generic equivalents.

Pixabay note (load-bearing correction): Pixabay's key-based API serves images and
video ONLY — there is no audio endpoint. We do NOT build a Pixabay audio client;
its SFX are reachable by static scrape only and are not wired here.

Every ingested clip is loudness-normalized with
``ffmpeg loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000`` before analysis, so mix gains
in ``sfx.py`` are meaningful across sources.

The integration/wiring notes live in ``src/mark/media/sfx.py``'s module docstring.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Iterable, Optional

import yaml

from .. import db as db_module
from ..app import App

log = logging.getLogger("mark.sourcing.sfx_bank")

# Monetization-safe licenses only. Everything else is rejected at ingest.
_LICENSE_OK = {"CC0", "Mixkit-Free", "Pixabay-Content"}

_FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"
_FREESOUND_PACE_S = 1.0  # respect the 60/min throttle

# Per-family offline placeholder generators: (lavfi source, post filter). The
# transient is placed so onset/peak analysis is meaningful — attack near start
# for ``onset`` families, a mid/end swell for the ``peak`` (transition/riser)
# families. Each is distinct enough to tell families apart by ear.
_FAMILY_GEN: dict[str, tuple[str, Optional[str]]] = {
    # peak ~mid: noise sweep that fades up then down (masks a cut)
    "transition": ("anoisesrc=r=48000:a=0.7:d=0.7:c=white:seed={seed}",
                   "highpass=f=280,afade=t=in:st=0:d=0.30:curve=exp,"
                   "afade=t=out:st=0.36:d=0.34"),
    # peak at end: rising frequency + rising amplitude (build into the reveal)
    "riser": ("aevalsrc=exprs='sin(2*PI*(180+760*t)*t)':d=1.5:s=48000",
              "volume=volume='min(1\\,pow(t/1.5\\,1.5))':eval=frame"),
    # onset at start: low sine burst with fast exp decay (a boom/braam)
    "impact": ("aevalsrc=exprs='sin(2*PI*68*t)*exp(-7*t)':d=0.6:s=48000", None),
    # onset at start: wobbly bass stamp (comedic boom / stinger)
    "comedy_meme": ("aevalsrc=exprs='sin(2*PI*(320+120*sin(2*PI*4*t))*t)*exp(-3*t)'"
                    ":d=0.8:s=48000", None),
    # onset at start: short bright click (caption pop / ui)
    "ui": ("aevalsrc=exprs='sin(2*PI*1400*t)*exp(-45*t)':d=0.16:s=48000", None),
    # onset at start: low sustained pulse (tension bed / stinger)
    "suspense": ("aevalsrc=exprs='sin(2*PI*92*t)*0.6':d=1.0:s=48000",
                 "afade=t=in:d=0.04,afade=t=out:st=0.9:d=0.1"),
    # onset at start: high shimmer chime
    "aesthetic": ("aevalsrc=exprs='sin(2*PI*2100*t)*exp(-6*t)':d=0.4:s=48000", None),
    # onset at start: bright coin/register blip
    "money": ("aevalsrc=exprs='sin(2*PI*1600*t)*exp(-9*t)':d=0.3:s=48000", None),
    # onset at start: two-tone success chime
    "reward": ("aevalsrc=exprs='(sin(2*PI*880*t)+0.5*sin(2*PI*1320*t))*exp(-4*t)'"
               ":d=0.5:s=48000", None),
    # onset at start: brand sting (two-tone with decay)
    "hook": ("aevalsrc=exprs='(sin(2*PI*440*t)+0.4*sin(2*PI*660*t))*exp(-3*t)'"
             ":d=0.6:s=48000", None),
    # onset near start: broadband crowd swell
    "social": ("anoisesrc=r=48000:a=0.4:d=0.9:c=brown:seed={seed}",
               "afade=t=in:d=0.15,afade=t=out:st=0.7:d=0.2"),
    # no transient: low steady room-tone bed
    "atmosphere": ("anoisesrc=r=48000:a=0.15:d=1.5:c=brown:seed={seed}",
                   "lowpass=f=800"),
}
_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
_AFORMAT = "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono"


# --------------------------------------------------------------------------- #
# Paths + library / manifest IO
# --------------------------------------------------------------------------- #
def _sfx_dir(app: App) -> Path:
    return Path(app.paths.data_dir) / "sfx"


def _library_path(app: App) -> Path:
    return Path(app.paths.config_dir) / "sfx_library.yaml"


def _manifest_path(app: App) -> Path:
    return _sfx_dir(app) / "manifest.json"


def load_library(app: App) -> dict:
    """Parse ``config/sfx_library.yaml`` (families + effects)."""
    path = _library_path(app)
    if not path.exists():
        raise FileNotFoundError(f"SFX library not found: {path}")
    return yaml.safe_load(path.read_text()) or {}


def load_manifest(app: App) -> dict:
    """Return the slug->entry manifest (empty dict if never synced)."""
    path = _manifest_path(app)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001 — a corrupt manifest must not crash render
        log.warning("sfx manifest unreadable (%s) — treating as empty", exc)
        return {}


def _effect_meta(library: dict, effect: dict) -> dict:
    """Merge family policy + per-effect overrides into the flat placement fields
    the engine consumes straight from the manifest (so ``place_sfx`` needs only
    the manifest, never the library)."""
    fam_name = effect["family"]
    fam = (library.get("families") or {}).get(fam_name, {})
    return {
        "family": fam_name,
        "align": effect.get("align") or fam.get("align") or "onset",
        "base_gain_db": float(fam.get("base_gain_db", -12)),
        "duck_music_db": float(fam.get("duck_music_db", 0)),
        "cap": effect.get("cap"),                 # per-clip cap or None
        "min_gap_s": effect.get("min_gap_s"),     # override or None (-> global 0.6)
        "purpose": effect.get("purpose", ""),
    }


# --------------------------------------------------------------------------- #
# Public sync API
# --------------------------------------------------------------------------- #
def ensure_library(app: App) -> dict:
    """Return a complete manifest, syncing only if it's missing/incomplete."""
    manifest = load_manifest(app)
    try:
        slugs = {e["slug"] for e in load_library(app).get("effects", [])}
    except FileNotFoundError:
        return manifest
    if manifest and slugs.issubset(manifest.keys()):
        return manifest
    return sync_library(app)


def sync_library(app: App, *, only: Optional[Iterable[str]] = None) -> dict:
    """Curate the library: fetch/synthesize every slug (or just ``only``),
    loudness-normalize, analyze transients, and (re)write the manifest.

    Wired to ``mark sfx sync`` (the CLI calls this — see INTEGRATION in sfx.py).
    Always completes: any live-source failure degrades to offline synthesis, so
    the render path is never left without a usable asset.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required to build the SFX bank")
    library = load_library(app)
    effects = library.get("effects", [])
    want = set(only) if only else None

    manifest = load_manifest(app)  # merge: only rebuild the requested slugs
    built, mocked = 0, 0
    for effect in effects:
        slug = effect["slug"]
        if want is not None and slug not in want:
            continue
        meta = _effect_meta(library, effect)
        try:
            path, source, license_, url = _acquire(app, slug, effect, meta["family"])
        except Exception as exc:  # noqa: BLE001 — never let one slug abort the sync
            log.warning("sfx acquire failed for %s (%s) — synthesizing", slug, exc)
            path, source, license_, url = _synth_mock(app, slug, meta["family"]), "synth", "CC0", None

        # License gate — refuse to ship anything outside the safe set.
        if license_ not in _LICENSE_OK:
            log.warning("license %r for %s not in %s — dropping to synth",
                        license_, slug, _LICENSE_OK)
            path, source, license_, url = _synth_mock(app, slug, meta["family"]), "synth", "CC0", None

        onset_ms, peak_ms, duration = _analyze_transients(path)
        manifest[slug] = {
            "file": str(Path(path).resolve()),
            "source": source,
            "license": license_,
            "url": url,
            "duration": round(duration, 3),
            "onset_ms": int(onset_ms),
            "peak_ms": int(peak_ms),
            **meta,
        }
        built += 1
        if source == "synth":
            mocked += 1

    _manifest_path(app).parent.mkdir(parents=True, exist_ok=True)
    _manifest_path(app).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    db_module.log_activity(
        app.conn, "sfx_sync",
        f"SFX bank synced: {built} effects ({mocked} synthesized, "
        f"{built - mocked} sourced) -> {len(manifest)} in manifest",
        level="success")
    return manifest


# --------------------------------------------------------------------------- #
# Acquisition (license-gated), with offline synthesis as the guaranteed floor
# --------------------------------------------------------------------------- #
def _acquire(app: App, slug: str, effect: dict, family: str) -> tuple[Path, str, str, Optional[str]]:
    """Return (normalized_wav_path, source, license, url) for one slug."""
    key = os.environ.get("FREESOUND_API_KEY") or None

    # 1) Vendored Kenney CC0 pack (offline, most reliable for ui/impact/whoosh).
    kenney = _find_vendored(app, slug)
    if kenney is not None:
        return _normalize(app, kenney, slug), "kenney", "CC0", None

    # Offline / no key -> synthesize (the default path in mock and in tests).
    if app.force_mock or not key:
        return _synth_mock(app, slug, family), "synth", "CC0", None

    # 2) Freesound APIv2, CC0-filtered (best-effort; falls through on any failure).
    fs = _fetch_freesound(app, slug, effect.get("query") or [slug], key)
    if fs is not None:
        raw, url = fs
        return _normalize(app, raw, slug), "freesound", "CC0", url

    # 3) Mixkit Free-License scrape (best-effort).
    mk = _fetch_mixkit(app, slug, effect.get("query") or [slug])
    if mk is not None:
        raw, url = mk
        return _normalize(app, raw, slug), "mixkit", "Mixkit-Free", url

    # 4) Guaranteed floor.
    return _synth_mock(app, slug, family), "synth", "CC0", None


def _find_vendored(app: App, slug: str) -> Optional[Path]:
    base = _sfx_dir(app) / "kenney"
    for ext in (".wav", ".ogg", ".mp3", ".flac"):
        p = base / f"{slug}{ext}"
        if p.is_file():
            return p
    return None


def _fetch_freesound(app: App, slug: str, queries: list[str], key: str
                     ) -> Optional[tuple[Path, str]]:
    """Search Freesound (CC0 only), download the best HQ preview. Best-effort:
    returns None on any network/parse failure so the caller degrades."""
    try:
        import httpx
    except Exception:
        return None
    raw_dir = _sfx_dir(app) / "freesound"
    raw_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Token {key}"}
    for qi, query in enumerate(queries):
        if qi:
            time.sleep(_FREESOUND_PACE_S)
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    _FREESOUND_SEARCH, headers=headers,
                    params={
                        "query": query,
                        "filter": 'license:"Creative Commons 0"',
                        "fields": "id,name,previews,license,duration,avg_rating",
                        "sort": "rating_desc", "page_size": "15",
                    })
                if resp.status_code == 429:  # throttled — back off and retry once
                    time.sleep(_FREESOUND_PACE_S * 4)
                    resp = client.get(_FREESOUND_SEARCH, headers=headers,
                                      params={"query": query,
                                              "filter": 'license:"Creative Commons 0"',
                                              "fields": "id,name,previews,license,duration",
                                              "sort": "rating_desc", "page_size": "15"})
                resp.raise_for_status()
                results = (resp.json() or {}).get("results") or []
                # Prefer short one-shots; risers/beds allowed longer.
                long_ok = query.split()[0] in {"riser", "long", "drumroll", "drone",
                                               "heartbeat", "tension", "epic", "build"}
                limit = 8.0 if long_ok else 3.0
                pick = next((r for r in results
                             if 0.05 < float(r.get("duration") or 0) <= limit), None)
                pick = pick or (results[0] if results else None)
                if not pick:
                    continue
                # License gate again on the actual item (defense in depth).
                if "Creative Commons 0" not in (pick.get("license") or "") \
                        and "creativecommons.org/publicdomain/zero" not in (pick.get("license") or ""):
                    continue
                previews = pick.get("previews") or {}
                purl = previews.get("preview-hq-ogg") or previews.get("preview-hq-mp3")
                if not purl:
                    continue
                media = client.get(purl, headers=headers, timeout=30)
                media.raise_for_status()
                ext = ".ogg" if purl.endswith("ogg") else ".mp3"
                raw = raw_dir / f"{pick['id']}_{slug}{ext}"
                raw.write_bytes(media.content)
                return raw, f"https://freesound.org/s/{pick['id']}/"
        except Exception as exc:  # noqa: BLE001
            log.info("freesound '%s' for %s failed: %s", query, slug, exc)
            continue
    return None


def _fetch_mixkit(app: App, slug: str, queries: list[str]) -> Optional[tuple[Path, str]]:
    """Best-effort Mixkit Free-License scrape. Kept intentionally conservative:
    returns None unless it finds a direct downloadable .wav/.mp3 for the first
    query term. (No key, no sign-up; commercial + monetized use permitted.)"""
    try:
        import re

        import httpx
    except Exception:
        return None
    raw_dir = _sfx_dir(app) / "mixkit"
    raw_dir.mkdir(parents=True, exist_ok=True)
    term = (queries[0] if queries else slug).replace(" ", "-")
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as client:
            page = client.get(f"https://mixkit.co/free-sound-effects/{term}/")
            if page.status_code != 200:
                return None
            m = re.search(r'https://assets\.mixkit\.co/[^"\']+\.(?:wav|mp3)', page.text)
            if not m:
                return None
            url = m.group(0)
            media = client.get(url)
            media.raise_for_status()
            ext = ".wav" if url.endswith("wav") else ".mp3"
            raw = raw_dir / f"{slug}{ext}"
            raw.write_bytes(media.content)
            return raw, url
    except Exception as exc:  # noqa: BLE001
        log.info("mixkit scrape for %s failed: %s", slug, exc)
        return None


# --------------------------------------------------------------------------- #
# Normalization + offline synthesis
# --------------------------------------------------------------------------- #
def _normalize(app: App, raw: Path, slug: str) -> Path:
    """Loudness-normalize a fetched clip to the mix reference and 48kHz mono
    WAV. On any ffmpeg failure, falls back to synthesizing the slug (never
    leaves a slug without a playable, analyzable file)."""
    out_dir = _sfx_dir(app) / "norm"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.wav"
    cmd = ["ffmpeg", "-y", "-i", str(raw), "-af", f"{_LOUDNORM},{_AFORMAT}",
           "-ar", "48000", "-ac", "1", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        log.warning("loudnorm failed for %s (%s) — synthesizing", slug, proc.stderr[-200:])
        # family unknown here; caller passes normalized path only for real sources,
        # so re-derive a neutral synth. Use the impact generator as a safe default.
        return _synth_mock(app, slug, "impact")
    return out


def _synth_mock(app: App, slug: str, family: str) -> Path:
    """Synthesize a distinct, loudness-normalized placeholder for ``slug`` from
    its family's lavfi generator. REAL playable 48kHz WAV — the offline default
    that makes the whole engine (and its tests) run with no network and no key."""
    out_dir = _sfx_dir(app) / "mock"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.wav"
    src, post = _FAMILY_GEN.get(family, _FAMILY_GEN["impact"])
    seed = (abs(hash(slug)) % 100000)
    src = src.format(seed=seed)
    afilter = f"{post + ',' if post else ''}{_LOUDNORM},{_AFORMAT}"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", src,
           "-af", afilter, "-ar", "48000", "-ac", "1", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        # Last resort: a bare tone so the slug still has a valid file.
        fallback = ["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.4:sample_rate=48000",
                    "-ac", "1", str(out)]
        fb = subprocess.run(fallback, capture_output=True, text=True)
        if fb.returncode != 0 or not out.exists():
            raise RuntimeError(f"synth failed for {slug}: {proc.stderr[-300:]}")
    return out


# --------------------------------------------------------------------------- #
# Transient analysis — numpy RMS-onset fallback (default; librosa if available)
# --------------------------------------------------------------------------- #
def _analyze_transients(path: Path) -> tuple[int, int, float]:
    """Return (onset_ms, peak_ms, duration_s) for an audio file.

    Decodes to 8kHz mono f32 via ffmpeg, builds a 10ms-hop RMS envelope, and
    picks the peak frame plus the first frame crossing 20% of the peak. librosa
    is NOT installed in this environment, so the numpy path is the default and
    must stand on its own; a librosa refinement is attempted opportunistically.
    """
    import numpy as np

    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000",
         "-f", "f32le", "-"], capture_output=True)
    data = np.frombuffer(proc.stdout, dtype="<f4")
    if data.size == 0:
        return 0, 0, 0.0
    sr = 8000
    duration = data.size / sr

    hop = 80  # 10 ms
    n_frames = max(1, data.size // hop)
    trimmed = data[: n_frames * hop].reshape(n_frames, hop)
    env = np.sqrt(np.mean(trimmed.astype(np.float64) ** 2, axis=1))
    peak_idx = int(np.argmax(env))
    peak = float(env[peak_idx])
    if peak <= 0:
        return 0, peak_idx * 10, round(duration, 3)
    thresh = 0.2 * peak
    above = np.where(env >= thresh)[0]
    onset_idx = int(above[0]) if above.size else peak_idx

    onset_ms, peak_ms = onset_idx * 10, peak_idx * 10

    # Opportunistic librosa refinement (absent here -> silently keep numpy).
    try:
        import librosa  # type: ignore

        y, lsr = librosa.load(str(path), sr=None, mono=True)
        env_l = librosa.onset.onset_strength(y=y, sr=lsr)
        if env_l.size:
            frames = librosa.onset.onset_detect(onset_envelope=env_l, sr=lsr, units="time")
            if len(frames):
                onset_ms = int(frames[0] * 1000)
    except Exception:
        pass

    return onset_ms, peak_ms, round(duration, 3)
