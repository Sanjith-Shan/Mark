"""Fake-movie recap template — the "this man..." narrated recap format.

Contract 5 of the content-templates build (docs/design/CONTENT-TEMPLATES-BUILD.md),
grounded in the movie-recap research synthesis
(``scratchpad/report-Movie-recap-content-format-and-automatio.json``).

The recap genre is a faceless narrator retelling a film's plot in third-person
present tense ("this man wakes up to 400 unanswered applications...") over a
sequence of clips — one clip per plot beat — with word-level karaoke captions.
The hard problem of the genre is RIGHTS: real footage triggers Content ID /
DMCA and is a legal non-starter for an ad. So this template ships the
CLEAN-SOURCE variant the research recommends as the default for autonomous
posting:

  * The LLM INVENTS a generic-genre "movie" (a heist thriller, a survival drama)
    as 6-10 beats. It is never a real film — that avoids both copyright and
    trademark/likeness exposure (see risks in the report).
  * Each beat's VISUAL is generated (fal text-to-video / image-to-video; a
    Pillow-still placeholder clip in mock mode) — every frame is content we made.
  * NARRATION IS THE MASTER CLOCK. We synthesize the narration per beat, measure
    each beat's audio duration, and fit that beat's VIDEO to the narration length
    (trim / mild speed / loop, all inside the EDL clip's in/out/speed with the
    0.5-2.0 speed clamp). The audio is never stretched — the classic
    AI-Movie-Shorts pattern (narration natural, video bends).
  * The final ~15% pivots the narration into the product twist
    ("...but he never needed the heist. He needed {product}."). Landing it any
    earlier reads as an ad from second one.

A second, opt-in capability — :func:`clip_intelligence` — is the reusable
"clipping skill": given a USER-SUPPLIED LOCAL video file (the founder's own demo,
a public-domain film, owned/licensed footage — never an auto-downloaded
copyrighted movie), it splits the file into shots and returns a keyframe per
shot. It degrades gracefully: PySceneDetect when importable, otherwise ffmpeg's
``select='gt(scene,threshold)'`` scene filter. Recap's owned-footage mode and
later templates can build on it.

Assembly goes through the shared EDL pipeline: this module emits ONE
``edit.json`` (Contract 1) and calls :func:`mark.media.render.render_edl`
(Contract 3). Captions come from :mod:`mark.media.align`; audio from
:mod:`mark.media.tts`. Everything runs under ``App.is_mock`` with no API keys.

INTEGRATION
-----------
Central wiring is the orchestrator's job (this module must not edit
``strategies.py``, ``agents/media.py``, ``db.py``, ``config.py`` or the
scheduler). What the rest of the system needs to know:

* Dispatch: already generic. ``templates/__init__.py`` lists ``"recap"`` in
  ``_MODULES`` and ``agents/media.produce_media`` routes ``strategy.id ==
  "fake-movie-recap"`` through ``PRODUCERS`` — no change needed once this file
  imports cleanly.
* Product config: to let a product use this strategy, its video platforms
  (``tiktok`` / ``instagram`` / ``youtube`` / ``x``) must be enabled and, if the
  product uses a ``strategies`` allowlist, ``"fake-movie-recap"`` must be in it.
  No new config keys are required.
* SFX/music: this template intentionally emits a CLEAN EDL (voiceover only, hard
  cuts). The shared produce path may run ``media/sfx.apply_sfx`` afterward
  (Contract 7) to add transition whooshes on the beat cuts — the beat cut points
  are exactly the clip boundaries in the EDL, so no extra markers are needed.
* Owned-footage recap (:func:`clip_intelligence`) is a helper only; no autonomous
  path calls it. A future web/CLI "recap my clip" action would wire it in.
* No DB migrations, no scheduler hooks (recap is not a discovery template).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..app import App
from ..llm import LLM
from ..media import edl as edl_mod
from ..media import images, tts
from ..media.align import word_timestamps
from ..media.render import render_edl
from ..strategies import Strategy

log = logging.getLogger("mark.templates.recap")

WIDTH, HEIGHT, FPS = 1080, 1920, 30
_MIN_BEATS, _MAX_BEATS = 6, 10
_FAL_MIN_SEC, _FAL_MAX_SEC = 3, 10  # fal duration enum range the models accept


# --------------------------------------------------------------------------- #
# Strategy
# --------------------------------------------------------------------------- #
STRATEGY = Strategy(
    id="fake-movie-recap",
    name="Fake-movie recap",
    description=(
        "A faceless narrator recaps a MADE-UP genre movie in third-person present "
        "tense ('this man wakes up to 400 unanswered applications') over AI-generated "
        "per-beat visuals with karaoke captions — the movie-recap aesthetic with zero "
        "copyright/Content-ID exposure because every frame is generated. 60-90s, 6-10 "
        "beats; a hook in sentence one; the final ~15% derails the narration into the "
        "product as the twist ('...but he never needed the heist. He needed {product}.'). "
        "Rides an established, high-retention format the audience already knows how to watch."
    ),
    emotional_target="recognition",
    platforms={
        "tiktok": "vertical recap, karaoke captions mandatory; part-split at beat "
                  "boundaries when it runs long (each part ends on a cliffhanger)",
        "instagram": "same, one notch more polished; Reel; CTA aims at sends/saves",
        "youtube": "Shorts cut (<60s) or the full recap; keep the twist for the end",
        "x": "post the vertical video natively; first line of the caption is the hook",
    },
    content_types=["video"],
    humor_level="light",   # deadpan documentary-narrator delivery
    strategist_brief=(
        "Choose a GENERIC film genre whose tropes map onto the product's core pain "
        "(heist = beating a rigged system, survival = grinding through the boring work, "
        "spy thriller = doing it all in secret). Never reference a real film, title, or "
        "character — generic-genre only. The topic is the fake movie's premise; the angle "
        "is the pain the twist ultimately resolves with the product."
    ),
    writer_brief=(
        "Write a RECAP, not a plot summary: third-person present tense, characters "
        "introduced generically ('this man', 'this woman') and never named, one concrete "
        "action per sentence, a scroll-stopping hook in sentence one. 6-10 beats. Keep the "
        "product entirely out of the first ~80%. The final 1-2 beats are the twist: the "
        "narration pivots so the whole 'movie' turns out to be about the product "
        "('...but he never needed the heist. He needed {product}.'). Land it flat and "
        "deadpan — it should feel like a rug-pull, not a sponsor read."
    ),
    media_brief=(
        "Per-beat cinematic visual prompts, consistent style descriptor repeated in every "
        "beat (same color grade, same lens language) so the 'movie' looks like one film. "
        "Deadpan documentary-narrator voiceover is the master clock."
    ),
    example_sketches=[
        "Heist thriller: 'This man has one shot to break into the most secure building in "
        "the city.' … final beat: '…but he never needed the vault. He needed {product}.'",
        "Survival drama: 'Stranded, with 400 job applications and no signal, this woman "
        "does the unthinkable.' … twist: 'She automated all of it. That's the whole movie.'",
    ],
    mix_weight=0.12,
)


# --------------------------------------------------------------------------- #
# Story schema (kept local — templates must not edit schemas.py)
# --------------------------------------------------------------------------- #
class RecapBeat(BaseModel):
    narration_sentence: str            # third-person present tense, one action
    visual_prompt: str                 # cinematic prompt for this beat's clip
    is_twist: bool = False             # part of the final product pivot


class RecapStory(BaseModel):
    title: str                         # the fake movie's title (generic, not a real film)
    genre: str                         # "heist thriller", "survival drama", ...
    logline: str = ""
    beats: list[RecapBeat] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Story generation
# --------------------------------------------------------------------------- #
_STORY_SYSTEM = (
    "You are a short-form movie-recap writer for a product-marketing channel. You invent "
    "a FAKE, generic-genre movie (never a real film, title, character, or recognizable "
    "scene) and recap it in the classic faceless-narrator style so the video rides a "
    "format the audience already knows how to watch.\n\n"
    "PRODUCT: {name} — {description}\n"
    "AUDIENCE: {audience}\n"
    "GENRE HINT / TOPIC: {topic}\n"
    "ANGLE (the pain the twist resolves): {angle}\n\n"
    "Rules:\n"
    "- Third-person PRESENT tense. Introduce people generically ('this man', 'this woman') "
    "and never name them.\n"
    "- One concrete action per sentence. Sentence one is a scroll-stopping HOOK.\n"
    "- {min_beats}-{max_beats} beats total, each 10-25 words.\n"
    "- The product appears in NONE of the beats until the final 1-2, which are the TWIST: "
    "the narration derails so the whole 'movie' turns out to be about {name} "
    "(e.g. '...but he never needed the heist. He needed {name}.'). Mark those beats "
    "is_twist=true.\n"
    "- Each beat also gets a cinematic visual_prompt; repeat a consistent style descriptor "
    "in every prompt so the movie looks like one film.\n"
    "- No banned slop ('game-changer', 'revolutionary', 'in today's digital age')."
)


def generate_story(app: App, llm: LLM, product: dict, plan, draft) -> RecapStory:
    """Invent the fake movie as ordered beats. Offline → a deterministic sample
    recap that already ends in a product twist, so the pipeline is fully
    exercised without any API key."""
    system = _STORY_SYSTEM.format(
        name=product["name"],
        description=(product.get("description") or "").strip()[:400],
        audience=(product.get("target_audience") or "").strip()[:200],
        topic=getattr(plan, "topic", "") or "a genre movie",
        angle=getattr(plan, "angle", "") or "",
        min_beats=_MIN_BEATS, max_beats=_MAX_BEATS,
    )
    user = (
        "Write the recap now as structured JSON: title, genre, logline, and the ordered "
        "beats. Remember: hook first, product hidden until the twist, generic genre only."
    )
    story = llm.parse(
        system, user, RecapStory,
        model=app.settings.llm.text_model,
        temperature=0.9,
        product_id=product["id"], content_id=getattr(plan, "content_id", None),
        mock_factory=lambda: _mock_story(product, plan, draft),
    )
    return _sanitize_story(story, product, plan, draft)


def _sanitize_story(story: RecapStory, product: dict, plan, draft) -> RecapStory:
    """Guarantee the invariants the rest of the pipeline relies on: enough beats,
    a bounded count, and a product twist as the final beat (even if a live model
    forgot to flag one)."""
    beats = [b for b in story.beats if (b.narration_sentence or "").strip()]
    if len(beats) < _MIN_BEATS:
        beats = _mock_story(product, plan, draft).beats
    beats = beats[:_MAX_BEATS]
    if not any(b.is_twist for b in beats):
        beats[-1].is_twist = True
    # The last beat must name the product — it's the whole point of the twist.
    name = product["name"]
    last = beats[-1]
    if name.lower() not in (last.narration_sentence or "").lower():
        last.narration_sentence = (
            last.narration_sentence.rstrip(". ") +
            f". He never needed any of it — he needed {name}."
        )
    return RecapStory(title=story.title or f"THE {product['name'].upper()} JOB",
                      genre=story.genre or "heist thriller",
                      logline=story.logline, beats=beats)


def _mock_story(product: dict, plan, draft) -> RecapStory:
    """Deterministic offline recap — a heist thriller that turns out to be about
    the product. Present tense, generic characters, twist in the final beat."""
    name = product["name"]
    style = "moody neo-noir color grade, anamorphic lens, cinematic 35mm, high contrast"
    beats = [
        RecapBeat(
            narration_sentence="This man wakes up to four hundred unanswered applications "
                               "and one impossible plan.",
            visual_prompt=f"A tired man at a cluttered desk lit by a single monitor at 3am, "
                          f"walls covered in sticky notes, {style}"),
        RecapBeat(
            narration_sentence="Everyone told him the system was rigged, so tonight he "
                               "decides to break it wide open.",
            visual_prompt=f"The same man studying a giant corkboard of red string and photos, "
                          f"determined stare, {style}"),
        RecapBeat(
            narration_sentence="He assembles a crew of misfits, each one burned by the same "
                               "faceless machine.",
            visual_prompt=f"Four silhouetted figures meeting in a dim warehouse, rain on the "
                          f"windows, {style}"),
        RecapBeat(
            narration_sentence="They study the tower for weeks, mapping every gate, every "
                               "guard, every locked door.",
            visual_prompt=f"Blueprints spread across a table, hands pointing at a glowing "
                          f"schematic of a skyscraper, {style}"),
        RecapBeat(
            narration_sentence="On the night of the job, alarms scream and the whole plan "
                               "starts falling apart around them.",
            visual_prompt=f"Red emergency lights flooding a corridor, a figure sprinting, "
                          f"sparks and smoke, {style}"),
        RecapBeat(
            narration_sentence="Cornered on the roof with no way down, he finally understands "
                               "what he was really after.",
            visual_prompt=f"A man standing at the edge of a rooftop at dawn, city skyline "
                          f"behind him, wind in his coat, {style}"),
        RecapBeat(
            narration_sentence=f"But he never needed the heist. He never needed the crew. "
                               f"He needed {name}.",
            visual_prompt=f"The man calmly closing a laptop showing {name}, faint smile, "
                          f"morning light, {style}",
            is_twist=True),
    ]
    return RecapStory(
        title=f"THE {name.upper()} JOB",
        genre="heist thriller",
        logline=f"One man, four hundred applications, and the only way out is {name}.",
        beats=beats,
    )


# --------------------------------------------------------------------------- #
# produce — the autonomous clean-source pipeline
# --------------------------------------------------------------------------- #
def produce(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
            out_dir: Path, character: Optional[dict] = None) -> dict:
    """Generate a fake-movie recap and return ``{"media_paths": [mp4]}``.

    Pipeline: (1) invent the story as beats; (2) narrate each beat (the master
    clock); (3) generate each beat's visual clip and fit it to its narration
    length; (4) emit one EDL with beat clips in order, the concatenated
    voiceover, and karaoke captions from forced alignment; (5) render.
    """
    if not _has_ffmpeg():
        raise RuntimeError("ffmpeg not found — required for recap assembly")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    story = generate_story(app, llm, product, plan, draft)
    log.info("recap %s: %d beats (%s)", content_id, len(story.beats), story.genre)

    voice = (character or {}).get("voice") or None
    instructions = ("Calm, dry, deadpan documentary narrator — the classic movie-recap "
                    "voice. Steady pace. Take a small beat before the final twist line and "
                    "deliver it completely flat.")

    beats_meta: list[dict] = []   # per beat: audio path, duration, words (offset), clip src
    beat_audio_paths: list[Path] = []
    cursor = 0.0                  # running start on the master timeline

    for i, beat in enumerate(story.beats):
        # 2) Narration for this beat — its duration drives everything below.
        vo_path, vo_dur = tts.synthesize(
            app, llm, beat.narration_sentence, out_dir / f"{content_id}_beat{i}_vo",
            voice=voice, instructions=instructions,
            content_id=content_id, product_id=product["id"])
        beat_audio_paths.append(vo_path)

        # Captions: align this beat's words against its own audio, then shift onto
        # the master timeline. Per-beat alignment keeps each sentence's karaoke
        # confined to its own clip (better sync than one global pass).
        words = word_timestamps(app, vo_path, beat.narration_sentence, llm=llm,
                                duration=vo_dur)
        shifted = [(w, s + cursor, e + cursor) for (w, s, e) in words]

        # 3) Visual clip for this beat, then fit it to the narration length.
        raw_clip = _beat_clip(app, llm, beat, vo_dur, out_dir, i, content_id,
                              product["id"], character)
        src_name, in_, out_, speed = _fit_clip(raw_clip, vo_dur, out_dir, i)

        beats_meta.append({"src": src_name, "in": in_, "out": out_, "speed": speed,
                           "dur": vo_dur, "words": shifted})
        cursor += vo_dur

    # Concatenate the per-beat narration into one voiceover track for the EDL.
    narration = _concat_audio(beat_audio_paths, out_dir / f"{content_id}_narration.wav")

    # 4) Build the EDL: hard cuts (NOT crossfades) so the visual timeline length
    # equals the narration length exactly and every beat's clip lines up with its
    # sentence — a crossfade would overlap seams and drift the sync.
    clips = [
        edl_mod.Clip(id=f"b{i}", src=m["src"], **{"in": m["in"]}, out=m["out"],
                     order=i, fit="cover", speed=m["speed"], mute=True)
        for i, m in enumerate(beats_meta)
    ]
    caption_words = [
        edl_mod.CaptionWord(w=w, t0=round(s, 3), t1=round(e, 3))
        for m in beats_meta for (w, s, e) in m["words"]
    ]
    edl = edl_mod.EDL(
        ai_generated=True,   # generated visuals → disclosure invariant (Contract 4)
        canvas=edl_mod.Canvas(width=WIDTH, height=HEIGHT, fps=FPS),
        clips=clips,
        captions=edl_mod.Captions(mode="karaoke", style="hormozi", words=caption_words),
        audio=[edl_mod.AudioTrack(src=Path(narration).name, kind="voiceover", t0=0.0)],
    )
    from ..agents import media as _media

    edl = _media.apply_sfx_to_edl(app, llm, edl, plan=plan, product=product)
    edl_mod.save(edl, edl_mod.edl_path_for(out_dir))

    # 5) Render the final captioned master.
    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    render_edl(app, edl, out_dir, final)
    return {"media_paths": [str(final)]}


# --------------------------------------------------------------------------- #
# Per-beat visual clip
# --------------------------------------------------------------------------- #
def _beat_clip(app: App, llm: LLM, beat: RecapBeat, target: float, out_dir: Path,
               i: int, content_id, product_id, character: Optional[dict]) -> Path:
    """Produce ONE source clip for a beat: fal text/image-to-video when fal is
    live, a Pillow-still placeholder clip otherwise. Character consistency (when
    a persona fronts the content) locks identity via an image-to-video first
    frame, exactly like ``media/video._background``."""
    first_frame = _character_frame(app, llm, beat, out_dir, i, content_id,
                                   product_id, character)
    clip = out_dir / f"beat{i}.mp4"

    if not app.is_mock("fal"):
        try:
            from ..media import video as video_mod

            secs = max(_FAL_MIN_SEC, min(_FAL_MAX_SEC, round(target) + 1))
            video_mod._fal_clip(app, beat.visual_prompt, secs, clip,
                                content_id, product_id, first_frame)
            return clip
        except Exception as exc:  # never crash a render over one beat — degrade
            log.warning("fal beat %d failed (%s) → still-image clip", i, exc)
            _record_degradation(app, f"fal recap beat failed → still clip ({exc})",
                                content_id, product_id)

    return _still_clip(app, llm, beat, target, out_dir, i, content_id, product_id,
                       first_frame)


def _character_frame(app, llm, beat, out_dir, i, content_id, product_id,
                     character) -> Optional[Path]:
    if not (character and character.get("reference_image")):
        return None
    try:
        from .. import characters as characters_mod

        scene = characters_mod.scene_prompt(character, beat.visual_prompt)
        frame = out_dir / f"{content_id}_beat{i}_frame.png"
        images.generate_image(app, llm, scene, frame, size="1024x1536",
                              reference_images=[character["reference_image"]],
                              content_id=content_id, product_id=product_id)
        return frame
    except Exception:
        _record_degradation(app, "recap character frame failed → unconditioned visual",
                            content_id, product_id)
        return None


def _still_clip(app: App, llm: LLM, beat: RecapBeat, target: float, out_dir: Path,
                i: int, content_id, product_id, first_frame: Optional[Path]) -> Path:
    """Offline / fallback beat clip: a generated still panned into a short video a
    hair longer than the narration so the fitter only ever has to trim."""
    still = first_frame
    if still is None:
        still = out_dir / f"{content_id}_beat{i}.png"
        images.generate_image(app, llm, beat.visual_prompt, still, size="1024x1536",
                              content_id=content_id, product_id=product_id)
    clip = out_dir / f"beat{i}.mp4"
    dur = round(target + 0.4, 3)
    vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={WIDTH}:{HEIGHT},setsar=1")
    _ffmpeg(["-y", "-loop", "1", "-i", still.name, "-t", f"{dur}", "-r", str(FPS),
             "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-preset", "veryfast", "-an", clip.name], cwd=out_dir,
            what=f"still clip beat {i}")
    from ..llm import log_external_cost

    log_external_cost(app, "fal", "video", "mock-recap-beat", units=dur,
                      content_id=content_id, product_id=product_id, mocked=True)
    return clip


# --------------------------------------------------------------------------- #
# Narration-is-master-clock fitting
# --------------------------------------------------------------------------- #
def _fit_clip(clip_path: Path, target: float, out_dir: Path,
              i: int) -> tuple[str, float, float, float]:
    """Fit a source clip to the narration ``target`` length using only EDL
    knobs (in/out trim + speed, clamped 0.5-2.0). Returns the relative src name
    plus (in, out, speed) so the effective on-timeline duration
    ``(out-in)/speed`` equals ``target``.

    Priority (never stretch the narration audio):
      * clip long enough      → trim to target (speed 1.0).
      * clip a bit short       → slow it (speed = src/target, if ≥ 0.5).
      * clip far too short     → pre-loop it past target with ffmpeg, then trim.
    """
    src_dur = _probe_duration(clip_path)
    name = Path(clip_path).name
    if src_dur <= 0:                       # unprobeable — trust the generator
        return name, 0.0, max(target, 0.1), 1.0
    if src_dur >= target:                  # trim
        return name, 0.0, round(target, 3), 1.0
    speed = src_dur / target               # < 1.0 → slower playback fills target
    if speed >= edl_mod.SPEED_MIN:
        return name, 0.0, round(src_dur, 3), round(speed, 4)
    looped = _loop_clip(clip_path, target, out_dir, i)
    return Path(looped).name, 0.0, round(target, 3), 1.0


def _loop_clip(clip_path: Path, target: float, out_dir: Path, i: int) -> Path:
    """Loop a too-short clip until it comfortably exceeds ``target`` so a plain
    trim can then land it exactly."""
    looped = out_dir / f"beat{i}_loop.mp4"
    _ffmpeg(["-y", "-stream_loop", "-1", "-i", Path(clip_path).name,
             "-t", f"{round(target + 0.4, 3)}", "-r", str(FPS),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
             "-an", looped.name], cwd=out_dir, what=f"loop beat {i}")
    return looped


def _concat_audio(paths: list[Path], out_path: Path) -> Path:
    """Concatenate the per-beat voiceovers into one master track (re-encoded to
    PCM WAV so mixed mp3/wav inputs from the real/mock TTS paths join cleanly)."""
    out_path = Path(out_path)
    if len(paths) == 1:
        _ffmpeg(["-y", "-i", Path(paths[0]).name, "-ac", "1", "-ar", "44100",
                 out_path.name], cwd=out_path.parent, what="single narration")
        return out_path
    listing = out_path.parent / f"{out_path.stem}_list.txt"
    listing.write_text("\n".join(f"file '{Path(p).name}'" for p in paths) + "\n")
    _ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", listing.name,
             "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", out_path.name],
            cwd=out_path.parent, what="narration concat")
    return out_path


# --------------------------------------------------------------------------- #
# clip_intelligence — the reusable owned-footage clipping skill
# --------------------------------------------------------------------------- #
def clip_intelligence(app: App, video_path: Path, *, threshold: float = 0.3,
                      min_scene_len: float = 0.6,
                      max_shots: Optional[int] = None) -> list[dict]:
    """Split a USER-SUPPLIED LOCAL video into shots and return one keyframe per
    shot. This is the reusable "clipping skill" — recap's owned-footage mode and
    later templates build on it.

    RIGHTS: only ever call this on video the user owns or is licensed to use
    (the founder's own demo, public-domain film, owned/licensed footage). This
    NEVER downloads copyrighted movies — that stays banned (Contract, decision 6).

    Best-effort and degrades gracefully:
      1. PySceneDetect (``scenedetect``) when importable.
      2. ffmpeg's ``select='gt(scene,threshold)'`` scene filter otherwise
         (the installed environment has no scenedetect/cv2).
      3. On any failure, one shot spanning the whole file.

    Returns a list of ``{"index", "start", "end", "keyframe"}`` dicts (times in
    seconds; ``keyframe`` is a Path to a mid-shot PNG, or None if extraction
    failed).
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"clip_intelligence: no such file: {video_path}")
    duration = _probe_duration(video_path)
    work = video_path.parent / f".{video_path.stem}_shots"
    work.mkdir(parents=True, exist_ok=True)

    boundaries = _scenedetect_boundaries(video_path, threshold, min_scene_len)
    if boundaries is None:
        boundaries = _ffmpeg_scene_boundaries(video_path, threshold)

    # Turn interior cut points into [start, end) shot spans.
    cuts = [t for t in boundaries if 0.0 < t < (duration or t + 1)]
    edges = [0.0] + sorted(cuts) + [duration if duration > 0 else (cuts[-1] + 1 if cuts else 1.0)]
    shots: list[dict] = []
    for idx in range(len(edges) - 1):
        start, end = edges[idx], edges[idx + 1]
        if end - start < min_scene_len and idx not in (0, len(edges) - 2):
            continue  # merge sub-threshold slivers into the neighbour
        keyframe = _extract_keyframe(video_path, (start + end) / 2.0, work, idx)
        shots.append({"index": len(shots), "start": round(start, 3),
                      "end": round(end, 3), "keyframe": keyframe})
        if max_shots and len(shots) >= max_shots:
            break
    if not shots:  # pathological — one shot for the whole file
        shots = [{"index": 0, "start": 0.0, "end": round(duration, 3),
                  "keyframe": _extract_keyframe(video_path, (duration or 1) / 2, work, 0)}]
    return shots


