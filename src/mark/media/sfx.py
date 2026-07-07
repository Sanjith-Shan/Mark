"""Sound-effects placement engine (Contract 7).

Operates on an :class:`~mark.media.edl.EDL`, appending ``AudioTrack(kind="sfx")``
tracks the renderer already knows how to mix (``render._audio_graph`` folds every
``kind="sfx"`` track into the bus at its own ``t0``/``gain_db``). Templates emit
clean EDLs; the central produce path calls :func:`apply_sfx` to augment them.

Design split (from the research spec):
  * DETERMINISTIC engine (this file) owns everything mechanical & time-critical:
    cut detection from ``edl.clips``, whoosh-on-transition, caption-pop sync,
    riser scheduling, transient-offset alignment, gain staging, the density
    governor, min-gap / boom caps, and style gating. Fully deterministic — runs
    with ``tags=[]`` and no LLM.
  * The LLM ``SfxTags`` pass (:func:`tag_script`) ONLY labels which script words
    carry meaning a sound designer would punctuate (reveal / punchline / emphasis
    / question / money + sentiment) and picks one ``sfx_style``. It never emits
    timestamps, gains, or file choices, so rendering stays deterministic. Offline
    / ``force_mock`` degrades to ``tags=[]`` + a platform-default style; the
    deterministic layer still scores a full track.

Transient alignment (the load-bearing invariant): each asset carries a
precomputed ``onset_ms``/``peak_ms`` in the manifest. Placement sets
``t0 = target − onset_ms/1000`` for ``align: onset`` families and
``t0 = target − peak_ms/1000`` for ``align: peak`` (whooshes/risers swell INTO
the frame). The renderer drops the file at ``t0`` — pre-roll is our job.

INTEGRATION (central wiring — done by the orchestrator/owner, NOT here or in
templates; this module only exposes the functions):
  * config: add ``media.sfx_enabled: true`` (Contract 7 default) to
    ``config/default.yaml`` + the ``MediaSettings`` model. ``apply_sfx`` is
    called only when that flag is set.
  * produce path: after a template returns its EDL (and after captions/align
    have populated ``edl.captions.words``), call
    ``sfx.apply_sfx(app, llm, edl, context={...})`` where ``context`` may carry
    ``hook_window`` (t0,t1), ``sfx_style`` (the bandit pick), ``platform``,
    ``tone``, ``brand_voice``, and optional ``beats`` ({"drop": t, "bar_len": s}).
    It is idempotent (skips if the EDL already has ``kind="sfx"`` tracks) and
    saves the EDL like any other produce step.
  * CLI: add ``mark sfx sync`` -> ``sourcing.sfx_bank.sync_library(app)`` and
    ``mark sfx list`` -> ``sourcing.sfx_bank.load_manifest(app)``.
  * bandit: add ``arm_type="sfx_style"`` with values
    ``heavy_meme | clean_cinematic | minimal``; the Strategist emits the pick
    (passed via ``context["sfx_style"]``) and the feedback loop rewards it on
    engagement (heavy-meme tends to win TikTok, minimal LinkedIn).
  * .env.example: add ``FREESOUND_API_KEY=`` (free at
    freesound.org/apiv2/apply) — optional; the bank synthesizes offline without it.
  * editor API (already sketched in the contract): ``GET /api/sfx`` exposes
    ``load_manifest``; timeline edits become ``kind="sfx"`` tracks in the EDL.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..app import App
from . import edl as edl_mod
from .edl import EDL, AudioTrack

log = logging.getLogger("mark.media.sfx")

# --------------------------------------------------------------------------- #
# SfxTags — the LLM's ONLY job (models live here, not schemas.py, per ownership)
# --------------------------------------------------------------------------- #
class SfxWordTag(BaseModel):
    word_index: int
    roles: list[Literal["reveal", "punchline", "emphasis", "question", "money"]] = Field(
        default_factory=list)
    sentiment: Literal["positive", "negative", "neutral"] = "neutral"


class SfxTags(BaseModel):
    sfx_style: Literal["heavy_meme", "clean_cinematic", "minimal"] = "clean_cinematic"
    tags: list[SfxWordTag] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Style presets (the bandit arm) — gate families + density BEFORE placement
# --------------------------------------------------------------------------- #
# None => all families allowed.
_STYLE_ALLOWED: dict[str, Optional[set[str]]] = {
    "heavy_meme": None,
    "clean_cinematic": {"transition", "impact", "riser", "aesthetic",
                        "suspense", "ui", "hook", "atmosphere"},
    "minimal": {"transition", "ui", "hook"},   # transition => whooshes only
}
_STYLE_DENSITY = {"heavy_meme": 10, "clean_cinematic": 6, "minimal": 3}

_DEFAULT_STYLE_BY_PLATFORM = {
    "tiktok": "heavy_meme", "youtube": "clean_cinematic", "instagram": "clean_cinematic",
    "x": "clean_cinematic", "threads": "clean_cinematic", "bluesky": "minimal",
    "linkedin": "minimal",
}

_GLOBAL_MIN_GAP = 0.6          # seconds between transients (pops exempt)
_LOW_END_MIN_GAP = 0.3         # no two low-end hits within 300ms
_LOW_END = {"boom_cinematic", "boom_deep_meme", "bass_drop", "screen_shake_rumble"}
_BOOMS = {"boom_cinematic", "boom_deep_meme"}   # share the 2-per-clip cap

# priorities (lower = kept first under the density governor)
_P_HOOK, _P_ACCENT, _P_TITLE, _P_WHOOSH, _P_POP = 0, 1, 2, 3, 4


@dataclass
class _Cue:
    slug: str
    target_t: float
    family: str
    entry: dict
    priority: int
    salience: float = 0.5
    clip_index: int = 0
    gain_trim: float = 0.0
    combo: bool = False        # layered stack (riser->impact / impact+rumble)
    is_pop: bool = False       # caption-synced pop: exempt from gap + ceiling
    beats_lock: bool = False   # boom locked to a spoken word — never nudge off it


# --------------------------------------------------------------------------- #
# Timeline geometry (derived exactly from the EDL — no detection needed)
# --------------------------------------------------------------------------- #
def _cut_points(edl: EDL) -> list[dict]:
    """Seam times + transition type for every clip boundary. Mirrors the
    renderer's fold (``render.render_edl``) so cut timing is exact."""
    clips = edl.clips
    durs = [edl_mod.clip_seconds(c) for c in clips]
    trans = edl_mod.transition_seconds(edl)
    cuts: list[dict] = []
    cur = durs[0] if durs else 0.0
    for i in range(1, len(clips)):
        d = trans[i - 1]
        if d > 0:
            cut_t = cur - d / 2.0          # midpoint of the crossfade
            ttype = "dissolve"
            cur = cur + durs[i] - d
        else:
            cut_t = cur
            ttype = "cut"
            cur = cur + durs[i]
        cuts.append({"t": cut_t, "index": i, "type": ttype})
    return cuts


