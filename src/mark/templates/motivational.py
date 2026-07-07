"""Motivational-letterbox template — the "motivational clips" niche, built clean.

The format (from the research report): a native 9:16 1080x1920 file with a solid
black canvas; a moody cinematic b-roll clip scaled into a centered ~1:1 window
(the black bars top/bottom are rendered INTO the file on purpose — that is the
letterbox convention, and it dodges the platform re-letterbox downrank that a
true 4:5 upload gets); a short second-person motivational line in the TOP bar; a
small ``@handle`` watermark in the BOTTOM bar. Audio is EITHER an original spoken
monologue (word-level karaoke captions) OR a licensed music bed under silent
b-roll with only the static quote.

Two registers — a bandit-friendly angle (register should be a bandit arm):

  * ``harsh``  — discipline/"sigma" grind: imperative, self-reliance, "Nobody is
    coming to save you." Spoken-monologue lane with karaoke captions.
  * ``hopecore`` — the 2026-resurgent soft register: cinematic slow-build,
    uplifting. Music-bed lane over silent b-roll with the static quote only.

Rights posture (the whole reason to build ORIGINAL rather than repost): we never
touch licensed speeches (Motiversity et al.), movie scenes, or trending
commercial audio. Visuals are license-free stock (Pexels/Pixabay — free for
commercial use, no attribution); the quote copy is LLM-written in the niche
register; speech is original TTS. That is "original composition in the niche's
visual language" — safe on Instagram's aggregator crackdown and TikTok's
Originality Policy, both of which now bury reposted/duplicated clips.

Everything works in ``App.is_mock`` mode with zero API keys: the LLM returns a
deterministic sample quote, stock sourcing returns a real local lavfi clip, and
TTS writes a real (silent) WAV — so the full EDL → render path is exercised
offline.

INTEGRATION (central wiring — NOT done in this module)
------------------------------------------------------
* Dispatch: registered automatically via ``templates.ensure_loaded()`` →
  ``PRODUCERS["motivational-letterbox"]``; ``agents/media.produce_media`` already
  routes template strategies. No edit needed there.
* Bandit arms this template wants tracked (add to the ``topic_angle`` / a new
  ``register`` arm type in the bandit config): ``register`` (harsh vs hopecore),
  ``audio_mode`` (speech vs music), ``quote_length``, and eventually ``grade``
  (B&W vs color) and ``broll_source`` (stock vs AI). Register is read here from
  ``plan.tone``/``plan.angle`` so the strategist/bandit can already steer it.
* Music lane: there is no central licensed-music sourcing module yet. Until one
  exists, the music bed is a synthesized ambient placeholder (ffmpeg). When a
  ``sourcing.music`` module lands (Pixabay/Uppbeat, license-clean), point
  ``_music_bed`` at it. Do NOT bake trending commercial audio into the file.
* B&W grade + slow-mo intensity: slow-mo is applied here via clip ``speed``; a
  per-clip grayscale grade is a future EDL field (needs a renderer filter) — left
  out so this module never edits ``render.py``.
* AI b-roll lane (fal Kling) is intentionally not wired here — stock keeps the
  ``ai_generated`` disclosure off for a cleaner motivational frame. If an AI lane
  is added, set ``EDL.ai_generated=True`` so the renderer burns the disclosure.
* Config (optional, sane defaults in code): a ``sourcing.stock`` query vocabulary
  block per register; ``PEXELS_API_KEY`` / ``PIXABAY_API_KEY`` in ``.env``.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from ..app import App
from ..llm import LLM
from ..media import edl as edl_mod
from ..media import align, render, tts
from ..sourcing import stock
from ..strategies import Strategy

log = logging.getLogger("mark.templates.motivational")

# Letterbox composition: a centered 1080x1080 window with ~420px bars top/bottom.
_WINDOW = {"x": 0, "y": 420, "w": 1080, "h": 1080}
_QUOTE_Y = 150        # quote sits in the top bar (0..420)
_WATERMARK_Y = 1560   # @handle sits in the bottom bar (1500..1920)
_MIN_SECONDS, _MAX_SECONDS = 6.0, 18.0   # niche clips run ~6-20s; keep loopable

# Curated, reliably-populated stock query vocabulary per register (research §3a).
_QUERIES = {
    "harsh": ["boxer training dark gym", "man running in rain", "cold plunge water",
              "rowing machine sweat", "lifting weights dark", "sprint stadium night",
              "mountain climber storm", "lone figure city night rain"],
    "hopecore": ["sunrise mountain summit", "friends celebrating sunset",
                 "ocean waves golden hour", "child running open field",
                 "city lights night drive", "sunlight through forest",
                 "runner finish line joy", "waves crashing slow motion"],
}

# Deterministic offline sample quotes (≤12 words, second person) — used in mock.
_SAMPLE_QUOTE = {
    "harsh": "Nobody is coming to save you. Get up and go.",
    "hopecore": "Keep going. The version of you waiting is worth it.",
}
_SAMPLE_MONOLOGUE = {
    "harsh": ("Nobody is coming to save you. The help you keep waiting for is "
              "not on its way. Get up. Do the hard thing today, and do it again "
              "tomorrow. Discipline is the only rescue you get."),
    "hopecore": ("Keep going. The road is long and the nights are quiet, but you "
                 "are closer than you were. The version of you that made it is "
                 "already proud. Take one more step."),
}


# --------------------------------------------------------------------------- #
# Strategy
# --------------------------------------------------------------------------- #
STRATEGY = Strategy(
    id="motivational-letterbox",
    name="Motivational letterbox",
    description=(
        "Original 'motivational clips' in the letterbox format: a moody cinematic "
        "b-roll clip framed in a centered 1:1 window with rendered-in black bars, a "
        "second-person quote in the top bar, an @handle in the bottom bar, and "
        "either an original spoken monologue with karaoke captions or a licensed "
        "music bed. Built ORIGINAL (license-free stock visuals + LLM quote + TTS "
        "speech) rather than reposted — the durable, ban-safe play now that "
        "Instagram excludes aggregator reposts from recommendations and TikTok's "
        "Originality Policy buries duplicated clips. Two registers, harsh-discipline "
        "vs 2026-resurgent hopecore, are a bandit arm."
    ),
    emotional_target="determination",
    platforms={
        "tiktok": "6-15s letterbox; harsh register + spoken monologue with karaoke captions; slow-mo b-roll",
        "instagram": "same, one notch more cinematic; keep the quote inside the top bar; loopable last frame",
        "youtube": "Shorts-native 9:16 letterbox; either register works",
        "x": "single vertical letterbox clip; quote doubles as the post text",
    },
    content_types=["video"],
    humor_level="none",
    uses_character=False,
    strategist_brief=(
        "Pick ONE register — harsh (discipline/self-reliance, imperative) or "
        "hopecore (soft, cinematic slow-build, uplifting) — and one concrete "
        "second-person idea. Harsh pairs with a spoken monologue; hopecore pairs "
        "with a music bed and a static quote. Name the register in the tone/angle "
        "so the bandit can learn which lands per platform."
    ),
    writer_brief=(
        "Write ONE quote line: second person, imperative, ≤12 words, self-reliance "
        "or hopecore-soft. 'Nobody is coming to save you.' 'Comfort is the enemy of "
        "progress.' No hashtags in the line, no author attribution, no 'in today's "
        "world' slop. For the harsh lane also write a 3-4 sentence monologue that "
        "expands the line — this becomes the original TTS voiceover."
    ),
    media_brief=(
        "Letterbox composer: centered 1:1 window, black bars are part of the "
        "composition. Quote top bar, @handle bottom bar. Moody cinematic slow-mo "
        "stock b-roll (boxing, running in rain, summits, city-at-night). Harsh = "
        "spoken monologue + karaoke captions; hopecore = ambient music bed, static "
        "quote only."
    ),
    example_sketches=[
        'harsh: b-roll of a boxer in a dark gym, top-bar quote "NOBODY IS COMING '
        'TO SAVE YOU. GET UP." over a flat spoken monologue with word-by-word captions.',
        'hopecore: slow-mo sunrise summit, static quote "KEEP GOING. IT IS WORTH '
        'IT." over a warm ambient bed, no speech.',
    ],
    mix_weight=0.12,
    requires_product=False,   # works for entertainment accounts too — the clip IS the content
    never_auto_approve=False,
)


# --------------------------------------------------------------------------- #
# LLM quote schema (kept local — schemas.py is centrally owned)
# --------------------------------------------------------------------------- #
class _Quote(BaseModel):
    quote: str = Field(description="Second-person motivational line, <=12 words")
    monologue: str = Field(default="", description="3-4 sentence spoken expansion (harsh lane)")


def _mock_quote(register: str) -> "_Quote":
    return _Quote(quote=_SAMPLE_QUOTE[register], monologue=_SAMPLE_MONOLOGUE[register])


# --------------------------------------------------------------------------- #
# Produce
# --------------------------------------------------------------------------- #
def produce(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
            out_dir: Path, character: dict | None = None) -> dict:
    """Compose one motivational-letterbox video. Returns ``{"media_paths": [...]}``
    (same shape as ``video.produce_video``) and writes ``edit.json`` into
    ``out_dir``. Works end-to-end in mock mode with no API keys."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found — required for motivational-letterbox render")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    register = _register_for(plan)
    speech = register == "harsh"   # harsh → spoken monologue; hopecore → music bed

    # 1) Quote (+ monologue) — LLM in the niche register, deterministic offline.
    quote_obj = _quote(app, llm, product, plan, register, draft, content_id)
    quote_text = _clean_quote(quote_obj.quote)
    monologue = (quote_obj.monologue or quote_obj.quote or quote_text).strip()

    # 2) Audio lane.
    audio_track = None
    caption_words: list[edl_mod.CaptionWord] = []
    if speech:
        voice = (character or {}).get("voice") or None
        audio_path, audio_dur = tts.synthesize(
            app, llm, monologue, out_dir / f"{content_id}_voice", voice=voice,
            instructions=_DELIVERY, content_id=content_id, product_id=product["id"])
        words = align.word_timestamps(app, audio_path, monologue, llm=llm,
                                      duration=audio_dur)
        caption_words = [edl_mod.CaptionWord(w=w, t0=round(s, 3), t1=round(e, 3))
                         for (w, s, e) in words]
        audio_track = edl_mod.AudioTrack(
            src=str(audio_path.resolve()), kind="voiceover", gain_db=0.0)
        target = audio_dur
    else:
        target = 9.0
        music_path = _music_bed(app, out_dir, target)
        audio_track = edl_mod.AudioTrack(
            src=str(music_path.resolve()), kind="music", gain_db=-6.0, duck_db=-12.0)

    # 3) Source a moody cinematic b-roll clip (license-free stock; real clip offline).
    clip_path, source_dur = _source_broll(app, register, content_id)

    # 4) Fit the clip's on-timeline length to the audio, using slow-mo to stretch
    #    a short clip (slow-motion is the niche signature) and trimming a long one.
    desired = _clamp(target, _MIN_SECONDS, min(_MAX_SECONDS, source_dur * 2))
    speed = _clamp(source_dur / desired, 0.5, 1.0)   # <1.0 = slow-mo stretch
    out = min(source_dur, desired * speed)
    duration = round(out / speed, 3)                 # actual on-timeline length

    # 5) Build the EDL.
    clip = edl_mod.Clip(
        id="broll", src=str(clip_path.resolve()), **{"in": 0.0}, out=round(out, 3),
        order=0, fit="window", window=edl_mod.Window(**_WINDOW), speed=round(speed, 4),
        mute=True)

    overlays = [
        edl_mod.Overlay(kind="text", text=_display_quote(quote_text), t0=0.0,
                        t1=duration, y=_QUOTE_Y, style="quote"),
        edl_mod.Overlay(kind="text", text=_handle(product), t0=0.0, t1=duration,
                        y=_WATERMARK_Y, style="watermark"),
    ]

    captions = edl_mod.Captions(mode="karaoke", style="hormozi", words=caption_words) \
        if caption_words else edl_mod.Captions(mode="none")

    edl = edl_mod.EDL(
        version=1,
        ai_generated=False,   # stock b-roll, not AI — no disclosure needed
        canvas=edl_mod.Canvas(width=1080, height=1920, fps=30, background="#000000"),
        clips=[clip],
        overlays=overlays,
        captions=captions,
        audio=[audio_track],
    )

    # 6) Auto-place SFX (shared build step), persist edit.json, render.
    from ..agents import media as _media

    edl = _media.apply_sfx_to_edl(app, llm, edl, plan=plan, product=product)
    edl_mod.save(edl, edl_mod.edl_path_for(out_dir))
    final = out_dir / f"{content_id}_{plan.platform}_video.mp4"
    render.render_edl(app, edl, out_dir, final)
    return {"media_paths": [str(final)]}


