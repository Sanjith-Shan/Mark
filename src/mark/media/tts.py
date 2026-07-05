"""Text-to-speech: OpenAI TTS (default) or ElevenLabs, with an offline path.

Returns ``(audio_path, duration_seconds)``. Offline, it writes a real silent WAV
sized to the estimated narration length so the rest of the video assembly (which
keys off audio duration) works unchanged.
"""

from __future__ import annotations

import struct
import subprocess
import wave
from pathlib import Path

from ..app import App
from ..llm import LLM, log_external_cost

WORDS_PER_SECOND = 2.6  # average narration pace


def estimate_duration(text: str) -> float:
    words = max(len(text.split()), 1)
    return max(3.0, min(words / WORDS_PER_SECOND, 180.0))


def synthesize(app: App, llm: LLM, text: str, out_path: Path, *,
               voice: str | None = None, instructions: str | None = None,
               content_id=None, product_id=None) -> tuple[Path, float]:
    """``instructions`` steers delivery (gpt-4o-mini-tts supports it) — comedic
    timing is half the joke, so humorous scripts pass a deadpan/pause brief."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = app.settings.media.tts_provider
    voice = voice or app.settings.media.tts_voice

    # ElevenLabs (optional, real only).
    if provider == "elevenlabs" and not app.is_mock("elevenlabs"):
        return _elevenlabs(app, text, out_path, voice, content_id, product_id)

    # OpenAI TTS.
    if not app.is_mock("openai"):
        model = getattr(app.settings.media, "tts_model", None) or "gpt-4o-mini-tts"
        mp3 = out_path.with_suffix(".mp3")
        kwargs = {"model": model, "voice": voice, "input": text}
        if instructions and not model.startswith("tts-1"):  # tts-1* rejects it
            kwargs["instructions"] = instructions
        with llm.client().audio.speech.with_streaming_response.create(**kwargs) as resp:
            resp.stream_to_file(str(mp3))
        log_external_cost(app, "openai", "tts", model, units=len(text),
                          content_id=content_id, product_id=product_id)
        return mp3, media_duration(mp3) or estimate_duration(text)

    # Offline: silent WAV of the estimated length.
    duration = estimate_duration(text)
    wav = out_path.with_suffix(".wav")
    _silent_wav(wav, duration)
    log_external_cost(app, "openai", "tts", "mock-silence", units=len(text),
                      content_id=content_id, product_id=product_id, mocked=True)
    return wav, duration


def _elevenlabs(app: App, text: str, out_path: Path, voice: str,
                content_id, product_id) -> tuple[Path, float]:
    import httpx

    # ElevenLabs multilingual v2. The API requires a voice ID in the URL, but
    # `voice` may be an ID, an ElevenLabs voice NAME (per-character voices are
    # configured by name), or an OpenAI-style name like "onyx" leaking from the
    # global default. IDs pass straight through; names are resolved via the
    # voices API; Rachel is only the last resort — always forcing her destroyed
    # per-character voice identity.
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    voice_id = None
    if voice:
        if len(voice) >= 20 and voice.isalnum():
            voice_id = voice  # already an ElevenLabs voice ID
        else:
            voice_id = _resolve_voice_id(app, voice)
    voice_id = voice_id or DEFAULT_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": app.keys.elevenlabs, "Content-Type": "application/json"}
    payload = {"text": text, "model_id": "eleven_multilingual_v2"}
    mp3 = out_path.with_suffix(".mp3")
    with httpx.Client(timeout=120) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        mp3.write_bytes(resp.content)
    log_external_cost(app, "elevenlabs", "tts", "eleven_multilingual_v2", units=len(text),
                      content_id=content_id, product_id=product_id)
    return mp3, media_duration(mp3) or estimate_duration(text)


def _resolve_voice_id(app: App, name: str) -> str | None:
    """Resolve an ElevenLabs voice name to its ID (case-insensitive) via
    GET /v1/voices. Returns None when the name doesn't match any voice
    (e.g. an OpenAI voice name like "onyx")."""
    import httpx

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get("https://api.elevenlabs.io/v1/voices",
                              headers={"xi-api-key": app.keys.elevenlabs})
            resp.raise_for_status()
            for v in resp.json().get("voices", []):
                if (v.get("name") or "").strip().lower() == name.strip().lower():
                    return v.get("voice_id")
    except Exception:
        pass
    return None


def _silent_wav(path: Path, seconds: float, rate: int = 44100) -> None:
    n = int(seconds * rate)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * n)


def media_duration(path: Path) -> float:
    """Probe duration via ffprobe; returns 0.0 if unavailable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip() or 0)
    except Exception:
        return 0.0
