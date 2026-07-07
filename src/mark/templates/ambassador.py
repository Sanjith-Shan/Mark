"""AI brand ambassador ("ABG CMO") — the identity-locked spokesperson template.

A single, fully-synthetic, photorealistic recurring character who fronts product
marketing forever: the SAME person in every video. This template ships the
highest-value, lowest-risk video path from the AI-influencer research
(scratchpad ``report-AI-influencer...json``): an identity-locked still →
locked-voice TTS → talking-head avatar animation → karaoke captions → the shared
EDL renderer (which burns the mandatory AI disclosure).

Consistency is layered exactly as the 2026 playbook prescribes:
  1. IDENTITY PACK (minted once, immutable): a canonical face + a handful of
     reference variants + a locked TTS voice, stored in the ``characters.identity``
     JSON column. Never regenerated — every future asset derives from it.
  2. REFERENCE-CONDITIONED generation: scene stills are edits of the canonical
     face (``images.generate_image(reference_images=...)`` today; nano-banana-pro
     as the upgrade — see INTEGRATION).
  3. QC GATE: :mod:`mark.media.identity` scores rendered frames against the
     canonical ArcFace embedding and logs drift (skipped offline / when
     insightface is absent — never blocks a render).

COMPLIANCE IS BAKED IN, not optional (FTC 2023 Endorsement Guides + Mar-2025
clarifications, per the research risks):
  * The renderer burns an "AI-generated" disclosure over t=0-5s (EDL
    ``ai_generated=True``) and this template adds a "#ad" sponsorship tag —
    dual disclosure, on-screen, in the first seconds.
  * The writer is HARD-constrained AWAY from first-person testimonials: a
    synthetic persona claiming it "tried and loved" a product is deceptive on
    its face. Framing is spokesperson / demonstration only ("watch what this app
    does"). Every ambassador post is treated as sponsored.

Runs FULLY in ``App.is_mock`` — no keys, no fal, no insightface: a deterministic
placeholder face is minted, animated to a motion clip with ffmpeg, and rendered
through the same EDL pipeline as the live path.


INTEGRATION (central wiring the orchestrator owns — NOT done here):
  * Dispatch: ``mark.templates.__init__`` already lists ``ambassador`` in
    ``_MODULES`` and maps ``STRATEGY.id`` → :func:`produce` into ``PRODUCERS``;
    ``agents.media.produce_media`` dispatches on ``strategy.id`` — no change
    needed. ``ensure_identity`` should be called once before the first ambassador
    render (a natural spot: the content-generation entry that resolves the
    character, or a ``mark character mint-identity`` CLI verb).
  * Optional dependency: add insightface to ``pyproject.toml`` as an EXTRA so the
    QC gate can be enabled without bloating the base install::

        [project.optional-dependencies]
        identity = ["insightface>=0.7", "onnxruntime>=1.17", "opencv-python-headless>=4.9"]

    With it absent, :func:`mark.media.identity.check_frames` returns
    ``{"passed": True, "skipped": True}`` — the pipeline is unaffected.
  * fal model slugs used by the LIVE path (re-verify prices/slugs at build time —
    fal slugs churned across 2025-26):
      - talking-head: ``fal-ai/kling-video/ai-avatar/v2/standard`` ($0.0562/s;
        image+audio → lipsynced avatar; animates OUR still so the face is locked).
      - b-roll (future): ``fal-ai/kling-video/o3/pro/reference-to-video`` (@Element
        identity conditioning, $0.112/s).
      - identity mint upgrade: ``fal-ai/nano-banana-pro/edit`` (up to 14 refs,
        ~$0.15/edit) for canonical + variants; ``fal-ai/flux-lora-portrait-trainer``
        (~$2.40/run) to bake a permanent LoRA (``identity.lora_url``).
    These belong in ``config.MediaSettings`` as named fields
    (``avatar_model``, ``broll_ref_model``, ``identity_image_model``,
    ``identity_lora_trainer``); until added, this module reads them via
    ``getattr(app.settings.media, ..., <default slug>)``.
  * Posting: ``posting/manager.py`` already sets platform AIGC flags; ambassador
    content should also carry the platform "paid partnership" tag where the
    upload-post API exposes it (sponsorship half of dual disclosure).
  * DB: uses the existing ``characters.identity`` TEXT/JSON column (added
    centrally). No schema change here.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from .. import characters as characters_mod
from .. import db as db_module
from ..app import App
from ..llm import LLM, log_external_cost
from ..media import edl as E
from ..media import identity, images, render, tts
from ..media.align import word_timestamps
from ..strategies import Strategy

log = logging.getLogger("mark.templates.ambassador")

# Live-path model slugs (see INTEGRATION; overridable via settings once added).
_DEFAULT_AVATAR_MODEL = "fal-ai/kling-video/ai-avatar/v2/standard"

# The no-testimonial rule, quoted verbatim into both the strategist and writer
# briefs so the constraint is impossible to miss (and asserted by tests).
_NO_TESTIMONIAL = (
    "HARD RULE — NO FIRST-PERSON TESTIMONIAL. The ambassador is a synthetic "
    "spokesperson with no real experience; she may NEVER claim to have personally "
    "tried, used, bought, or loved the product ('I tried it and it got me a job' "
    "is BANNED — FTC treats an AI persona's testimonial as deceptive on its face). "
    "Frame every post as demonstration / spokesperson narration ('watch what this "
    "app does', 'here's how it works') in the SECOND or THIRD person. Every post is "
    "sponsored: it is an ad for the product and is labeled #ad on-screen plus the "
    "auto-burned AI-generated disclosure."
)

STRATEGY = Strategy(
    id="ai-ambassador",
    name="AI brand ambassador",
    description=(
        "A single identity-locked, photorealistic synthetic spokesperson who fronts "
        "the product forever — the SAME face and voice in every video. Talking-head "
        "product demonstrations with baked-in AI + sponsorship disclosure. Parasocial "
        "familiarity compounds: the audience comes to know one recurring 'person', "
        "which lifts message acceptance and time-on-content — while staying compliant "
        "because it demonstrates (never testifies)."
    ),
    emotional_target="trust",
    platforms={
        "tiktok": "15-40s talking-head demo; karaoke captions mandatory; hook in first 2s",
        "instagram": "same, one notch more polished; Reels; clear CTA",
        "youtube": "vertical Short, <60s; title curiosity-driven",
        "x": "short talking-head clip; one-line demo caption",
    },
    content_types=["video"],
    humor_level="light",
    uses_character=True,
    strategist_brief=(
        "The product's identity-locked AI ambassador fronts this. Choose ONE concrete "
        "product capability or user pain to DEMONSTRATE (a feature in action, a "
        "before/after of the workflow) — never a personal anecdote. " + _NO_TESTIMONIAL
    ),
    writer_brief=(
        "Write a spoken script for the ambassador to deliver to camera as a "
        "spokesperson demonstrating the product. Second/third person, warm and "
        "credible, hook in the first line, one clear CTA. " + _NO_TESTIMONIAL
    ),
    media_brief=(
        "Talking-head: the canonical ambassador speaks to camera, photorealistic, soft "
        "flattering key light, shallow depth of field, aspirational-lifestyle setting "
        "(NOT suggestive — must stay ad-platform brand-safe). Identity is locked to the "
        "character's canonical face; keep framing frontal / near-frontal to minimise drift."
    ),
    mix_weight=0.08,
)


# --------------------------------------------------------------------------- #
# Identity pack (minted once, immutable)
# --------------------------------------------------------------------------- #
def ensure_identity(app: App, llm: LLM, character: dict) -> dict:
    """Mint (once) and return the character's identity pack.

    The pack — ``{canonical_face, refs[], lora_url, arcface_path, voice_id,
    avatar_model, minted_at}`` — is stored in the ``characters.identity`` JSON
    column and NEVER regenerated: re-reading a live pack returns it verbatim so
    the face can never silently drift between mints. Runs offline (deterministic
    placeholder face); the live path generates a photorealistic canonical +
    reference-conditioned variants.
    """
    char_id = character["id"]
    fresh = characters_mod.get(app, char_id) or character
    existing = db_module.loads(fresh.get("identity"), None)
    if (existing and existing.get("canonical_face")
            and Path(existing["canonical_face"]).exists()):
        return existing  # immutable — already minted

    pack_dir = app.paths.media_dir / "identity" / f"char_{char_id}"
    refs_dir = pack_dir / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    canonical = pack_dir / "canonical.png"

    visual = (character.get("visual_desc") or "a friendly photorealistic person").strip()
    face_prompt = (
        f"Photorealistic head-and-shoulders portrait of {visual}. Single subject, "
        "front-facing, neutral friendly expression, soft even studio key light, "
        "shallow depth of field, plain softly-lit background, natural skin texture, "
        "sharp focus on the eyes, no text, no watermark. Fully synthetic person."
    )

    if app.is_mock("openai"):
        # Deterministic placeholder face so the whole pipeline runs offline.
        _placeholder_face(canonical, seed=char_id)
        refs = []
        for i in range(3):
            r = refs_dir / f"ref_{i}.png"
            _placeholder_face(r, seed=char_id, pose=i + 1)  # same face, tiny pose shift
            refs.append(r)
    else:
        # Canonical face (photorealistic) + reference-conditioned variants. This is
        # the shipped baseline; nano-banana-pro is the upgrade (see INTEGRATION).
        images.generate_image(app, llm, face_prompt, canonical, size="1024x1536",
                              product_id=character["product_id"])
        refs = []
        for i, angle in enumerate(("three-quarter left view", "three-quarter right view",
                                   "warm smiling expression")):
            r = refs_dir / f"ref_{i}.png"
            try:
                images.generate_image(
                    app, llm, f"{visual} — the SAME person, identical face and hair, {angle}",
                    r, size="1024x1536", reference_images=[str(canonical)],
                    product_id=character["product_id"])
                refs.append(r)
            except Exception as exc:
                log.warning("identity ref %d generation failed (%s) — continuing.", i, exc)

    # Canonical ArcFace embedding for the QC gate (None when insightface absent).
    emb = identity.arcface_embedding(canonical)
    arcface_path = None
    if emb is not None:
        arcface_path = pack_dir / "arcface.npy"
        np.save(arcface_path, emb)

    pack = {
        "canonical_face": str(canonical),
        "refs": [str(r) for r in refs],
        "lora_url": None,  # set by a future flux-lora-portrait-trainer run (live)
        "arcface_path": str(arcface_path) if arcface_path else None,
        "voice_id": character.get("voice") or app.settings.media.tts_voice,
        "avatar_model": getattr(app.settings.media, "avatar_model", _DEFAULT_AVATAR_MODEL),
        "minted_at": datetime.now(timezone.utc).isoformat(),
    }
    db_module.update(app.conn, "characters", char_id, identity=pack)
    # Reuse the canonical face as the character's reference sheet so generic
    # (non-template) paths pick up the locked identity too.
    if not fresh.get("reference_image"):
        db_module.update(app.conn, "characters", char_id, reference_image=str(canonical))
    db_module.log_activity(
        app.conn, "character",
        f"Minted identity pack for “{character['name']}” "
        f"(refs={len(refs)}, arcface={'yes' if arcface_path else 'skipped'})",
        product_id=character["product_id"])
    return pack


# --------------------------------------------------------------------------- #
# Produce
# --------------------------------------------------------------------------- #
def produce(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
            out_dir: Path, character: Optional[dict] = None) -> dict:
    """Produce one talking-head ambassador video → ``{"media_paths": [...]}``.

    Talking-head path (ship-first): script → locked-voice TTS → talking-head clip
    (live: fal Kling AI Avatar animating the canonical still; mock: still-to-video
    motion clip) → EDL {clip, karaoke captions aligned over the TTS, voiceover,
    ai_generated=True} → identity QC gate (skipped offline) → EDL render.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for ambassador video")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if character is None:
        character = characters_mod.resolve_for_content(app, product, STRATEGY)
    if character is None:
        raise RuntimeError("ai-ambassador requires a character but none is configured")

    pack = ensure_identity(app, llm, character)
    canonical = Path(pack["canonical_face"])

    # 1) Script → locked-voice TTS. Never a testimonial; the writer enforces this,
    #    but we also strip a leading "I " safety-net is out of scope — trust the brief.
    script = (getattr(draft, "script", None) or getattr(draft, "caption", None)
              or plan.topic or "Here's what this app does.").strip()
    voice = pack.get("voice_id") or (character or {}).get("voice")
    audio_path, duration = tts.synthesize(
        app, llm, script, out_dir / f"{content_id}_voice", voice=voice,
        content_id=content_id, product_id=product["id"])

    # 2) Scene still (identity-locked) then talking-head clip that animates it.
    still = _scene_still(app, llm, product, content_id, plan, draft, out_dir,
                         character, canonical)
    clip = _talking_head_clip(app, still, audio_path, duration,
                              out_dir / f"{content_id}_talkinghead.mp4",
                              content_id, product["id"], pack)
    clip_dur = tts.media_duration(clip) or duration
    clip_out = round(min(duration, clip_dur), 3)
    if clip_out <= 0.1:
        clip_out = round(max(clip_dur, 0.2), 3)

    # 3) Caption timing: forced-align the KNOWN script over the TTS audio.
    words = word_timestamps(app, audio_path, script, llm=llm, duration=duration)

    # 4) EDL: talking-head clip + karaoke captions + voiceover; AI-generated →
    #    the renderer burns the mandatory disclosure over t=0-5s.
    edl = E.EDL(
        version=1,
        ai_generated=True,
        canvas=E.Canvas(width=1080, height=1920, fps=30),
        clips=[E.Clip(id="th", src=clip.name, in_=0.0, out=clip_out, order=0,
                      fit="cover", mute=True)],
        overlays=[E.Overlay(kind="text", text="#ad", t0=0.0, t1=5.0,
                            y_frac=0.055, style="watermark")],  # sponsorship half of dual disclosure
        captions=E.Captions(
            mode="karaoke", style="hormozi",
            words=[E.CaptionWord(w=w, t0=round(s, 3), t1=round(e, 3))
                   for (w, s, e) in words]) if words else E.Captions(mode="none"),
        audio=[E.AudioTrack(src=Path(audio_path).name, kind="voiceover", gain_db=0.0)],
    )
    from ..agents import media as _media

    edl = _media.apply_sfx_to_edl(app, llm, edl, plan=plan, product=product)
    edl_path = E.save(edl, E.edl_path_for(out_dir))

    # 5) Identity QC gate — score rendered frames vs the canonical face. Skipped
    #    offline / when insightface is absent; never blocks the render.
    canonical_emb = _load_embedding(pack)
    qc = identity.check_frames(clip, canonical_emb)
    _log_qc(app, product, content_id, qc)

    # 6) Render: captionless master (for the web editor) + final with captions.
    master = out_dir / "master.mp4"
    master_edl = edl.model_copy(deep=True)
    master_edl.captions = E.Captions(mode="none")
    try:
        render.render_edl(app, master_edl, out_dir, master, proxy=False)
    except Exception as exc:  # master is a convenience artifact — don't fail on it
        log.warning("captionless master render failed (%s) — continuing to final.", exc)

    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    render.render_edl(app, edl, out_dir, final, proxy=False)
    log.info("ambassador video ready: %s (edl=%s, qc=%s)",
             final.name, Path(edl_path).name,
             "skipped" if qc.get("skipped") else qc.get("passed"))
    return {"media_paths": [str(final)]}