_DELIVERY = ("Deep, calm, deliberate — a hard-earned certainty, not shouting. "
             "Leave a beat of silence between sentences. Deliver each line flat "
             "and final, like it is simply true.")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _register_for(plan) -> str:
    """Harsh (discipline) vs hopecore (soft) — read from the plan so the
    strategist/bandit can steer it. Defaults to harsh (the base register)."""
    blob = " ".join(str(getattr(plan, f, "") or "")
                    for f in ("tone", "angle", "topic", "emotional_target")).lower()
    hope = ("hope", "soft", "uplift", "gentle", "warm", "cinematic", "inspir", "gratitude")
    return "hopecore" if any(k in blob for k in hope) else "harsh"


def _quote(app: App, llm: LLM, product: dict, plan, register: str, draft,
           content_id: int) -> "_Quote":
    system = (
        "You write for the 'motivational clips' niche (letterbox quote reels). "
        f"Register: {register.upper()} — "
        + ("harsh, imperative, self-reliance/discipline; punchy and cold."
           if register == "harsh" else
           "hopecore: soft, uplifting, cinematic slow-build; sincere, not corny.")
        + " Second person. Never use 'in today's world', 'game-changer', "
          "'unlock your potential', 'level up', or any author attribution.")
    user = (
        f"Topic/angle: {getattr(plan, 'topic', '')} / {getattr(plan, 'angle', '')}\n"
        f"Seed line (optional, may ignore): {getattr(draft, 'hook', '') or ''}\n\n"
        "Return: (1) quote — one second-person line, <=12 words; "
        "(2) monologue — 3-4 sentences expanding the line for a spoken voiceover.")
    return llm.parse(system, user, _Quote, temperature=0.9,
                     mock_factory=lambda: _mock_quote(register),
                     content_id=content_id, product_id=product["id"])