def _scenedetect_boundaries(video_path: Path, threshold: float,
                            min_scene_len: float) -> Optional[list[float]]:
    """PySceneDetect path (only if the lib is importable — it is not in this
    environment, so this returns None and we fall through to ffmpeg)."""
    try:
        from scenedetect import AdaptiveDetector, detect  # type: ignore
    except Exception:
        return None
    try:
        fps = _probe_fps(video_path) or 30.0
        scenes = detect(str(video_path),
                        AdaptiveDetector(min_scene_len=max(1, int(min_scene_len * fps))))
        # Interior cut points = each scene's start (skip the 0.0 opening).
        return [s[0].get_seconds() for s in scenes if s[0].get_seconds() > 0.01]
    except Exception as exc:
        log.debug("scenedetect failed (%s) → ffmpeg scene filter", exc)
        return None


def _ffmpeg_scene_boundaries(video_path: Path, threshold: float) -> list[float]:
    """Scene-change timestamps via ffmpeg's scene filter. ``select`` keeps only
    frames whose scene score exceeds ``threshold``; ``showinfo`` prints each
    kept frame's ``pts_time`` to stderr, which we parse."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video_path),
         "-filter:v", f"select='gt(scene,{threshold})',showinfo",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    return sorted(set(times))


def _extract_keyframe(video_path: Path, t: float, work: Path,
                      idx: int) -> Optional[Path]:
    out = work / f"shot_{idx:03d}.png"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{max(t, 0):.3f}", "-i", str(video_path),
         "-frames:v", "1", str(out)],
        capture_output=True, text=True)
    return out if proc.returncode == 0 and out.is_file() else None


# --------------------------------------------------------------------------- #
# ffmpeg / probe helpers
# --------------------------------------------------------------------------- #
def _has_ffmpeg() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None


def _ffmpeg(args: list[str], *, cwd: Path, what: str) -> None:
    proc = subprocess.run(["ffmpeg", *args], cwd=str(cwd),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg {what} failed: {proc.stderr[-600:]}")


def _probe_duration(path: Path) -> float:
    return tts.media_duration(path)


def _probe_fps(path: Path) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        if "/" in out:
            num, den = out.split("/")
            return float(num) / float(den) if float(den) else None
        return float(out) if out else None
    except Exception:
        return None


def _record_degradation(app: App, msg: str, content_id, product_id) -> None:
    try:
        from ..agents.media import record_degradation

        record_degradation(app, msg, content_id=content_id, product_id=product_id)
    except Exception:
        pass