def _clip_boundaries(edl: EDL, cuts: list[dict], total: float) -> list[float]:
    """Timeline boundaries [0, cut0, cut1, …, total] for clip lookup."""
    return [0.0] + [c["t"] for c in cuts] + [total]


def _clip_of(boundaries: list[float], t: float) -> int:
    idx = bisect_right(boundaries, t) - 1
    return max(0, min(idx, len(boundaries) - 2))


# --------------------------------------------------------------------------- #
# The deterministic placement engine
# --------------------------------------------------------------------------- #
def place_sfx(edl: EDL, manifest: dict, *, hook_window: tuple[float, float],
              tags: SfxTags, style: str,
              beats: Optional[dict] = None) -> list[AudioTrack]:
    """Return the ``kind="sfx"`` tracks for ``edl``. Deterministic; works with
    ``tags.tags == []`` (hook sting + whooshes on cuts + caption pops + title
    impacts still fire). ``manifest`` entries carry the placement policy
    (family/align/gain/cap/min_gap + onset_ms/peak_ms) merged at sync time."""
    style = style if style in _STYLE_DENSITY else "clean_cinematic"
    allowed = _STYLE_ALLOWED.get(style)
    density = _STYLE_DENSITY[style]

    words = edl.captions.words
    cuts = _cut_points(edl)
    total = edl_mod.visual_duration(edl)
    boundaries = _clip_boundaries(edl, cuts, total)
    tagged: dict[int, SfxWordTag] = {t.word_index: t for t in tags.tags}

    cands: list[_Cue] = []

    def add(slug: str, target_t: float, *, priority: int, salience: float = 0.5,
            gain_trim: float = 0.0, combo: bool = False, beats_lock: bool = False) -> None:
        entry = manifest.get(slug)
        if entry is None:
            return
        fam = entry.get("family", "")
        if allowed is not None and fam not in allowed:
            return
        # minimal keeps only whooshes from the transition family.
        if style == "minimal" and fam == "transition" and not slug.startswith("whoosh"):
            return
        target_t = max(0.0, min(float(target_t), total))
        gmin = entry.get("min_gap_s")
        is_pop = fam == "ui" and gmin == 0.0
        cands.append(_Cue(slug=slug, target_t=target_t, family=fam, entry=entry,
                          priority=priority, salience=salience,
                          clip_index=_clip_of(boundaries, target_t),
                          gain_trim=gain_trim, combo=combo, is_pop=is_pop,
                          beats_lock=beats_lock))

    # --- Rule 1: hook sting — exactly one, on the first hook-word onset ------ #
    hw0, hw1 = hook_window
    first_word = next((w for w in words if w.t1 > hw0 and w.t0 < hw1),
                      words[0] if words else None)
    hook_t = first_word.t0 if first_word else hw0
    add("hook_sting", hook_t, priority=_P_HOOK, salience=1.0)

    # --- Rule 2/3: risers + booms/impacts + money from tags ----------------- #
    for t in tags.tags:
        if not (0 <= t.word_index < len(words)):
            continue
        w = words[t.word_index]
        roles = set(t.roles)
        ci = _clip_of(boundaries, w.t0)
        if "punchline" in roles:
            # a hair after the joke lands so the boom IS the payoff
            add("boom_deep_meme", w.t0, priority=_P_ACCENT, salience=0.9, beats_lock=True)
        if "reveal" in roles:
            add("boom_cinematic", w.t0, priority=_P_ACCENT, salience=0.85, beats_lock=True)
            runway = w.t0 - boundaries[ci]      # clear time before the reveal in its clip
            riser = ("riser_4bar" if runway >= 3.0
                     else "riser_2bar" if runway >= 1.5 else None)
            if riser:
                # peak == the reveal frame; crossfades into the impact (combo)
                add(riser, w.t0, priority=_P_ACCENT, salience=0.8, combo=True)
        if "money" in roles:
            add("cash_register", w.t0, priority=_P_ACCENT, salience=0.7)

    # --- Rule 7 (music sync): bass drop on the beat drop -------------------- #
    if beats:
        drop = beats.get("drop")
        if drop is not None:
            add("bass_drop", float(drop), priority=_P_ACCENT, salience=0.95)

    # --- Rule 4: whooshes on transitions ------------------------------------ #
    for c in cuts:
        is_dissolve = c["type"] == "dissolve"
        has_title = any(abs(o.t0 - c["t"]) < 0.35 for o in edl.overlays)
        if not (is_dissolve or has_title or style == "heavy_meme"):
            continue  # skip static hard cuts with no motion and no title
        slug = "whoosh_long_cinematic" if is_dissolve else "whoosh_short"
        add(slug, c["t"], priority=_P_WHOOSH,
            salience=0.6 if is_dissolve else 0.45)

    # --- Rule 5: impacts on title/text lands -------------------------------- #
    for o in edl.overlays:
        add("impact_hit_mid", o.t0, priority=_P_TITLE, salience=0.5)

    # --- Rule 6: caption pops on emphasized / emphasis-tagged words --------- #
    for i, w in enumerate(words):
        tag = tagged.get(i)
        roles = set(tag.roles) if tag else set()
        if "punchline" in roles or "reveal" in roles:
            continue  # a boom already carries this beat
        if not (w.emphasize or "emphasis" in roles or "money" in roles):
            continue
        positive = bool(tag and tag.sentiment == "positive")
        slug = "ding_correct" if positive else "pop_text"
        # transient in the 60-120ms gap BEFORE the word so it never masks the consonant
        add(slug, max(0.0, w.t0 - 0.08), priority=_P_POP, salience=0.3)

    # --- Rule 7 (nudge): quantize non-boom accents to the nearest beat ------ #
    if beats and beats.get("beat_times"):
        bts = sorted(float(x) for x in beats["beat_times"])
        for c in cands:
            if c.beats_lock or c.is_pop:
                continue
            nb = min(bts, key=lambda b: abs(b - c.target_t))
            if abs(nb - c.target_t) <= 0.08:
                c.target_t = nb

    return _arbitrate(cands, density)


