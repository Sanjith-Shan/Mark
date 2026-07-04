"""Video generation + assembly.

Two visual sources:
  * AI-generated b-roll via fal.ai (Kling / Wan / Veo) when ``FAL_KEY`` is set.
  * An OpenAI/offline background image otherwise.

Either way we assemble the final clip with ffmpeg: scale/crop to 1080x1920 (9:16),
mux the TTS voiceover, and burn in TikTok-style word captions. ffmpeg is the only
hard requirement; moviepy is used only if present.

Output spec: 1080x1920, H.264 (yuv420p), 30fps, AAC 128k — matches the targets in
the build spec for all platforms.
"""

from __future__ import annotations

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


def produce_video(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
                  out_dir: Path, character: dict | None = None) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for video assembly")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    script = (draft.script or draft.caption or plan.topic).strip()

    # 1) Voiceover (in the character's voice when one fronts this content).
    voice = (character or {}).get("voice") or None
    audio_path, duration = tts.synthesize(
        app, llm, script, out_dir / f"{content_id}_voice", voice=voice,
        content_id=content_id, product_id=product["id"])

    # 2) Background visual (AI video if fal is live, else a generated image).
    bg_path, bg_is_video = _background(app, llm, product, content_id, plan, draft,
                                       out_dir, duration, character=character)

    # 3) Captions.
    words = captions_mod.word_timestamps(app, audio_path, script, duration)
    ass_path = out_dir / "captions.ass"
    if words:
        captions_mod.build_ass(words, WIDTH, HEIGHT, ass_path)

    # 4) Assemble.
    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    _assemble(out_dir, bg_path, bg_is_video, audio_path, ass_path if words else None,
              final, duration)
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

    if not app.is_mock("fal"):
        try:
            path = _ai_video(app, prompt, duration, out_dir / f"{content_id}_broll.mp4",
                             content_id, product["id"], first_frame=first_frame)
            return path, True
        except Exception as exc:  # fall through to image background — but say so
            import logging

            logging.getLogger("mark.video").warning(
                "fal video generation failed, using image background: %s", exc)
    if first_frame is not None:
        return first_frame, False
    # Image background (works offline).
    img = out_dir / f"{content_id}_bg.png"
    images.generate_image(app, llm, prompt, img, size="1024x1536",
                          content_id=content_id, product_id=product["id"])
    return img, False


def _ai_video(app: App, prompt: str, duration: float, out_path: Path,
              content_id, product_id, first_frame: Path | None = None) -> Path:
    import httpx
    import fal_client  # type: ignore

    os.environ.setdefault("FAL_KEY", app.keys.fal or "")
    seconds = int(min(max(duration, 3), 10))

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


# --------------------------------------------------------------------------- #
# ffmpeg assembly
# --------------------------------------------------------------------------- #
def _assemble(out_dir, bg_path, bg_is_video, audio_path, ass_path, final, duration):
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
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
