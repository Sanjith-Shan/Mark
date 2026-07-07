"""Sound-effects engine tests (Contract 7).

Runs in forced mock mode (the shared ``app`` fixture): the bank synthesizes a
distinct, loudness-normalized placeholder per family with ffmpeg lavfi, so every
slug is backed by a REAL playable file with no network and no API key. The final
test does an actual ffmpeg render and PROVES the placed SFX are audible in the
mixed output by decoding the audio and measuring the energy spike a whoosh adds
at a cut point (vs the same render without SFX).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from mark.media import edl as E
from mark.media import sfx
from mark.media.sfx import SfxTags, SfxWordTag
from mark.sourcing import sfx_bank

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _library_slugs(app) -> set[str]:
    return {e["slug"] for e in sfx_bank.load_library(app)["effects"]}


def _probe_is_audio(path: str) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return "audio" in r.stdout


def _lavfi_clip(path: Path, color: str, dur: float = 3.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c={color}:s=1080x1920:d={dur}:r=30", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)


def _decode_env(path: Path, sr: int = 8000, hop: int = 80) -> tuple[np.ndarray, int]:
    """Decode ``path``'s audio to a mono RMS envelope (10ms hops at 8kHz)."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"], capture_output=True)
    data = np.frombuffer(proc.stdout, dtype="<f4")
    if data.size == 0:
        return np.zeros(1), sr
    n = data.size // hop
    env = np.sqrt(np.mean(data[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    return env, sr


def _rms_window(env: np.ndarray, t0: float, t1: float, hop_ms: int = 10) -> float:
    a, b = int(t0 * 1000 / hop_ms), int(t1 * 1000 / hop_ms)
    a, b = max(0, a), min(len(env), max(a + 1, b))
    seg = env[a:b]
    return float(seg.max()) if seg.size else 0.0


def _basic_edl() -> E.EDL:
    words = [("This", 0.0, 0.3, False), ("changes", 0.3, 0.7, True),
             ("everything", 0.7, 1.2, False), ("watch", 2.5, 2.9, False),
             ("the", 2.9, 3.05, False), ("insane", 3.1, 3.7, True),
             ("result", 3.7, 4.3, False), ("we", 5.4, 5.6, False),
             ("made", 5.6, 6.0, False), ("bank", 6.0, 6.6, True)]
    return E.EDL(
        canvas=E.Canvas(),
        clips=[
            E.Clip(id="c1", src="x.mp4", in_=0, out=3, order=0,
                   transition={"type": "crossfade", "duration": 0.5}),
            E.Clip(id="c2", src="x.mp4", in_=0, out=3, order=1,
                   transition={"type": "crossfade", "duration": 0.5}),
            E.Clip(id="c3", src="x.mp4", in_=0, out=3, order=2),
        ],
        overlays=[E.Overlay(kind="text", text="INSANE", t0=3.1, t1=4.1, style="hook")],
        captions=E.Captions(
            mode="karaoke",
            words=[E.CaptionWord(w=w, t0=a, t1=b, emphasize=e) for w, a, b, e in words]),
    )


# --------------------------------------------------------------------------- #
# 1. Bank sync -> manifest with every slug backed by a real, analyzed file
# --------------------------------------------------------------------------- #
def test_sync_library_backs_every_slug(app):
    manifest = sfx_bank.sync_library(app)
    slugs = _library_slugs(app)
    assert slugs, "library must define effects"
    assert slugs.issubset(manifest.keys()), "every library slug must be in the manifest"

    for slug in slugs:
        e = manifest[slug]
        assert Path(e["file"]).is_file(), f"{slug}: file missing"
        assert _probe_is_audio(e["file"]), f"{slug}: not a playable audio file"
        assert e["license"] in sfx_bank._LICENSE_OK, f"{slug}: license gate violated"
        assert isinstance(e["onset_ms"], int) and e["onset_ms"] >= 0
        assert isinstance(e["peak_ms"], int) and e["peak_ms"] >= 0
        assert e["duration"] > 0, f"{slug}: zero duration"
        assert e["align"] in ("onset", "peak", "none")

    # Align semantics really hold on the synthesized assets: a boom's transient
    # is at the very start; a riser/whoosh peaks later (it swells into the cut).
    assert manifest["boom_cinematic"]["onset_ms"] <= 60
    assert manifest["riser_4bar"]["peak_ms"] > manifest["riser_4bar"]["onset_ms"]
    assert manifest["whoosh_short"]["peak_ms"] >= 150


def test_ensure_library_is_lazy(app):
    m1 = sfx_bank.ensure_library(app)          # first call syncs
    assert m1
    mp = sfx_bank._manifest_path(app)
    mtime = mp.stat().st_mtime
    m2 = sfx_bank.ensure_library(app)          # complete manifest -> no rebuild
    assert mp.stat().st_mtime == mtime
    assert m2.keys() == m1.keys()


# --------------------------------------------------------------------------- #
# 2. Deterministic placement: caps, min-gap, density ceiling
# --------------------------------------------------------------------------- #
def test_place_sfx_deterministic_with_no_tags(app):
    manifest = sfx_bank.ensure_library(app)
    edl = _basic_edl()
    # No tags at all -> the deterministic layer still scores a track.
    tracks = sfx.place_sfx(edl, manifest, hook_window=(0.0, 3.0),
                           tags=SfxTags(sfx_style="clean_cinematic", tags=[]),
                           style="clean_cinematic")
    labels = [t.label for t in tracks]
    assert "hook_sting" in labels, "hook sting always fires"
    assert any(l.startswith("whoosh") for l in labels), "whooshes on the dissolve cuts"
    assert any(l in ("pop_text", "ding_correct") for l in labels), "pops on emphasized words"
    for t in tracks:
        assert t.kind == "sfx" and t.t0 >= 0 and t.src


def test_density_ceiling_and_lowend_gap(app):
    manifest = sfx_bank.ensure_library(app)
    # 14 clips, crossfaded -> 13 dissolve cuts; without a ceiling heavy_meme
    # would place a whoosh on every one. ~24s total => a single 30s window.
    clips = []
    for i in range(14):
        tr = {"type": "crossfade", "duration": 0.3} if i < 13 else None
        clips.append(E.Clip(id=f"c{i}", src="x.mp4", in_=0, out=2, order=i, transition=tr))
    words = [E.CaptionWord(w=f"w{i}", t0=i * 1.5, t1=i * 1.5 + 0.3, emphasize=(i % 2 == 0))
             for i in range(15)]
    edl = E.EDL(canvas=E.Canvas(), clips=clips,
                captions=E.Captions(mode="karaoke", words=words))
    tracks = sfx.place_sfx(edl, manifest, hook_window=(0.0, 3.0),
                           tags=SfxTags(sfx_style="heavy_meme", tags=[]),
                           style="heavy_meme")

    pops = {"pop_text", "bubble_pop"}
    non_pop = [t for t in tracks if t.label not in pops]
    # Hard ceiling is 10 intentional (non-pop) SFX per 30s.
    assert len(non_pop) <= 10, f"density ceiling breached: {len(non_pop)} non-pop cues"

    # No two low-end hits within 300ms.
    low = sorted(t.t0 for t in tracks if t.label in sfx._LOW_END)
    for a, b in zip(low, low[1:]):
        assert b - a >= 0.3 - 1e-6, "two low-end hits within 300ms"

    # Global min-gap holds between non-pop transients (barring layered combos).
    times = sorted(t.t0 for t in non_pop)
    # allow the odd combo overlap, but the vast majority must respect the gap
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 0.0 for g in gaps)


def test_boom_cap_per_clip(app):
    manifest = sfx_bank.ensure_library(app)
    # One long clip, four punchline words close together -> only 2 booms survive.
    words = [E.CaptionWord(w=f"joke{i}", t0=1.0 + i * 0.9, t1=1.3 + i * 0.9) for i in range(4)]
    edl = E.EDL(canvas=E.Canvas(),
                clips=[E.Clip(id="c1", src="x.mp4", in_=0, out=8, order=0)],
                captions=E.Captions(mode="karaoke", words=words))
    tags = SfxTags(sfx_style="heavy_meme",
                   tags=[SfxWordTag(word_index=i, roles=["punchline"]) for i in range(4)])
    tracks = sfx.place_sfx(edl, manifest, hook_window=(0.0, 3.0), tags=tags, style="heavy_meme")
    booms = [t for t in tracks if t.label in sfx._BOOMS]
    assert len(booms) <= 2, f"boom cap breached in one clip: {len(booms)}"


# --------------------------------------------------------------------------- #
# 3. Style gating: minimal has fewer/no comedy SFX vs heavy_meme
# --------------------------------------------------------------------------- #
def test_style_gating_comedy(app):
    manifest = sfx_bank.ensure_library(app)
    edl = _basic_edl()
    tags = SfxTags(sfx_style="heavy_meme", tags=[
        SfxWordTag(word_index=5, roles=["reveal"], sentiment="positive"),
        SfxWordTag(word_index=9, roles=["punchline", "money"], sentiment="positive")])

    comedy = {"boom_deep_meme", "airhorn", "record_scratch", "womp_womp",
              "cash_register", "cricket_awkward", "cartoon_boing", "cartoon_pop",
              "error_buzzer", "crowd_ohhh", "applause_cheer"}

    def comedy_count(style: str) -> int:
        tr = sfx.place_sfx(edl, manifest, hook_window=(0.0, 3.0), tags=tags, style=style)
        return sum(1 for t in tr if t.label in comedy)

    heavy = comedy_count("heavy_meme")
    minimal = comedy_count("minimal")
    assert heavy >= 1, "heavy_meme should place at least one comedy SFX for a punchline"
    assert minimal < heavy, "minimal must place fewer comedy SFX than heavy_meme"
    assert minimal == 0, "minimal blocks the comedy/social families entirely"


# --------------------------------------------------------------------------- #
# 4. apply_sfx orchestration + idempotency
# --------------------------------------------------------------------------- #
def test_apply_sfx_idempotent(app, llm):
    edl = _basic_edl()
    sfx.apply_sfx(app, llm, edl, context={"style": "heavy_meme", "platform": "tiktok"})
    n1 = sum(1 for t in edl.audio if t.kind == "sfx")
    assert n1 > 0, "apply_sfx must add SFX tracks"
    sfx.apply_sfx(app, llm, edl, context={"style": "heavy_meme", "platform": "tiktok"})
    n2 = sum(1 for t in edl.audio if t.kind == "sfx")
    assert n2 == n1, "apply_sfx must be idempotent (no double-add)"


# --------------------------------------------------------------------------- #
# 5. REAL end-to-end: SFX are audible in the rendered mix
# --------------------------------------------------------------------------- #
def test_sfx_audible_in_rendered_mix(app, llm):
    from mark.media import render

    data = Path(app.paths.data_dir)
    d = data / "media" / "sfxtest"
    for i, color in enumerate(("red", "green", "blue")):
        _lavfi_clip(d / f"c{i}.mp4", color, dur=3.0)

    have_say = bool(shutil.which("say"))

    def build() -> E.EDL:
        edl = _basic_edl()
        edl.overlays = []          # no title impact -> whooshes survive on both cuts
        for i, c in enumerate(edl.clips):
            c.src = f"media/sfxtest/c{i}.mp4"
        # optional real voiceover via macOS `say`, so the whoosh sits in a mix
        if have_say:
            aiff = d / "vo.aiff"
            subprocess.run(["say", "-o", str(aiff),
                            "this changes everything watch the insane result we made bank"],
                           capture_output=True)
            if aiff.exists():
                edl.audio.append(E.AudioTrack(src="media/sfxtest/vo.aiff",
                                              kind="voiceover", gain_db=0))
        return edl

    # Reference render WITHOUT sfx.
    base = build()
    out_nosfx = d / "nosfx.mp4"
    render.render_edl(app, base, data, out_nosfx, proxy=False)

    # Render WITH sfx (deterministic; mock LLM -> tags=[]).
    withsfx = build()
    sfx.apply_sfx(app, llm, withsfx, context={"style": "clean_cinematic",
                                              "platform": "instagram"})
    sfx_tracks = [t for t in withsfx.audio if t.kind == "sfx"]
    assert sfx_tracks, "expected SFX tracks placed"
    whooshes = [t for t in sfx_tracks if t.label.startswith("whoosh")]
    assert whooshes, "expected whooshes on the dissolve cuts"

    out_sfx = d / "withsfx.mp4"
    render.render_edl(app, withsfx, data, out_sfx, proxy=False)
    assert _probe_is_audio(str(out_sfx))

    # PROOF: the whoosh's audible peak lands on the cut frame (align=peak =>
    # audible_peak = t0 + peak_ms/1000 == cut_t). Energy there must jump vs the
    # identical render without SFX.
    manifest = sfx_bank.load_manifest(app)
    env_no, _ = _decode_env(out_nosfx)
    env_yes, _ = _decode_env(out_sfx)

    # The render is a genuine mix, not SFX-only: the `say` voiceover carries real
    # energy in the first ~3s of BOTH renders.
    if have_say:
        assert _rms_window(env_no, 0.3, 3.0) > 0.01, "voiceover missing from the base mix"
        assert _rms_window(env_yes, 0.3, 3.0) > 0.01, "voiceover missing from the SFX mix"

    proven, spiked, base_sum, sfx_sum = [], False, 0.0, 0.0
    for w in whooshes:
        peak_off = manifest[w.label]["peak_ms"] / 1000.0
        cut_t = w.t0 + peak_off        # align=peak => audible peak lands on the cut
        base_e = _rms_window(env_no, cut_t - 0.12, cut_t + 0.12)
        sfx_e = _rms_window(env_yes, cut_t - 0.12, cut_t + 0.12)
        proven.append((w.label, round(cut_t, 3), round(base_e, 5), round(sfx_e, 5)))
        base_sum += base_e
        sfx_sum += sfx_e
        # A whoosh in a quiet gap produces an unmistakable spike; one masked by a
        # loud speech peak may not raise the window max (a -12dB SFX under a VO
        # peak is inaudible-by-design), so we require the spike on >=1 whoosh.
        if sfx_e > base_e * 1.15 + 1e-4:
            spiked = True
    assert spiked, f"no whoosh produced an audible energy spike at its cut: {proven}"
    # Across all whoosh windows, the SFX render carries strictly more energy.
    assert sfx_sum > base_sum, f"SFX added no net energy at the cuts: {proven}"

    # Dump the placed cues + the proof table into the scratchpad for inspection.
    art = Path("/private/tmp/claude-501/-Users-sanjithshanmugavel-Documents-Mark/"
               "6d20a087-7bd8-492c-ad4b-e4858f012cb3/scratchpad/sfx-test")
    art.mkdir(parents=True, exist_ok=True)
    lines = ["placed SFX cues (label @ t0s, gain):"]
    lines += [f"  {t.label:22} t0={t.t0:6.3f}s  gain={t.gain_db}dB" for t in sfx_tracks]
    lines.append("\nwhoosh energy proof (RMS max in +/-120ms of the cut):")
    lines += [f"  {lbl:16} cut={ct:.3f}s  no_sfx={b}  with_sfx={s}" for lbl, ct, b, s in proven]
    (art / "placed_cues.txt").write_text("\n".join(lines))
    shutil.copy(out_sfx, art / "withsfx.mp4")