def _is_combo(a: _Cue, b: _Cue) -> bool:
    """Intended layered stacks that are allowed to overlap the min-gap."""
    if not (a.combo or b.combo):
        # rumble under an impact is always a layer, even without the flag
        slugs = {a.slug, b.slug}
        if "screen_shake_rumble" in slugs and {"impact"} & {a.family, b.family}:
            return abs(a.target_t - b.target_t) < 0.25
        return False
    fams = {a.family, b.family}
    if fams == {"riser", "impact"} and abs(a.target_t - b.target_t) < 0.3:
        return True
    return False


def _window_ok(accepted_times: list[float], t: float, density: int,
               span: float = 30.0) -> bool:
    """True if adding a cue at ``t`` keeps every ``span``-second window at or
    below ``density`` cues. Anchored at each cue time near ``t`` (any densest
    window's left edge coincides with a cue)."""
    times = sorted(s for s in accepted_times if t - span < s < t + span)
    times.append(t)
    times.sort()
    for s in times:
        if sum(1 for x in times if s <= x < s + span) > density:
            return False
    return True


def _arbitrate(cands: list[_Cue], density: int) -> list[AudioTrack]:
    """Density governor + min-gap / boom-cap / low-end / per-slug-cap guardrails.
    Greedy by priority then salience, so the load-bearing beats survive."""
    cands.sort(key=lambda c: (c.priority, -c.salience, c.target_t))
    accepted: list[_Cue] = []

    for c in cands:
        gmin = c.entry.get("min_gap_s")
        gmin = _GLOBAL_MIN_GAP if gmin is None else float(gmin)

        # min-gap vs already-accepted transients (pops don't participate at all)
        if not c.is_pop:
            clash = False
            for a in accepted:
                if a.is_pop:
                    continue
                a_gmin = a.entry.get("min_gap_s")
                a_gmin = _GLOBAL_MIN_GAP if a_gmin is None else float(a_gmin)
                if abs(a.target_t - c.target_t) < max(gmin, a_gmin):
                    if _is_combo(a, c):
                        continue
                    clash = True
                    break
            if clash:
                continue

        # never two low-end hits within 300ms
        if c.slug in _LOW_END and any(
                a.slug in _LOW_END and abs(a.target_t - c.target_t) < _LOW_END_MIN_GAP
                for a in accepted):
            continue

        # boom cap: <=2 booms per clip (shared)
        if c.slug in _BOOMS and sum(
                1 for a in accepted if a.slug in _BOOMS and a.clip_index == c.clip_index) >= 2:
            continue

        # per-slug per-clip cap from the library
        cap = c.entry.get("cap")
        if cap is not None and sum(
                1 for a in accepted if a.slug == c.slug and a.clip_index == c.clip_index) >= cap:
            continue

        # global density ceiling: no 30s window may exceed ``density`` intentional
        # (non-pop) SFX. Check that ADDING this cue keeps every 30s window legal.
        if not c.is_pop and not _window_ok(
                [a.target_t for a in accepted if not a.is_pop], c.target_t, density):
            continue

        accepted.append(c)

    tracks: list[AudioTrack] = []
    for c in accepted:
        align = c.entry.get("align", "onset")
        off_ms = c.entry.get("peak_ms" if align == "peak" else "onset_ms", 0) or 0
        t0 = max(0.0, c.target_t - off_ms / 1000.0)
        gain = float(c.entry.get("base_gain_db", -12)) + c.gain_trim
        tracks.append(AudioTrack(kind="sfx", src=c.entry["file"], t0=round(t0, 3),
                                 gain_db=round(gain, 2), label=c.slug))
    tracks.sort(key=lambda t: t.t0)
    return tracks


