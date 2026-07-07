"""AI animal-story template — serialized "sad cat drama" short-form video.

The viral "AI Cat Stories / Sad Meow Meow Song" format (KnowYourMeme; the
@mpminds April-2024 sound, 50M+ views / 930k+ videos): a recurring named animal
(canonically the orange tabby "Chubby") suffers a melodramatic hardship —
bullying, homelessness, a house fire, betrayal, going to war — across 8-10 short
scenes. The classic form has **no narration**: a sad music bed plus short
present-tense on-screen text per scene carry the story, ending on either a
tearjerker moral or a hard cliffhanger baiting "Part 2". By 2026 it evolved from
still slideshows into fully animated cinematic clips (image-to-video per scene),
so this template renders one animated beat per scene.

Pipeline (mirrors the research report; every step degrades to offline mock):
  1. Story beats — one structured LLM call → a :class:`StoryBoard` of 8-10 beats
     {overlay_text ≤8 words present-tense, image_prompt, motion_prompt,
     duration_s, sfx_hint} + arc_type. Offline → a deterministic sad-cat board.
  2. Character sheet — one consistent animal identity (reuse
     ``characters.ensure_reference_image`` when a character fronts the series,
     else generate a sheet still into the content dir). Every scene still is
     conditioned on it so the SAME cat appears in every beat.
  3. Scene stills — per beat, ``images.generate_image`` conditioned on the sheet
     (real reference-edit consistency; offline composites the subject region so
     the frames visibly share one animal).
  4. Animate — each still → a short clip: image-to-video via fal in real mode
     (``video._fal_clip`` with the still as the first frame), else a subtle
     ffmpeg zoompan push-in from the still (works fully offline).
  5. EDL — beat clips in order with gentle crossfades, ``static_scene`` captions
     (one CaptionEvent per beat carrying overlay_text), a ducked music bed, and
     ``ai_generated=True`` (the renderer burns the AI-disclosure at t=0-5s).
     ``edit.json`` is persisted; ``render_edl`` produces the final MP4.

INTEGRATION (central wiring — orchestrator, NOT this module):
  * ``strategies.register`` / ``PRODUCERS`` wiring is automatic via
    ``mark.templates.__init__.ensure_loaded`` (already lists ``animal_story``).
  * SFX: this module emits a CLEAN EDL and writes beat/scene markers into
    ``storyboard.json`` + ``strategy_context`` (see below). The shared produce
    path (Contract 7) should call ``sfx.apply_sfx`` afterward to place meows /
    rain / rescue stings on the cut points — templates must not place SFX.
  * strategy_context: the orchestrator should persist ``arc_type``,
    ``beats`` (overlay_text list) and ``character_id`` into the content row's
    ``strategy_context`` so the bandit can learn arc_type performance and the
    series/Part-2 machinery can chain episodes. This module writes a sidecar
    ``storyboard.json`` in the media dir for the web editor / audit; it does NOT
    touch the DB (single responsibility, matches ``video.produce_video``).
  * series/Part-2: ``STRATEGY.series_format`` is set, so ``series.py`` treats
    this as an episodic series with the kill rule; cliffhanger episodes should be
    posted "Part 1" with Part 2 scheduled +24h (existing series feature).
  * Compliance: keep the human approval gate ON for YouTube (Feb-2026 AI-slop
    purge targeted templated animal channels); posting sets platform AIGC flags.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..app import App
from ..llm import LLM
from ..media import edl as edl_mod
from ..media import images
from ..media.render import render_edl
from ..strategies import Strategy

log = logging.getLogger("mark.templates.animal_story")

FPS = 30
_MIN_BEATS, _MAX_BEATS = 8, 10
_DEFAULT_BEAT_SECONDS = 4.5
_CROSSFADE = 0.4
# Arc types the story can take — surfaced as an angle so the bandit can learn
# which arcs perform (research: rescue / cinderella glow-up / drama / war /
# betrayal are the documented sub-genres).
ARC_TYPES = ["rescue", "cinderella", "drama", "war", "betrayal"]

_DEFAULT_VISUAL = (
    "a small ginger tabby kitten named Whiskers with huge watery green eyes, "
    "one slightly torn ear and soft orange fur, cute Pixar-realistic hybrid "
    "render style, never photoreal — the SAME cat in every scene"
)


# --------------------------------------------------------------------------- #
# Storyboard schema (structured LLM output; local to the template)
# --------------------------------------------------------------------------- #
class Beat(BaseModel):
    """One scene of the story."""

    overlay_text: str                     # ≤8 words, present tense, names the animal
    image_prompt: str                     # scene ONLY — identity comes from the sheet
    motion_prompt: str = "slow cinematic push-in"  # one performance beat
    duration_s: float = _DEFAULT_BEAT_SECONDS
    sfx_hint: str = ""                    # advisory for the shared SFX engine


class StoryBoard(BaseModel):
    """8-10 beats of serialized sad-animal drama + the metadata the series and
    bandit machinery learn from."""

    title: str = "Whiskers"
    arc_type: str = "rescue"              # ARC_TYPES
    beats: list[Beat] = Field(default_factory=list)
    twist_beat: int = 6                   # 1-based index of the outrageous turn
    cliffhanger: bool = True              # ends mid-action, baiting Part 2
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Strategy
# --------------------------------------------------------------------------- #
STRATEGY = Strategy(
    id="animal-story",
    name="AI animal story (sad-cat serialized drama)",
    description=(
        "Serialized emotional animal drama: a recurring named animal suffers a "
        "melodramatic hardship-then-hope arc across 8-10 short animated scenes, "
        "carried by present-tense on-screen text + a sad music bed (no narration), "
        "ending on a tearjerker moral or a hard 'Part 2' cliffhanger. The format "
        "that made the @mpminds 'sad meow' sound (50M+ views); differentiation in "
        "2026 comes from a recurring named character + serialized cliffhangers, not "
        "the base format."
    ),
    emotional_target="hope",
    platforms={
        "tiktok": "8-10 scenes, 30-45s, static per-scene text, hard cliffhanger → Part 2",
        "instagram": "same as Reels; caption front-loads 'Part 1', pin Part 2 timing",
        "youtube": "Shorts re-render; KEEP human approval on (AI-slop purge risk)",
    },
    content_types=["video"],
    humor_level="none",
    uses_character=True,
    series_format=(
        "One serialized animal (recurring named character) per series. Every "
        "episode is one chapter: beat 1 is the emotional gut-punch (distressed "
        "cute animal in the first 1-3s), the arc heightens, beat ~6-7 is the "
        "outrageous twist, the final beat resolves OR cliffhangs mid-action for "
        "Part 2. Reference at least one prior chapter's loss when serializing."
    ),
    strategist_brief=(
        "Pick ONE arc_type (rescue | cinderella | drama | war | betrayal) as the "
        "angle and one hardship. Beat 1 must be an emotionally loaded first shot. "
        "Prefer a two-parter cliffhanger for retention; the bandit learns which "
        "arc_type converts."
    ),
    writer_brief=(
        "Per-scene overlay text ONLY: ≤8 words, present tense, name the animal "
        "('Whiskers lost everything in the storm'). No narration script. Keep "
        "distress melodramatic, never graphic/abusive. Caption frames 'Part 1' "
        "when it cliffhangs; hashtags include #aicat #catstory #sadcatstory."
    ),
    media_brief=(
        "Character-sheet-locked identity: the SAME animal in every beat via "
        "reference-image conditioning. Scene prompts describe the SCENE only "
        "(rain, alley, fire) — the animal's look comes from the sheet. One "
        "performance beat per clip (5s holds consistency better than 15s). "
        "Sad-piano bed at -6dB; original AI music only (never bake the copyrighted "
        "'sad meow' cover into the file)."
    ),
    example_sketches=[
        "TikTok: on-screen 'Whiskers waits in the rain' → 'nobody stops' → "
        "'a hand reaches down' → 'but it belongs to Greg' → 'Part 2 tomorrow'",
        "Rescue arc: abandoned kitten → storm → limps to an empty alley → a gentle "
        "stranger → warm home → 'Whiskers is finally safe' (moral resolution)",
    ],
    mix_weight=0.12,
    requires_product=False,   # entertainment format — the story itself is the draw
)


# --------------------------------------------------------------------------- #
# Produce
# --------------------------------------------------------------------------- #
def produce(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
            out_dir: Path, character: Optional[dict] = None) -> dict:
    """Render one serialized animal-story video. Returns ``{"media_paths": [...]}``
    (same shape as ``video.produce_video``). Runs fully in mock mode."""
    import shutil

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for animal-story rendering")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = product["id"]

    board = _storyboard(app, llm, product, content_id, plan, draft)

    # 1) One consistent animal identity for the whole story.
    sheet_path, visual_desc = _character_sheet(
        app, llm, product, content_id, out_dir, character)

    # 2) Per beat: scene still (identity-conditioned) → animated clip.
    clips: list[edl_mod.Clip] = []
    for i, beat in enumerate(board.beats):
        still = _scene_still(app, llm, out_dir, content_id, pid, i, beat,
                             sheet_path, visual_desc, character)
        clip_path = out_dir / f"{content_id}_beat{i}.mp4"
        _animate_beat(app, beat, still, clip_path, content_id, pid, index=i)
        transition = (edl_mod.Transition(type="crossfade", duration=_CROSSFADE)
                      if i < len(board.beats) - 1 else None)
        clips.append(edl_mod.Clip(
            id=f"beat{i}", src=clip_path.name, **{"in": 0.0},
            out=float(beat.duration_s), order=i, fit="cover", mute=True,
            transition=transition))

    # 3) Assemble the EDL: static per-scene captions + a ducked sad-music bed.
    edl = _build_edl(app, out_dir, content_id, board, clips)
    from ..agents import media as _media

    edl = _media.apply_sfx_to_edl(app, llm, edl, plan=plan, product=product)
    edl_mod.save(edl, edl_mod.edl_path_for(out_dir))
    _write_sidecar(out_dir, board, character)  # editor/audit + INTEGRATION marker

    # 4) Render final (captions burned, AI-disclosure invariant applied).
    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    render_edl(app, edl, out_dir, final, proxy=False)
    log.info("animal-story %s: %d beats, arc=%s → %s",
             content_id, len(board.beats), board.arc_type, final.name)
    return {"media_paths": [str(final)]}


# --------------------------------------------------------------------------- #
# Storyboard generation
# --------------------------------------------------------------------------- #
def _storyboard(app: App, llm: LLM, product: dict, content_id: int, plan,
                draft) -> StoryBoard:
    arc = _pick_arc(plan)
    system = (
        "You script the viral 'AI sad cat story' short-form format for a recurring "
        "named animal. Output a StoryBoard of 8-10 beats. CONVENTIONS (strict):\n"
        "- Beat 1 is the emotional gut-punch: a distressed cute animal, first shot.\n"
        "- The arc heightens; beat ~6-7 is the outrageous twist.\n"
        "- The final beat resolves with a moral OR cliffhangs mid-action for Part 2.\n"
        "- overlay_text: <=8 words, PRESENT TENSE, names the animal, no hashtags.\n"
        "- image_prompt: describe ONLY the scene/environment (rain, alley, fire) — "
        "NOT the animal's appearance (identity is locked by a character sheet).\n"
        "- motion_prompt: ONE performance beat ('the cat slowly looks up, rain "
        "falling, slow push-in').\n"
        "- duration_s: 4-5. Keep distress melodramatic, never graphic or abusive.\n"
        f"- arc_type: {arc}."
    )
    user = (
        f"Product/brand context (for tone only, do not advertise): {product.get('name')}"
        f" — {product.get('description', '')[:300]}\n"
        f"Angle: {getattr(plan, 'angle', '') or arc}. "
        f"Topic: {getattr(plan, 'topic', '') or 'a sad animal rescue'}.\n"
        "Write the serialized episode now."
    )
    board = llm.parse(
        system, user, StoryBoard,
        model=app.settings.llm.text_model,
        mock_factory=lambda: _mock_storyboard(arc, plan),
        content_id=content_id, product_id=product["id"],
    )
    return _sanitize_board(board, arc, plan)


def _pick_arc(plan) -> str:
    angle = (getattr(plan, "angle", "") or "").lower()
    for arc in ARC_TYPES:
        if arc in angle:
            return arc
    # deterministic spread across arcs by content topic hash
    topic = (getattr(plan, "topic", "") or "").strip()
    return ARC_TYPES[sum(map(ord, topic)) % len(ARC_TYPES)] if topic else "rescue"


def _sanitize_board(board: StoryBoard, arc: str, plan) -> StoryBoard:
    """Enforce the 8-10 beat contract even if the model over/under-produces."""
    beats = [b for b in board.beats if (b.overlay_text or "").strip()]
    if len(beats) < _MIN_BEATS:
        filler = _mock_storyboard(arc, plan).beats
        beats = (beats + filler)[:_MAX_BEATS]
        if len(beats) < _MIN_BEATS:
            beats = filler
    beats = beats[:_MAX_BEATS]
    for b in beats:
        b.overlay_text = " ".join(b.overlay_text.split()[:8])
        b.duration_s = float(min(max(b.duration_s or _DEFAULT_BEAT_SECONDS, 3.0), 6.0))
        if not (b.image_prompt or "").strip():
            b.image_prompt = "a cinematic emotional scene, soft rain, moody light"
        if not (b.motion_prompt or "").strip():
            b.motion_prompt = "slow cinematic push-in"
    board.beats = beats
    if board.arc_type not in ARC_TYPES:
        board.arc_type = arc
    return board


def _mock_storyboard(arc: str, plan) -> StoryBoard:
    """Deterministic offline sad-cat board (9 beats, twist at 7, cliffhanger)."""
    beats = [
        Beat(overlay_text="Whiskers shivers alone in the rain",
             image_prompt="a rain-soaked empty city street at night, glowing puddles, "
                          "cold blue streetlight, cinematic",
             motion_prompt="slow push-in, heavy rain falling, subtle camera drift",
             sfx_hint="rain, distant thunder"),
        Beat(overlay_text="Nobody stops to help him",
             image_prompt="blurry umbrellas and shoes hurrying past on a wet sidewalk, "
                          "shallow depth of field",
             motion_prompt="feet rush past, slow pan across the puddle",
             sfx_hint="footsteps, rain"),
        Beat(overlay_text="A bigger cat steals his last food",
             image_prompt="a knocked-over paper food container spilling into a gutter, "
                          "dim alley light",
             motion_prompt="the container tips over, slow tilt down",
             sfx_hint="clatter, hiss"),
        Beat(overlay_text="Whiskers limps into an empty alley",
             image_prompt="a narrow brick alley at night, wet cobblestones, one flickering "
                          "lamp, fog",
             motion_prompt="slow forward dolly down the alley, fog drifting",
             sfx_hint="dripping water"),
        Beat(overlay_text="He remembers his warm old home",
             image_prompt="a soft golden memory of a cozy living room, fireplace glow, "
                          "warm bokeh, dreamlike",
             motion_prompt="gentle zoom into the warm glow, soft focus",
             sfx_hint="soft fireplace crackle"),
        Beat(overlay_text="But that home is gone now",
             image_prompt="the same living room dark and empty, dust sheets on the "
                          "furniture, cold light",
             motion_prompt="slow reverse dolly, the warmth fades to grey",
             sfx_hint="wind, silence"),
        Beat(overlay_text="Then a gentle hand reaches through the rain",
             image_prompt="a human hand reaching down into frame under heavy rain, warm "
                          "backlight behind, cinematic",
             motion_prompt="the hand lowers into frame, rain slows, light warms",
             sfx_hint="rain softening, heartbeat"),
        Beat(overlay_text="But the hand belongs to Greg",
             image_prompt="a tall shadowy silhouette in a doorway, harsh backlight, "
                          "ominous, rain behind",
             motion_prompt="slow push toward the silhouette, thunder flash",
             sfx_hint="thunder crack, sting"),
        Beat(overlay_text="To be continued... Part 2 tomorrow",
             image_prompt="a car's tail-lights disappearing down a rainy road at night, "
                          "empty street, melancholic",
             motion_prompt="the lights recede into the dark, slow fade",
             sfx_hint="car engine fading, sad piano"),
    ]
    topic = (getattr(plan, "topic", "") or "").strip()
    title = "Whiskers" if not topic else topic.split()[0].title()
    return StoryBoard(
        title=title, arc_type=arc if arc in ARC_TYPES else "rescue",
        beats=beats, twist_beat=8, cliffhanger=True,
        caption=("Whiskers lost everything in the storm. Part 1 — "
                 "Part 2 tomorrow. (AI-generated)"),
        hashtags=["aicat", "catstory", "sadcatstory", "aianimals", "part1"],
    )


# --------------------------------------------------------------------------- #
# Character identity + scene stills
# --------------------------------------------------------------------------- #
def _character_sheet(app: App, llm: LLM, product: dict, content_id: int,
                     out_dir: Path, character: Optional[dict]) -> tuple[Path, str]:
    """Return (reference_sheet_path, visual_desc). Reuse a passed character's
    canonical sheet; otherwise generate a one-off sheet for this story."""
    if character:
        from .. import characters as characters_mod

        try:
            sheet = characters_mod.ensure_reference_image(app, llm, character)
            return Path(sheet), (character.get("visual_desc") or _DEFAULT_VISUAL)
        except Exception as exc:  # never let identity setup crash the render
            log.warning("character sheet failed (%s) — generating a one-off sheet", exc)

    visual_desc = _DEFAULT_VISUAL
    sheet = out_dir / f"{content_id}_sheet.png"
    prompt = (f"Character reference sheet: {visual_desc}. Single subject, "
              "front-facing medium shot, sad expression, soft studio light, plain "
              "light-gray background, no text, no watermark.")
    images.generate_image(app, llm, prompt, sheet, size="1024x1536",
                          content_id=content_id, product_id=product["id"])
    return sheet, visual_desc


def _scene_still(app: App, llm: LLM, out_dir: Path, content_id: int, pid: str,
                 index: int, beat: Beat, sheet_path: Path, visual_desc: str,
                 character: Optional[dict]) -> Path:
    """Generate one identity-conditioned scene still for a beat."""
    if character:
        from .. import characters as characters_mod

        scene = characters_mod.scene_prompt(character, beat.image_prompt)
    else:
        scene = (f"{visual_desc}. Scene: {beat.image_prompt}. {beat.motion_prompt}. "
                 "Portrait 9:16, cinematic, emotional lighting, no text.")
    still = out_dir / f"{content_id}_beat{index}_still.png"
    images.generate_image(app, llm, scene, still, size="1024x1536",
                          reference_images=[sheet_path] if sheet_path else None,
                          content_id=content_id, product_id=pid)
    # Offline the model can't actually place the animal (mock stills are
    # text-on-gradient placeholders), so mute the placeholder text with a
    # cinematic scrim and draw a deterministic cat emblem into a consistent
    # region — the mock render then reads as ONE recognizable cat across every
    # scene. Real reference-edit generation does this for real.
    if app.is_mock("openai"):
        try:
            _composite_subject(still, Path(sheet_path) if sheet_path else None)
        except Exception as exc:
            log.debug("subject composite skipped: %s", exc)
    return still


def _composite_subject(still_path: Path, sheet_path: Optional[Path]) -> None:
    """Mock-only visual aid: darken the placeholder scene, then draw the SAME
    simple cat emblem in the SAME spot in every scene so the offline story reads
    as one consistent animal subject. Tint is sampled from the character sheet so
    the emblem is tied to that identity."""
    from PIL import Image, ImageDraw

    scene = Image.open(still_path).convert("RGBA")
    sw, sh = scene.size

    # 1) Cinematic scrim — mute the gradient's placeholder prompt text so the
    #    subject and caption read cleanly.
    scrim = Image.new("RGBA", scene.size, (8, 10, 18, 140))
    scene = Image.alpha_composite(scene, scrim)
    draw = ImageDraw.Draw(scene)

    # 2) Ginger tint from the sheet (deterministic identity anchor); default to a
    #    warm ginger tabby.
    tint = (222, 138, 74)
    if sheet_path and Path(sheet_path).exists():
        try:
            avg = Image.open(sheet_path).convert("RGB").resize((1, 1)).getpixel((0, 0))
            tint = tuple(min(255, int(v * 0.6 + w * 0.4))
                         for v, w in zip(avg, (222, 138, 74)))  # bias toward ginger
        except Exception:
            pass

    # 3) A simple, identical-every-scene cat face in a fixed subject region.
    #    Lower third — clears the static_scene caption band (~0.50 height).
    cx, cy = sw // 2, int(sh * 0.72)
    r = int(sw * 0.17)                      # head radius
    ear = int(r * 0.7)
    fur, dark = tint, tuple(max(0, c - 70) for c in tint)
    # Ears (triangles).
    draw.polygon([(cx - r, cy - int(r * 0.5)), (cx - r + ear, cy - r - ear),
                  (cx - int(r * 0.15), cy - r)], fill=fur)
    draw.polygon([(cx + r, cy - int(r * 0.5)), (cx + r - ear, cy - r - ear),
                  (cx + int(r * 0.15), cy - r)], fill=fur)
    # Head + muzzle.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fur, outline=dark, width=4)
    # Eyes (big watery green — the character's signature).
    eye_dx, eye_dy, eye_r = int(r * 0.42), int(r * 0.12), int(r * 0.22)
    for sx in (-1, 1):
        ex = cx + sx * eye_dx
        draw.ellipse([ex - eye_r, cy - eye_dy - eye_r, ex + eye_r, cy - eye_dy + eye_r],
                     fill=(70, 170, 120))
        draw.ellipse([ex - eye_r // 3, cy - eye_dy - eye_r // 3,
                      ex + eye_r // 3, cy - eye_dy + eye_r // 3], fill=(15, 15, 20))
    # Nose + whiskers.
    ny = cy + int(r * 0.18)
    draw.polygon([(cx - r // 10, ny), (cx + r // 10, ny), (cx, ny + r // 8)],
                 fill=(210, 120, 130))
    for wy in (ny - r // 12, ny + r // 12):
        draw.line([(cx - r // 6, wy), (cx - r, wy - r // 12)], fill=(235, 235, 235), width=3)
        draw.line([(cx + r // 6, wy), (cx + r, wy - r // 12)], fill=(235, 235, 235), width=3)

    scene.convert("RGB").save(still_path)


# --------------------------------------------------------------------------- #
# Animation (image-to-video real / ffmpeg zoompan offline)
# --------------------------------------------------------------------------- #
def _animate_beat(app: App, beat: Beat, still: Path, out_path: Path,
                  content_id: int, pid: str, *, index: int) -> Path:
    """Animate one still to a short clip. Real: fal image-to-video (still is the
    first frame → identity locked). Offline/failure: a subtle ffmpeg zoompan
    push-in from the still."""
    seconds = float(beat.duration_s)
    if not app.is_mock("fal"):
        try:
            from ..media import video as video_mod

            return video_mod._fal_clip(
                app, beat.motion_prompt, int(round(seconds)), out_path,
                content_id, pid, first_frame=still)
        except Exception as exc:
            log.warning("fal i2v failed for beat %d (%s) — zoompan fallback", index, exc)
    return _zoompan_clip(still, seconds, out_path, index)


def _zoompan_clip(still: Path, seconds: float, out_path: Path, index: int) -> Path:
    """Subtle motion clip from a still: pre-upscale (zoompan headroom) then a slow
    push-in. Alternating start scale per beat adds gentle variety. Fully offline."""
    frames = max(int(round(seconds * FPS)), 1)
    # Even beats push in, odd beats ease out — small variation, no jitter.
    if index % 2 == 0:
        z = "min(zoom+0.0011,1.20)"
    else:
        z = "if(lte(on,1),1.20,max(zoom-0.0010,1.03))"
    vf = (
        "scale=1620:2880:force_original_aspect_ratio=increase,crop=1620:2880,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1920:fps={FPS},setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", still.name, "-t", f"{seconds:.3f}",
        "-r", str(FPS), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-an", out_path.name,
    ]
    proc = subprocess.run(cmd, cwd=str(out_path.parent), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"zoompan clip failed: {proc.stderr[-500:]}")
    return out_path


# --------------------------------------------------------------------------- #
# EDL assembly
# --------------------------------------------------------------------------- #
def _build_edl(app: App, out_dir: Path, content_id: int, board: StoryBoard,
               clips: list[edl_mod.Clip]) -> edl_mod.EDL:
    durs = [edl_mod.clip_seconds(c) for c in clips]
    n = len(clips)

    # A throwaway EDL to reuse the renderer's exact transition/duration math so
    # caption windows land on the folded (crossfaded) timeline.
    probe = edl_mod.EDL(clips=[c.model_copy() for c in clips], ai_generated=True)
    trans = edl_mod.transition_seconds(probe)
    total = edl_mod.visual_duration(probe)

    starts, acc = [], 0.0
    for i in range(n):
        starts.append(acc)
        acc += durs[i] - (trans[i] if i < n - 1 else 0.0)

    events = []
    for i, beat in enumerate(board.beats[:n]):
        t0 = starts[i]
        t1 = starts[i + 1] if i < n - 1 else total
        if t1 > t0:
            events.append(edl_mod.CaptionEvent(text=beat.overlay_text, t0=t0, t1=t1))

    captions = edl_mod.Captions(mode="static_scene", style="clean", events=events)

    # Sad ambient music bed (mock: a soft synthesized minor chord; real path can
    # swap in Stable Audio). Ducking is a no-op here (no voiceover) but declared
    # so a narrated variant Just Works.
    music_path = _ambient_music(out_dir, content_id, total)
    audio = [edl_mod.AudioTrack(src=music_path.name, kind="music",
                                gain_db=-6.0, duck_db=-12.0)]

    return edl_mod.EDL(
        version=1, ai_generated=True,
        canvas=edl_mod.Canvas(width=1080, height=1920, fps=FPS),
        clips=clips, captions=captions, audio=audio,
    )


def _ambient_music(out_dir: Path, content_id: int, seconds: float) -> Path:
    """Generate a soft sad-ambient bed (two low sine tones, faded). Real, playable
    audio so the mux/ducking path is exercised offline."""
    out_path = out_dir / f"{content_id}_music.wav"
    dur = max(seconds, 1.0)
    fade_out = max(dur - 1.0, 0.0)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur:.3f}",
        "-f", "lavfi", "-i", f"sine=frequency=277.18:duration={dur:.3f}",
        "-filter_complex",
        ("[0][1]amix=inputs=2,volume=0.16,"
         f"afade=t=in:d=1,afade=t=out:st={fade_out:.3f}:d=1[a]"),
        "-map", "[a]", "-c:a", "pcm_s16le", out_path.name,
    ]
    proc = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        # Never fail a render over the music bed — fall back to silence.
        log.warning("ambient music synth failed — silent bed: %s", proc.stderr[-300:])
        from ..media.tts import _silent_wav

        _silent_wav(out_path, dur)
    return out_path


def _write_sidecar(out_dir: Path, board: StoryBoard, character: Optional[dict]) -> None:
    """Persist the storyboard next to the EDL for the web editor / audit and as
    the INTEGRATION handoff the orchestrator lifts into strategy_context."""
    import json

    payload = {
        "arc_type": board.arc_type,
        "title": board.title,
        "twist_beat": board.twist_beat,
        "cliffhanger": board.cliffhanger,
        "caption": board.caption,
        "hashtags": board.hashtags,
        "character_id": (character or {}).get("id"),
        "beats": [b.model_dump() for b in board.beats],
    }
    (out_dir / "storyboard.json").write_text(json.dumps(payload, indent=2))