def _source_broll(app: App, register: str, content_id: int) -> tuple[Path, float]:
    """Pick a query from the register vocabulary, search license-free stock, and
    download the first hit (a real lavfi clip offline). Returns (path, duration)."""
    vocab = _QUERIES[register]
    query = vocab[content_id % len(vocab)]
    items = stock.search_videos(app, query, orientation="portrait", per_page=10)
    if not items:  # provider hiccup — try a generic fallback before giving up
        items = stock.search_videos(app, "cinematic slow motion", orientation="portrait")
    if not items:
        raise RuntimeError(f"no stock b-roll found for motivational clip ({query!r})")
    path = stock.download_video(app, items[0])
    dur = tts.media_duration(path) or float(items[0].get("duration") or 8.0)
    return path, max(dur, 1.0)


def _music_bed(app: App, out_dir: Path, seconds: float) -> Path:
    """Placeholder ambient music bed (see INTEGRATION). Synthesized offline via
    ffmpeg so the hopecore/music lane runs with zero rights exposure until a
    licensed-music sourcing module exists."""
    path = out_dir / "music_bed.m4a"
    # Warm low drone + soft high shimmer, gently faded — an unobtrusive bed.
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=110:duration={seconds:.3f}",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds:.3f}",
        "-filter_complex",
        "[0:a]volume=0.25[a0];[1:a]volume=0.10[a1];"
        f"[a0][a1]amix=inputs=2:normalize=0,afade=t=in:d=1,"
        f"afade=t=out:st={max(seconds - 1.5, 0):.3f}:d=1.5[a]",
        "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"music bed synth failed: {proc.stderr[-400:]}")
    return path


def _handle(product: dict) -> str:
    raw = (product.get("handle") or product.get("id") or product.get("name") or "mark")
    slug = re.sub(r"[^a-z0-9_]+", "", str(raw).lower()) or "mark"
    return f"@{slug}"


def _clean_quote(text: str) -> str:
    q = re.sub(r"\s+", " ", (text or "").strip()).strip('"“”')
    return q or "Nobody is coming to save you. Get up and go."


def _display_quote(text: str) -> str:
    """Uppercase for the bold-sans motivational look, capped at ~12 words."""
    words = text.split()
    if len(words) > 12:
        text = " ".join(words[:12])
    return text.upper()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))
