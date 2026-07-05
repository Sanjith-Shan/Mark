"""Video generation + assembly.

Two visual sources:
  * AI-generated b-roll via fal.ai (Kling / Wan / Veo) when ``FAL_KEY`` is set.
  * An OpenAI/offline background image otherwise.

Long voiceovers get MULTI-SHOT b-roll: the prompt is split into up to
_MAX_SHOTS sequential shot variations, each generated as its own clip and
stitched with ffmpeg concat — a single 10s clip looping under a 40s narration
reads as obviously fake. The offline path mirrors the same multi-segment
shape so the stitching is exercised without fal.

Either way we assemble the final clip with ffmpeg: scale/crop to 1080x1920 (9:16),
mux the TTS voiceover, and burn in TikTok-style word captions. ffmpeg is the only
hard requirement; moviepy is used only if present.

Output spec: 1080x1920, H.264 (yuv420p), 30fps, AAC 128k — matches the targets in
the build spec for all platforms.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

from ..app import App
from ..llm import LLM, log_external_cost
from . import captions as captions_mod
from . import images, tts

WIDTH, HEIGHT, FPS = 1080, 1920, 30
# Rough fal.ai per-second prices for cost logging.
_FAL_PRICE_PER_SEC = {"kling": 0.10, "wan": 0.05, "veo": 0.25}

_MAX_SHOT_SECONDS = 10  # per-clip cap the fal models accept
_MAX_SHOTS = 4          # cost ceiling per video
_SHOT_SUFFIXES = ["wide establishing shot", "close up, tight framing",
                  "different angle, side profile", "slow push-in, shallow depth of field"]


def produce_video(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
                  out_dir: Path, character: dict | None = None) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for video assembly")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    script = (draft.script or draft.caption or plan.topic).strip()

    # 1) Voiceover (in the character's voice when one fronts this content).
    # Comedic scripts get a delivery brief — deadpan, and a beat before the
    # final line (experts lengthen the pre-punch pause ~41%; timing is half
    # the mechanism).
    voice = (character or {}).get("voice") or None
    instructions = None
    if getattr(draft, "humor_mechanism", None):
        instructions = ("Deadpan, dry, completely matter-of-fact — like someone "
                        "who has survived 400 job applications. Do NOT sound "
                        "excited or salesy. Take a clear beat of silence before "
                        "the final line, then deliver it flat.")
    audio_path, duration = tts.synthesize(
        app, llm, script, out_dir / f"{content_id}_voice", voice=voice,
        instructions=instructions,
        content_id=content_id, product_id=product["id"])

    # 2) Background visual (AI video if fal is live, else a generated image).
    bg_path, bg_is_video = _background(app, llm, product, content_id, plan, draft,
                                       out_dir, duration, character=character)

    # 3) Captions.
    words = captions_mod.word_timestamps(app, audio_path, script, duration, llm=llm)
    ass_path = out_dir / "captions.ass"
    if words:
        captions_mod.build_ass(words, WIDTH, HEIGHT, ass_path)

    # 4) Assemble.
    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    _assemble(out_dir, bg_path, bg_is_video, audio_path, ass_path if words else None,
              final, duration, app=app, content_id=content_id, product_id=product["id"])
    return {"media_paths": [str(final)]}


# --------------------------------------------------------------------------- #
# Background
# --------------------------------------------------------------------------- #
def _background(app, llm, product, content_id, plan, draft, out_dir, duration,
                character: dict | None = None):
    prompt = draft.video_prompt or draft.image_prompt or plan.topic

    # Character consistency: render a scene still conditioned on the character's
    # reference sheet, then animate THAT frame (image-to-video). The identity is
    # locked in the first frame, which is how virtual-influencer creators keep a
    # face stable across clips.
    first_frame = None
    if character and character.get("reference_image"):
        from .. import characters as characters_mod

        scene = characters_mod.scene_prompt(character, prompt)
        frame = out_dir / f"{content_id}_scene.png"
        try:
            images.generate_image(app, llm, scene, frame, size="1024x1536",
                                  reference_images=[character["reference_image"]],
                                  content_id=content_id, product_id=product["id"])
            first_frame = frame
        except Exception:
            first_frame = None
            from ..agents.media import record_degradation

            record_degradation(app, "character scene render failed → unconditioned background",
                               content_id=content_id, product_id=product["id"])

    if not app.is_mock("fal"):
        try:
            path = _ai_video(app, prompt, duration, out_dir / f"{content_id}_broll.mp4",
                             content_id, product["id"], first_frame=first_frame)
            return path, True
        except Exception as exc:  # fall through to image background — but say so
            import logging

            logging.getLogger("mark.video").warning(
                "fal video generation failed, using image background: %s", exc)
            from ..agents.media import record_degradation

            record_degradation(app, f"fal video failed → static background ({exc})",
                               content_id=content_id, product_id=product["id"])
    elif duration > _MAX_SHOT_SECONDS and first_frame is None:
        # Offline: produce the same multi-segment b-roll shape the real path
        # would, so shot planning + stitching stay exercised without fal.
        try:
            return _mock_broll(app, llm, prompt, duration,
                               out_dir / f"{content_id}_broll.mp4",
                               content_id, product["id"]), True
        except Exception:
            pass  # fall through to the static image path
    if first_frame is not None:
        return first_frame, False
    # Image background (works offline).
    img = out_dir / f"{content_id}_bg.png"
    images.generate_image(app, llm, prompt, img, size="1024x1536",
                          content_id=content_id, product_id=product["id"])
    return img, False


def _shot_plan(prompt: str, duration: float) -> list[tuple[str, int]]:
    """Split a long voiceover into up to _MAX_SHOTS sequential (prompt, seconds)
    shots. Same scene prompt with shot-language variation keeps it cheap (no
    extra LLM call) while killing the obvious single-clip loop."""
    n = 1
    if duration > _MAX_SHOT_SECONDS:
        n = min(math.ceil(duration / _MAX_SHOT_SECONDS), _MAX_SHOTS)
    per = int(min(max(duration / n, 3), _MAX_SHOT_SECONDS))
    if n == 1:
        return [(prompt, per)]
    return [(f"{prompt}, {_SHOT_SUFFIXES[i % len(_SHOT_SUFFIXES)]}", per) for i in range(n)]


def _ai_video(app: App, prompt: str, duration: float, out_path: Path,
              content_id, product_id, first_frame: Path | None = None) -> Path:
    shots = _shot_plan(prompt, duration)
    if len(shots) == 1:
        p, sec = shots[0]
        return _fal_clip(app, p, sec, out_path, content_id, product_id, first_frame)
    clips = []
    for i, (p, sec) in enumerate(shots):
        clip = out_path.with_name(f"{out_path.stem}_shot{i + 1}.mp4")
        clips.append(_fal_clip(app, p, sec, clip, content_id, product_id, first_frame))
    return _concat_clips(clips, out_path)


def _fal_clip(app: App, prompt: str, seconds: int, out_path: Path,
              content_id, product_id, first_frame: Path | None = None) -> Path:
    """Generate ONE clip via fal (cost logged per clip)."""
    import httpx
    import fal_client  # type: ignore

    os.environ.setdefault("FAL_KEY", app.keys.fal or "")

    if first_frame is not None:
        # Image-to-video keeps the character identity from the conditioned still.
        model = app.settings.media.video_i2v_model
        image_url = fal_client.upload_file(str(first_frame))
        result = fal_client.subscribe(model, arguments={
            "prompt": prompt, "image_url": image_url,
            "duration": str(seconds), "aspect_ratio": "9:16"})
        url = result["video"]["url"] if isinstance(result.get("video"), dict) else result["video"]
        out_path.write_bytes(httpx.get(url, timeout=300).content)
        rate = next((v for k, v in _FAL_PRICE_PER_SEC.items() if k in model), 0.10)
        log_external_cost(app, "fal", "video", model, usd=rate * seconds, units=seconds,
                          content_id=content_id, product_id=product_id)
        return out_path

    model = app.settings.media.video_model

    def _run(m):
        # fal model schemas define duration as a string enum ("3".."15").
        return fal_client.subscribe(
            m, arguments={"prompt": prompt, "duration": str(seconds), "aspect_ratio": "9:16"})

    try:
        result = _run(model)
    except Exception:
        result = _run(app.settings.media.video_fallback)
        model = app.settings.media.video_fallback

    url = result["video"]["url"] if isinstance(result.get("video"), dict) else result["video"]
    out_path.write_bytes(httpx.get(url, timeout=300).content)
    rate = next((v for k, v in _FAL_PRICE_PER_SEC.items() if k in model), 0.10)
    log_external_cost(app, "fal", "video", model, usd=rate * seconds, units=seconds,
                      content_id=content_id, product_id=product_id)
    return out_path


def _concat_clips(clips: list[Path], out_path: Path) -> Path:
    """Stitch sequential shots with the concat demuxer (re-encoded so mixed
    clip parameters can't break the mux)."""
    work = out_path.parent
    lst = work / f"{out_path.stem}_concat.txt"
    lst.write_text("\n".join(f"file '{Path(c).name}'" for c in clips) + "\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst.name,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-an", out_path.name]
    proc = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {proc.stderr[-500:]}")
    return out_path


def _mock_broll(app: App, llm: LLM, prompt: str, duration: float, out_path: Path,
                content_id, product_id) -> Path:
    """Offline stand-in for :func:`_ai_video` with the same multi-shot shape:
    each shot becomes a short clip rendered from a mock still, stitched via the
    same concat path. Small frame size — _assemble upscales anyway."""
    shots = _shot_plan(prompt, duration)
    clips = []
    for i, (p, sec) in enumerate(shots):
        still = out_path.with_name(f"{out_path.stem}_shot{i + 1}.png")
        images.generate_image(app, llm, p, still, size="1024x1536",
                              content_id=content_id, product_id=product_id)
        clip = out_path.with_name(f"{out_path.stem}_shot{i + 1}.mp4")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", still.name, "-t", str(sec),
               "-r", str(FPS), "-vf", "scale=540:960,setsar=1",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
               clip.name]
        proc = subprocess.run(cmd, cwd=str(out_path.parent), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg mock shot failed: {proc.stderr[-500:]}")
        log_external_cost(app, "fal", "video", "mock-multishot", units=sec,
                          content_id=content_id, product_id=product_id, mocked=True)
        clips.append(clip)
    if len(clips) == 1:
        clips[0].replace(out_path)
        return out_path
    return _concat_clips(clips, out_path)


# --------------------------------------------------------------------------- #
# ffmpeg assembly
# --------------------------------------------------------------------------- #
def _assemble(out_dir, bg_path, bg_is_video, audio_path, ass_path, final, duration,
              app=None, content_id=None, product_id=None):
    bg_rel = Path(bg_path).name
    audio_rel = Path(audio_path).name
    final_rel = Path(final).name

    vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={WIDTH}:{HEIGHT},setsar=1")
    if ass_path is not None:
        vf += f",subtitles={Path(ass_path).name}"

    if bg_is_video:
        inputs = ["-stream_loop", "-1", "-i", bg_rel]
    else:
        inputs = ["-loop", "1", "-i", bg_rel]

    base = [
        "ffmpeg", "-y", *inputs, "-i", audio_rel,
        "-map", "0:v", "-map", "1:a",
        "-vf", vf, "-r", str(FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k",
        "-t", f"{duration:.2f}", "-shortest", final_rel,
    ]
    # Run from out_dir so the subtitles filter path stays simple/relative.
    proc = subprocess.run(base, cwd=str(out_dir), capture_output=True, text=True)
    if proc.returncode != 0 and ass_path is not None:
        # libass may be unavailable — retry without burned captions.
        vf_no_subs = vf.rsplit(",subtitles=", 1)[0]
        base[base.index("-vf") + 1] = vf_no_subs
        proc = subprocess.run(base, cwd=str(out_dir), capture_output=True, text=True)
        if proc.returncode == 0 and app is not None:
            from ..agents.media import record_degradation

            record_degradation(app, "caption burn-in failed → no captions",
                               content_id=content_id, product_id=product_id)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