# --------------------------------------------------------------------------- #
# Talking-head + scene still
# --------------------------------------------------------------------------- #
def _scene_still(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
                 out_dir: Path, character: dict, canonical: Path) -> Path:
    """A scene keyframe with the character's LOCKED identity. Live: a
    reference-conditioned edit of the canonical face into the scene. Offline: the
    canonical face itself (already deterministic, already the right person)."""
    if app.is_mock("openai"):
        return canonical
    scene = (getattr(draft, "video_prompt", None) or getattr(draft, "image_prompt", None)
             or plan.topic or "speaking to camera")
    prompt = characters_mod.scene_prompt(character, f"{scene}, speaking to camera, front-facing")
    still = out_dir / f"{content_id}_scene.png"
    try:
        images.generate_image(app, llm, prompt, still, size="1024x1536",
                              reference_images=[str(canonical)],
                              content_id=content_id, product_id=product["id"])
        return still
    except Exception as exc:
        log.warning("scene still render failed (%s) — falling back to canonical face.", exc)
        return canonical


def _talking_head_clip(app: App, still: Path, audio_path: Path, duration: float,
                       out_path: Path, content_id: int, product_id: str,
                       pack: dict) -> Path:
    """Animate ``still`` to a talking-head clip. Live: fal Kling AI Avatar (image +
    audio → lipsynced video; the face is inherently locked because it animates OUR
    still). Offline: a subtle still-to-video motion clip via ffmpeg."""
    if not app.is_mock("fal"):
        try:
            return _fal_avatar(app, still, audio_path, duration, out_path,
                               content_id, product_id, pack)
        except Exception as exc:
            log.warning("fal avatar generation failed (%s) — using motion-clip fallback.", exc)
    return _mock_motion_clip(still, duration, out_path)


