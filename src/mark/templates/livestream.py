"""Livestream clipping — the ``stream-clips`` content template.

Turn audience-voted livestream moments (Twitch clips) into edited 9:16 shorts:
find the moment the stream's own viewers already clipped, download it, reformat
it into the facecam-top / gameplay-bottom stacked layout that the 2026 format
meta demands (raw reposts get demoted by TikTok/YouTube originality
enforcement — the heavy re-edit IS the "added value" defense), burn word-synced
captions and a first-frame hook, keep the streamer's own audio, and credit the
streamer on-screen and in the caption.

Discovery clones the humor-radar pattern: poll a permissioned roster's top clips
(``sourcing.twitch.get_clips`` returns them in descending view order), score each
by view-velocity + vod_offset CLUSTERING (multiple viewers clipping the same
~5-min VOD window is the single strongest virality signal — the audience voted),
judge each with the LLM (clip-worthiness + a first-frame hook + a licensed-music
safety flag), track velocity/stage the way ``humor_radar`` and the trend radar do,
and upsert every sighting into the ``stream_finds`` table.

HARD RULES (permission-first, enforced by the strategy shape + the pipeline):
  * PERMISSION-FIRST ROSTER. Clips are the streamer's copyright (plus game
    publisher + any music). The roster is seeded ONLY from broadcasters we have
    written permission for — paid clipping campaigns (Whop Content Rewards /
    Clipify) or streamers who explicitly allow credited clip pages. The default
    roster below is a documented PLACEHOLDER; production rosters come from the
    ``clip_campaigns`` permission records / campaign onboarding.
  * NEVER AUTO-APPROVE. ``STRATEGY.never_auto_approve = True`` — a human judges
    and posts every clip (taste + rights are human calls; a bad repost is an
    account-killer). Campaign submission is always a human click.
  * CREDIT ALWAYS CARRIED. On-screen ("clip: twitch.tv/<streamer>") + in the
    caption/strategy_context; this is a fair-use posture, not an afterthought.
  * DROP UNSAFE FINDS AT THE DOOR. Anything the judge flags as licensed-music /
    unclear-rights is never surfaced for posting (Content ID hits regardless of
    the streamer's consent).
  * REAL FOOTAGE → ``ai_generated = False``. No AI-disclosure burn (it isn't AI),
    but the streamer credit is mandatory instead.

INTEGRATION (central wiring the orchestrator owns — NOT done here)
------------------------------------------------------------------
* Dispatch: ``mark.templates`` already lists ``livestream`` in ``_MODULES`` and
  wires ``PRODUCERS["stream-clips"] = produce`` + ``DISCOVERY["stream-clips"] =
  refresh`` via ``ensure_loaded()``. No change needed.
* Scheduler: call :func:`refresh` from the fast-trends pulse
  (``scheduler/engine.py:job_trends_fast``) alongside ``humor_radar.refresh`` so
  fresh clips land in ``stream_finds`` between generation passes.
* Roster source: production should replace :func:`_roster` results with the
  permissioned broadcasters recorded in ``clip_campaigns`` (login + credit
  string + submission deadline). This module owns no roster of record — the
  default is a placeholder that makes the offline/mock pipeline run.
* Twitch/yt-dlp env keys live in ``sourcing.twitch`` / ``sourcing.ytdlp``; both
  degrade to deterministic offline mocks when keys are absent, so this whole
  template runs end-to-end under ``App.force_mock`` with no credentials.
* Per-streamer facecam crop rects (:data:`_FACECAM_DEFAULT`) are static per
  overlay layout; a one-shot GPT-4o-vision call on a sample frame to auto-detect
  the facecam rectangle is a documented FUTURE add — until then the default rect
  (or a per-streamer override in the roster) is used.
* Choosing which clip a content row renders: put the ``stream_finds.id`` in the
  content's ``strategy_context["stream_find_id"]`` at draft time; :func:`produce`
  falls back to the top :func:`radar` item when it is absent.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .. import db as db_module
from .. import store
from ..app import App
from ..llm import LLM
from ..media import align
from ..media import edl as edl_mod
from ..media import render as render_mod
from ..sourcing import twitch, ytdlp
from ..strategies import Strategy

log = logging.getLogger("mark.templates.livestream")

STRATEGY_ID = "stream-clips"

# Velocity/stage math mirrors humor_radar / trends — same longitudinal discipline
# (view-count growth vs. earlier sightings of the same clip).
_VEL_MIN_AGE_H, _VEL_MAX_AGE_H, _STAGE_EPS = 1, 72, 0.03
_CLUSTER_WINDOW_S = 300  # vod_offsets within this share "the moment"

# 9:16 stacked layout — facecam band on top, gameplay below (the 2026 meta).
CANVAS_W, CANVAS_H = 1080, 1920
_TOP_H = 768                     # facecam band (~40%); gameplay = 1152 (~60%)
# Crop rects as (x, y, w, h) FRACTIONS of the source frame. Per-streamer and
# static per overlay layout — override per roster entry; GPT-4o-vision auto-detect
# is the documented future upgrade. Defaults: a top-left webcam box + full-frame
# gameplay (works for any input size; produces two visibly distinct regions).
_FACECAM_DEFAULT = (0.0, 0.0, 0.40, 0.45)
_GAMEPLAY_DEFAULT = (0.0, 0.0, 1.0, 1.0)


# --------------------------------------------------------------------------- #
# Roster — PLACEHOLDER (see module docstring / INTEGRATION). Production rosters
# are seeded from permissioned clip_campaigns records, never hardcoded here.
# --------------------------------------------------------------------------- #
_DEFAULT_ROSTER: list[dict] = [
    {"login": "mockstreamer", "game": "Just Chatting", "campaign": "example-clip-program"},
    {"login": "pixelqueen", "game": "VALORANT", "campaign": "example-clip-program"},
    {"login": "grindcaster", "game": "Minecraft", "campaign": "example-clip-program"},
]


def _roster(app: App) -> list[dict]:
    """The permissioned broadcaster roster. Placeholder default; production
    should return the broadcasters recorded in ``clip_campaigns``."""
    return list(_DEFAULT_ROSTER)


# --------------------------------------------------------------------------- #
# Strategy — grounded in the research (permission-first, human-in-the-loop,
# facecam/gameplay stacked reformat, credited repost of REAL footage).
# --------------------------------------------------------------------------- #
STRATEGY = Strategy(
    id=STRATEGY_ID,
    name="Livestream clips",
    description=(
        "Reformat audience-voted livestream moments (Twitch clips from a "
        "permissioned roster) into credited 9:16 shorts: facecam-top / "
        "gameplay-bottom stack, word-synced captions, first-frame hook, the "
        "streamer's own audio kept. The moment is found by the stream's own "
        "viewers (clip-creation velocity + vod_offset clustering), not guessed. "
        "Heavy re-editing is both the engagement meta and the originality-policy "
        "defense; permission + credit is the rights posture."
    ),
    emotional_target="dark_laughter",
    platforms={
        "tiktok": "stacked facecam/gameplay 9:16, 15-45s, word-synced captions, hook on frame one; credit in caption",
        "instagram": "same as Reels; credit the streamer + campaign handle; CTA aims at shares",
        "youtube": "Shorts; #Shorts in description; title carries the hook; credit in description",
    },
    content_types=["video"],
    humor_level="none",             # the humor is in the real footage, not written
    uses_character=False,
    strategist_brief=(
        "Pick a clip already surging on a PERMISSIONED streamer (high view "
        "velocity + a vod_offset cluster = multiple viewers clipped the same "
        "moment). Never a raw repost — the value is the stacked reformat, hook, "
        "and captions. Skip anything flagged for licensed music."
    ),
    writer_brief=(
        "Caption is one dry line + a mandatory credit ('clip: twitch.tv/<streamer>' "
        "per the campaign's required format). Never claim the moment as your own. "
        "Vary the hook/caption per platform (originality enforcement demotes "
        "identical reposts)."
    ),
    media_brief=(
        "Facecam cropped to the top band, gameplay below, 1080x1920. First-frame "
        "hook overlay (0-2.5s). Word-synced captions in the lower region. Keep "
        "the clip's original audio. No AI generation — this is real footage."
    ),
    mix_weight=0.08,
    never_auto_approve=True,        # human-in-the-loop, always
    requires_product=False,         # the clip IS the content; no product to demo
)


# --------------------------------------------------------------------------- #
# Judge — is this clip worth editing, and is it safe to touch?
# --------------------------------------------------------------------------- #
class _ClipVerdict(BaseModel):
    external_id: str = ""
    keep: float = 0.5          # 0..1 — clip-worthiness (would this pop as a short)
    hook_text: str = ""        # <8 words, first-frame overlay
    caption: str = ""          # one dry line (credit is appended by the writer)
    category: str = "clutch"   # funny | rage | clutch | wholesome
    safe: bool = True          # False: licensed music / unclear rights — never use


class _ClipVerdicts(BaseModel):
    items: list[_ClipVerdict] = Field(default_factory=list)


def _hookify(title: Optional[str]) -> str:
    words = (title or "").strip().split()
    return " ".join(words[:8]) if words else "you had to be there"


def _judge(app: App, llm: LLM, clips: list[dict], streamer: str) -> dict[str, _ClipVerdict]:
    def _mock() -> _ClipVerdicts:
        # Offline heuristic: the audience already voted (view_count) — trust it.
        return _ClipVerdicts(items=[
            _ClipVerdict(
                external_id=f"twitch:{c['id']}",
                keep=round(min(0.95, 0.4 + (c.get("view_count") or 0) / 10000.0), 3),
                hook_text=_hookify(c.get("title")),
                caption=(c.get("title") or "").strip(),
                category="clutch", safe=True)
            for c in clips])

    if llm.mock or not clips:
        verdicts = _mock()
    else:
        listing = "\n".join(
            f'- id="twitch:{c["id"]}" views={c.get("view_count")} '
            f'dur={c.get("duration")}s "{c.get("title")}"' for c in clips[:40])
        system = (
            "You curate livestream clips for a human-approved clipping operation "
            f"(streamer: {streamer}, we have permission to clip them).\n"
            "For each clip return: keep (0..1 — would this stacked-and-captioned "
            "short actually pop on TikTok/Shorts; reward high-energy, self-"
            "contained moments, punish slow/context-dependent ones), hook_text "
            "(<8 words, a first-frame overlay that stops the scroll), caption "
            "(one dry line; DO NOT add credit — that is appended later), category "
            "(funny|rage|clutch|wholesome), and safe (false if the moment likely "
            "contains licensed/background music, TV/sports footage, or anything "
            "that would draw an automated Content ID claim regardless of the "
            "streamer's consent — when unsure, false).")
        verdicts = llm.parse(system, f"Judge these clips:\n{listing}", _ClipVerdicts,
                             model=app.settings.llm.judge_model, temperature=0.2,
                             mock_factory=_mock)
    return {v.external_id: v for v in verdicts.items}


# --------------------------------------------------------------------------- #
# Velocity + stage (longitudinal, same as humor_radar) + vod_offset clustering
# --------------------------------------------------------------------------- #
def _velocity(app: App, external_id: str, views_now: int) -> Optional[float]:
    rows = db_module.query(
        app.conn,
        "SELECT view_count FROM stream_finds WHERE external_id = ? "
        "AND collected_at >= datetime('now', ?) AND collected_at <= datetime('now', ?)",
        (external_id, f"-{_VEL_MAX_AGE_H} hours", f"-{_VEL_MIN_AGE_H} hours"))
    prior = [r["view_count"] for r in rows if r["view_count"] is not None]
    if not prior:
        return None
    base = sum(prior) / len(prior)
    return round((views_now - base) / max(base, 1.0), 4)  # relative growth


def _stage(velocity: Optional[float], views_now: int) -> str:
    if velocity is None:
        return "mature" if views_now >= 10000 else "new"
    if velocity > _STAGE_EPS:
        return "rising"
    if velocity < -_STAGE_EPS:
        return "declining"
    return "mature"


def _cluster_counts(clips: list[dict]) -> dict[int, int]:
    """How many clips share each clip's ~5-min VOD window. A high count means
    multiple viewers independently clipped the same moment — the strongest
    virality signal available."""
    offsets = [c.get("vod_offset") for c in clips if c.get("vod_offset") is not None]
    counts: dict[int, int] = {}
    for o in offsets:
        counts[o] = sum(1 for o2 in offsets if abs(o2 - o) <= _CLUSTER_WINDOW_S)
    return counts


# --------------------------------------------------------------------------- #
# Refresh — the collection pass (wired into the fast trend poll)
# --------------------------------------------------------------------------- #
def refresh(app: App, llm: LLM, *, limit_per_streamer: int = 20,
            started_hours: int = 6) -> list[dict]:
    """Poll every roster streamer's top recent clips, judge + score them, and
    upsert one ``stream_finds`` sighting per clip. Returns the stored finds,
    best (clip-worthiness) first."""
    roster = _roster(app)
    if not roster:
        return []
    users = {u["login"]: u for u in twitch.get_users(app, [r["login"] for r in roster])}
    started_at = (datetime.now(timezone.utc) - timedelta(hours=started_hours)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")

    stored: list[dict] = []
    for r in roster:
        user = users.get(r["login"])
        if not user:
            continue
        clips, _cursor = twitch.get_clips(app, user["id"], started_at=started_at,
                                          first=limit_per_streamer)
        if not clips:
            continue
        clusters = _cluster_counts(clips)
        verdicts = _judge(app, llm, clips, streamer=r["login"])
        n = len(clips)
        for rank, c in enumerate(clips):  # Helix order = descending views
            ext = f"twitch:{c['id']}"
            v = verdicts.get(ext, _ClipVerdict())
            views = int(c.get("view_count") or 0)
            vel = _velocity(app, ext, views)
            stage = _stage(vel, views)
            cluster = clusters.get(c.get("vod_offset"), 1)
            meta = {
                "creator": c.get("creator_name"), "cluster": cluster,
                "view_rank": rank, "campaign": r.get("campaign"),
                "category": v.category, "caption": v.caption,
                "facecam_rect": r.get("facecam_rect"),
            }
            db_module.insert(
                app.conn, "stream_finds",
                source="twitch", external_id=ext, streamer=r["login"],
                title=c.get("title"), clip_url=c.get("url"),
                game=r.get("game"), view_count=views, vod_offset=c.get("vod_offset"),
                duration=c.get("duration"), keep=round(v.keep, 3),
                hook_text=v.hook_text or _hookify(c.get("title")),
                safe=1 if v.safe else 0, velocity=vel, stage=stage,
                campaign_id=None, downloaded_path=None, metadata=meta)
            stored.append({
                "external_id": ext, "streamer": r["login"], "title": c.get("title"),
                "clip_url": c.get("url"), "view_count": views,
                "vod_offset": c.get("vod_offset"), "duration": c.get("duration"),
                "keep": v.keep, "hook_text": v.hook_text, "safe": v.safe,
                "velocity": vel, "stage": stage, "cluster": cluster,
                "category": v.category})
    purge_old(app)
    stored.sort(key=lambda x: x["keep"], reverse=True)
    return stored


def purge_old(app: App, days: int = 7) -> int:
    cur = db_module.execute(
        app.conn, "DELETE FROM stream_finds WHERE collected_at < datetime('now', ?)",
        (f"-{int(days)} days",))
    return cur.rowcount


# --------------------------------------------------------------------------- #
# Radar — what should we clip RIGHT NOW? (read side)
# --------------------------------------------------------------------------- #
def radar(app: App, llm: Optional[LLM] = None, *, limit: int = 12,
          max_age_hours: int = 24) -> list[dict]:
    """Ranked clip-worthy finds: latest sighting per clip, unsafe and declining
    vetoed, blended score = clip-worthiness + view-velocity momentum + moment
    cluster strength + audience view rank."""
    rows = db_module.query(
        app.conn,
        "SELECT * FROM stream_finds WHERE collected_at >= datetime('now', ?) "
        "ORDER BY collected_at DESC",
        (f"-{int(max_age_hours)} hours",))
    latest: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        latest.setdefault(d["external_id"], d)

    out = []
    for d in latest.values():
        if not d.get("safe"):
            continue
        if (d.get("stage") or "new") == "declining":
            continue  # the window is closed — hard veto
        meta = db_module.loads(d.get("metadata"), {}) or {}
        d["metadata"] = meta
        cluster = int(meta.get("cluster") or 1)
        momentum = max(0.0, min((d.get("velocity") or 0.0) + 0.05, 0.5)) / 0.5
        cluster_score = min(cluster, 5) / 5.0
        rank_score = 1.0 / (1.0 + int(meta.get("view_rank") or 0))
        score = (0.45 * (d.get("keep") or 0.5)
                 + 0.2 * momentum
                 + 0.2 * cluster_score
                 + 0.15 * rank_score)
        d["radar_score"] = round(score, 4)
        d["post_now"] = bool((d.get("stage") in ("new", "rising"))
                             and (d.get("keep") or 0) >= 0.55
                             and d.get("clip_url"))
        out.append(d)
    out.sort(key=lambda x: x["radar_score"], reverse=True)
    return out[:limit]


# --------------------------------------------------------------------------- #
# produce — download → stacked 9:16 reformat → EDL (hook + captions + original
# audio) → render.
# --------------------------------------------------------------------------- #
def produce(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
            out_dir: Path, character: Optional[dict] = None) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for clip reformatting")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    find = _chosen_find(app, llm, content_id)
    if not find:
        raise RuntimeError(
            "no clip-worthy stream_find available — run refresh() first or set "
            "strategy_context['stream_find_id']")

    # 1) Download the clip (permissioned). Mock/offline → a real lavfi clip.
    clip_url = (find.get("clip_url") or "").strip()
    if clip_url and not app.force_mock and not clip_url.startswith("mock"):
        dl_url = clip_url
    else:
        dl_url = f"mock:{find['external_id']}"
    raw = ytdlp.download(dl_url, out_dir)

    # 2) Reformat to the stacked 9:16 layout (facecam top, gameplay bottom).
    facecam = _facecam_rect(find)
    composed = out_dir / f"{content_id}_stacked.mp4"
    _reformat_vertical(raw, composed, facecam, _GAMEPLAY_DEFAULT)
    dur = _probe_duration(composed) or float(find.get("duration") or 8.0)

    # 3) Captions: ASR on the clip's REAL audio (unscripted); offline → even
    # spacing of a stand-in phrase so mock renders still carry karaoke captions.
    words: list = []
    if not app.force_mock:
        try:
            words = align.word_timestamps(app, composed, script=None, llm=llm)
        except Exception as exc:
            log.warning("clip ASR failed (%s) — falling back to even spacing", exc)
    if not words:
        phrase = _caption_phrase(find)
        words = align.even_spacing(phrase.split(), min(max(dur - 0.3, 1.5), 6.0))

    # 4) EDL: the composed (pre-sized 1080x1920) clip as one cover clip, a
    # first-frame hook overlay, an on-screen streamer credit, karaoke captions in
    # the lower region, and the clip's ORIGINAL audio kept. Real footage → no AI
    # disclosure, but credit is mandatory.
    hook = (find.get("hook_text") or _hookify(find.get("title")))[:60].strip() or "watch this"
    overlays = [edl_mod.Overlay(kind="text", text=hook, t0=0.0,
                                t1=min(2.5, dur), y_frac=0.09, style="hook")]
    streamer = find.get("streamer")
    if streamer:
        overlays.append(edl_mod.Overlay(
            kind="text", text=f"clip: twitch.tv/{streamer}", t0=0.0, t1=dur,
            y_frac=0.93, style="watermark"))

    captions = edl_mod.Captions(
        mode="karaoke", style="hormozi",
        words=[edl_mod.CaptionWord(w=w, t0=round(a, 3), t1=round(b, 3))
               for (w, a, b) in words if b > a and a < dur])

    edl = edl_mod.EDL(
        version=1,
        ai_generated=False,             # real footage — credit, not AI disclosure
        canvas=edl_mod.Canvas(width=CANVAS_W, height=CANVAS_H, fps=30),
        clips=[edl_mod.Clip(id="clip", src=composed.name, in_=0.0,
                            out=round(dur, 3), order=0, fit="cover", mute=False)],
        overlays=overlays,
        captions=captions,
        audio=[edl_mod.AudioTrack(kind="original", gain_db=0)])
    from ..agents import media as _media

    edl = _media.apply_sfx_to_edl(app, llm, edl, plan=plan, product=product)
    edl_mod.save(edl, edl_mod.edl_path_for(out_dir))

    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    render_mod.render_edl(app, edl, out_dir, final, proxy=False)

    if find.get("id"):
        db_module.execute(
            app.conn, "UPDATE stream_finds SET downloaded_path = ? WHERE id = ?",
            (str(composed), find["id"]))
    db_module.log_activity(
        app.conn, "livestream",
        f"Clipped {find['external_id']} ({streamer}) → {final.name}",
        product_id=product.get("id"), content_id=content_id, level="success")
    return {"media_paths": [str(final)], "media_urls": []}


# --------------------------------------------------------------------------- #
# produce helpers
# --------------------------------------------------------------------------- #
def _chosen_find(app: App, llm: LLM, content_id: int) -> Optional[dict]:
    """The stream_find this content renders: an explicit
    ``strategy_context['stream_find_id']`` if present, else the top radar item."""
    row = store.get_content(app.conn, content_id)
    sctx = db_module.loads(row.get("strategy_context") if row else None, {}) or {}
    fid = sctx.get("stream_find_id")
    if fid:
        r = db_module.query_one(app.conn, "SELECT * FROM stream_finds WHERE id = ?", (fid,))
        if r:
            d = dict(r)
            d["metadata"] = db_module.loads(d.get("metadata"), {}) or {}
            return d
    top = radar(app, llm, limit=1)
    return top[0] if top else None


def _facecam_rect(find: dict) -> tuple[float, float, float, float]:
    """Per-streamer facecam crop rect (fractions of source). Roster override →
    default. (Vision auto-detect is the future upgrade — see INTEGRATION.)"""
    meta = find.get("metadata") if isinstance(find.get("metadata"), dict) else {}
    rect = (meta or {}).get("facecam_rect")
    if isinstance(rect, (list, tuple)) and len(rect) == 4:
        try:
            return tuple(float(x) for x in rect)  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass
    return _FACECAM_DEFAULT


def _caption_phrase(find: dict) -> str:
    for key in ("hook_text", "title"):
        val = (find.get(key) or "").strip()
        if val:
            return val
    return "the clip everyone is talking about"


def _reformat_vertical(src: Path, dst: Path,
                       facecam: tuple[float, float, float, float],
                       gameplay: tuple[float, float, float, float]) -> Path:
    """Compose the stacked 9:16 clip in ONE ffmpeg pass: split the source, crop
    the facecam rect → cover-fill the top band, crop the gameplay rect →
    cover-fill the bottom band, vstack to 1080x1920. Keeps the source audio
    (mapped through) so the EDL's ``kind="original"`` track has real audio.

    Crop rects are fractions of the source, so this is resolution-independent —
    the same graph works on a 1920x1080 real clip or a 1080x1920 mock clip."""
    fx, fy, fw, fh = facecam
    gx, gy, gw, gh = gameplay
    bot_h = CANVAS_H - _TOP_H
    fc = (
        "[0:v]split=2[a][b];"
        f"[a]crop=iw*{fw:g}:ih*{fh:g}:iw*{fx:g}:ih*{fy:g},"
        f"scale={CANVAS_W}:{_TOP_H}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{_TOP_H},setsar=1[top];"
        f"[b]crop=iw*{gw:g}:ih*{gh:g}:iw*{gx:g}:ih*{gy:g},"
        f"scale={CANVAS_W}:{bot_h}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{bot_h},setsar=1[bot];"
        "[top][bot]vstack=inputs=2,format=yuv420p[v]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", fc,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"stacked reformat failed (ffmpeg): {proc.stderr[-800:]}")
    return dst


def _probe_duration(path: Path) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30)
        val = out.stdout.strip()
        return float(val) if val else None
    except Exception:
        return None