# --------------------------------------------------------------------------- #
# LLM SfxTags pass (the ONE semantic input the timeline can't yield)
# --------------------------------------------------------------------------- #
_TAGGER_SYSTEM = (
    "You are an SFX beat-tagger for short-form video. You do NOT choose sounds, "
    "volumes, or timings. You ONLY label which script moments carry meaning that "
    "a sound designer would punctuate. Be sparing — most words get no tag. "
    "Over-tagging produces noise; the engine hard-caps density regardless, so "
    "flag only the genuinely load-bearing beats.\n\n"
    "Roles per word: reveal (a payoff/answer/turns-out/before->after moment); "
    "punchline (the funny/absurd/ironic/shock beat — the engine may drop a boom "
    "here); emphasis (a superlative, number, or intensifier worth a caption pop); "
    "question (a rhetorical hook question); money (a price/savings/earnings/$$$ "
    "beat). Also per flagged word: sentiment in {positive,negative,neutral}.\n"
    "Also return exactly one sfx_style in {heavy_meme,clean_cinematic,minimal} for "
    "the whole clip (comedic/TikTok -> heavy_meme; polished IG/YT -> "
    "clean_cinematic; professional/LinkedIn -> minimal)."
)


def _default_style(platform: str) -> str:
    return _DEFAULT_STYLE_BY_PLATFORM.get((platform or "").lower(), "clean_cinematic")