def _fal_avatar(app: App, still: Path, audio_path: Path, duration: float,
                out_path: Path, content_id: int, product_id: str, pack: dict) -> Path:
    """Live talking-head via fal Kling AI Avatar v2 (image + audio → lipsync)."""
    import os

    import httpx
    import fal_client  # type: ignore

    os.environ.setdefault("FAL_KEY", app.keys.fal or "")
    model = pack.get("avatar_model") or _DEFAULT_AVATAR_MODEL
    image_url = fal_client.upload_file(str(still))
    audio_url = fal_client.upload_file(str(audio_path))
    result = fal_client.subscribe(model, arguments={
        "image_url": image_url, "audio_url": audio_url, "aspect_ratio": "9:16"})
    video = result.get("video")
    url = video["url"] if isinstance(video, dict) else video
    out_path.write_bytes(httpx.get(url, timeout=600).content)
    log_external_cost(app, "fal", "video", model, usd=0.0562 * max(duration, 1),
                      units=int(max(duration, 1)), content_id=content_id,
                      product_id=product_id)
    return out_path


def _mock_motion_clip(still: Path, duration: float, out_path: Path) -> Path:
    """Offline talking-head stand-in: the still with a slow Ken-Burns push-in so
    it reads as a moving clip (not a frozen frame). Falls back to a plain loop if
    zoompan isn't available. 1080x1920, muted (voiceover is muxed by the EDL)."""
    dur = max(float(duration), 0.5)
    total_frames = max(int(dur * 30), 1)
    work = out_path.parent
    zoom = (f"scale=1350:2400,zoompan=z='min(zoom+0.0006,1.12)':d={total_frames}:"
            f"s=1080x1920:fps=30,setsar=1")
    # The still may live outside ``work`` (the canonical face sits in the identity
    # pack dir) — pass it as an absolute path; only the OUTPUT is a bare name.
    base = ["ffmpeg", "-y", "-loop", "1", "-i", str(Path(still).resolve()),
            "-t", f"{dur:.3f}", "-r", "30"]
    tail = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-an", out_path.name]
    proc = subprocess.run(base + ["-vf", zoom] + tail, cwd=str(work),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        # zoompan unavailable/failed — plain scaled loop still yields a valid clip.
        plain = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        proc = subprocess.run(base + ["-vf", plain] + tail, cwd=str(work),
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg motion clip failed: {proc.stderr[-500:]}")
    return out_path


# --------------------------------------------------------------------------- #
# QC helpers
# --------------------------------------------------------------------------- #
def _load_embedding(pack: dict) -> Optional[np.ndarray]:
    p = pack.get("arcface_path")
    if p and Path(p).exists():
        try:
            return np.load(p)
        except Exception:
            return None
    return None


def _log_qc(app: App, product: dict, content_id: int, qc: dict) -> None:
    if qc.get("skipped"):
        msg = "identity QC skipped (insightface/embedding absent)"
    else:
        msg = (f"identity QC {'PASS' if qc.get('passed') else 'DRIFT'} "
               f"mean={qc.get('mean_sim')} min={qc.get('min_sim')} thr={qc.get('threshold')}")
    try:
        db_module.log_activity(app.conn, "render", msg, product_id=product["id"])
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Offline placeholder face (deterministic, seeded)
# --------------------------------------------------------------------------- #
def _placeholder_face(out_path: Path, seed: int, pose: int = 0) -> Path:
    """A deterministic, clearly-a-person placeholder portrait for mock mode: a
    seeded background gradient with a simple frontal face (head, eyes, brows,
    nose, mouth). Same ``seed`` → same face; ``pose`` nudges eye/head position a
    hair so reference variants differ without changing identity. Real PNG so the
    downstream pipeline (avatar animation, QC, render) works unchanged."""
    from PIL import Image, ImageDraw

    W, H = 1024, 1536
    rng = np.random.default_rng(seed * 2654435761 % (2**32))
    top = rng.integers(30, 90, size=3)
    bottom = rng.integers(120, 200, size=3)
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (top[None, None, :] * (1 - grad) + bottom[None, None, :] * grad)
    arr = np.broadcast_to(arr, (H, W, 3)).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)

    cx = W // 2 + (pose - 1) * 12       # tiny head shift per pose
    cy = int(H * 0.46)
    fw, fh = int(W * 0.34), int(H * 0.26)  # face half-extents
    skin = tuple(int(x) for x in rng.integers(170, 225, size=3)) + (255,)
    hair = tuple(int(x) for x in rng.integers(30, 90, size=3)) + (255,)

    # Hair (behind face), then face oval.
    draw.ellipse([cx - fw - 18, cy - fh - 70, cx + fw + 18, cy + fh - 10], fill=hair)
    draw.ellipse([cx - fw, cy - fh, cx + fw, cy + fh], fill=skin)

    eye_dx = int(fw * 0.42)
    eye_y = cy - int(fh * 0.12) + (pose - 1) * 3
    eye_w, eye_h = int(fw * 0.20), int(fh * 0.11)
    for sx in (-1, 1):
        ex = cx + sx * eye_dx
        draw.ellipse([ex - eye_w, eye_y - eye_h, ex + eye_w, eye_y + eye_h],
                     fill=(255, 255, 255, 255))
        draw.ellipse([ex - eye_h, eye_y - eye_h, ex + eye_h, eye_y + eye_h],
                     fill=(40, 30, 25, 255))                       # iris/pupil
        draw.line([ex - eye_w, eye_y - eye_h - 14, ex + eye_w, eye_y - eye_h - 16],
                  fill=hair, width=8)                              # brow
    # Nose + mouth.
    draw.line([cx, eye_y + 10, cx - 10, cy + int(fh * 0.30)], fill=(120, 90, 80, 255), width=6)
    draw.line([cx - 10, cy + int(fh * 0.30), cx + 14, cy + int(fh * 0.30)],
              fill=(120, 90, 80, 255), width=6)
    mw = int(fw * 0.42)
    my = cy + int(fh * 0.58)
    draw.arc([cx - mw, my - 26, cx + mw, my + 26], start=10, end=170,
             fill=(150, 70, 70, 255), width=10)

    img.convert("RGB").save(out_path)
    return out_path
