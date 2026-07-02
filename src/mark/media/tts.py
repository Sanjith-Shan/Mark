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
               voice: str | None = None, content_id=None, product_id=None) -> tuple[Path, float]:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = app.settings.media.tts_provider
    voice = voice or app.settings.media.tts_voice

    # ElevenLabs (optional, real only).
    if provider == "elevenlabs" and not app.is_mock("elevenlabs"):
        return _elevenlabs(app, text, out_path, voice, content_id, product_id)

    # OpenAI TTS.
    if not app.is_mock("openai"):
        mp3 = out_path.with_suffix(".mp3")
        with llm.client().audio.speech.with_streaming_response.create(
            model="tts-1-hd", voice=voice, input=text
        ) as resp:
            resp.stream_to_file(str(mp3))
        log_external_cost(app, "openai", "tts", "tts-1-hd", units=len(text),
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

    # ElevenLabs multilingual v2; `voice` may be a voice id.
    voice_id = voice if voice and voice[0].isalnum() and len(voice) > 10 else "Rachel"
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