def tag_script(app: App, llm, words, platform: str, tone: str,
               brand_voice: str) -> SfxTags:
    """LLM SfxTags pass over the caption words. Offline / ``force_mock`` / no LLM
    -> ``tags=[]`` + a platform-default style, so the deterministic layer still
    produces a full track with zero LLM spend."""
    style = _default_style(platform)
    if llm is None or getattr(llm, "mock", True) or not words:
        return SfxTags(sfx_style=style, tags=[])

    numbered = "\n".join(f"{i}: {w.w}" for i, w in enumerate(words))
    user = (f"Script words (index: word):\n{numbered}\n\n"
            f"Platform: {platform}   Tone: {tone}   Product voice: {brand_voice}")

    def _mock() -> SfxTags:
        return SfxTags(sfx_style=style, tags=[])

    try:
        return llm.parse(_TAGGER_SYSTEM, user, SfxTags,
                         model=getattr(app.settings.llm, "judge_model", None),
                         temperature=0.2, mock_factory=_mock)
    except Exception as exc:  # noqa: BLE001 — tagging must never break produce
        log.warning("SfxTags LLM pass failed (%s) — deterministic layer only", exc)
        return SfxTags(sfx_style=style, tags=[])


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def apply_sfx(app: App, llm, edl: EDL, *, context: Optional[dict] = None) -> EDL:
    """Ensure the SFX bank, tag the script (if an LLM is given), place the cues,
    and append the ``kind="sfx"`` tracks to ``edl.audio``. Idempotent: a no-op if
    the EDL already carries SFX tracks. Returns the same EDL."""
    if any(t.kind == "sfx" for t in edl.audio):
        return edl

    from ..sourcing import sfx_bank

    ctx = context or {}
    try:
        manifest = sfx_bank.ensure_library(app)
    except Exception as exc:  # noqa: BLE001 — no SFX is better than a broken render
        log.warning("SFX bank unavailable (%s) — skipping SFX", exc)
        return edl
    if not manifest:
        return edl

    words = edl.captions.words
    hook_window = ctx.get("hook_window")
    if hook_window is None:
        hook_window = (0.0, min(3.0, edl_mod.visual_duration(edl)))
    platform = ctx.get("platform", "tiktok")
    tone = ctx.get("tone", "")
    brand_voice = ctx.get("brand_voice", "")

    tags = tag_script(app, llm, words, platform, tone, brand_voice)
    style = ctx.get("sfx_style") or ctx.get("style")
    if style:
        tags.sfx_style = style   # explicit override (e.g. the bandit pick)

    tracks = place_sfx(edl, manifest, hook_window=tuple(hook_window),
                       tags=tags, style=tags.sfx_style, beats=ctx.get("beats"))
    edl.audio.extend(tracks)

    try:
        from .. import db as db_module

        db_module.log_activity(
            app.conn, "sfx",
            f"Placed {len(tracks)} SFX cue(s) [{tags.sfx_style}]: "
            + ", ".join(f"{t.label}@{t.t0:.2f}s" for t in tracks[:8])
            + ("…" if len(tracks) > 8 else ""))
    except Exception:
        pass
    return edl
