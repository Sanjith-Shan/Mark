"""Word-level timing: forced alignment of known scripts + sync verification.

Timing sources, best first:

  1. whisperx.align() — wav2vec2 phoneme forced alignment of the KNOWN script
     (only when whisperx happens to be importable; it is not a hard dep).
  2. faster-whisper (installed) with ``word_timestamps=True``. When the script
     is known, the transcribed timings are SNAPPED onto the script tokens via
     fuzzy monotonic alignment — the display text is always the script,
     verbatim; only the timings come from ASR.
  3. OpenAI whisper-1 ``verbose_json`` word timestamps (the only OpenAI model
     that returns them, mid-2026) — used when local models fail and a key is live.
  4. Even spacing weighted by word length — fully offline, deterministic.

``App.force_mock`` (tests, --dry-run) skips straight to (4) so the mock path is
fast and deterministic. A missing OpenAI key does NOT disable (1)/(2) — they
are local.
"""

from __future__ import annotations

import logging
import re
import statistics
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from ..app import App
from ..llm import LLM

log = logging.getLogger("mark.align")

Word = tuple[str, float, float]  # (text, start, end)

_WHISPER_MODEL = None  # cached faster-whisper model (loads once per process)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def word_timestamps(app: App, audio_path: Path, script: Optional[str] = None, *,
                    llm: Optional[LLM] = None,
                    duration: Optional[float] = None) -> list[Word]:
    """Word-level timings for ``audio_path``.

    When ``script`` is given it is ground truth: the returned words are the
    script tokens verbatim, with timings aligned to the audio. Without a
    script, ASR output is returned as-is (empty list if no ASR path worked).
    ``duration`` is only a hint for the offline even-spacing fallback.
    """
    audio_path = Path(audio_path)
    tokens = [w for w in (script or "").split() if w.strip()]

    if not app.force_mock and audio_path.exists():
        raw = None
        if tokens:
            raw = _whisperx_words(audio_path, script)
        if not raw:
            raw = _faster_whisper_words(audio_path)
        if not raw and not app.is_mock("openai"):
            raw = _openai_words(app, audio_path, llm)
        if raw:
            return snap_to_script(raw, tokens) if tokens else raw

    if not tokens:
        return []
    return even_spacing(tokens, _fallback_duration(audio_path, tokens, duration))


def verify_sync(app: App, video_path: Path, words: list[Word]) -> dict:
    """Re-align the rendered video's audio against the caption schedule.

    Extracts the audio track, re-runs :func:`word_timestamps` with the same
    script, and compares per-word start times. Median offset > 80ms almost
    always means the voiceover was muxed with an offset or the video was
    trimmed after alignment.
    """
    video_path = Path(video_path)
    if not words:
        return {"median_offset_ms": 0.0, "max_offset_ms": 0.0, "passed": False,
                "word_count": 0, "method": "none"}
    script = " ".join(w for w, _s, _e in words)
    with tempfile.TemporaryDirectory(prefix="mark-sync-") as tmp:
        wav = Path(tmp) / "audio.wav"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1",
             "-ar", "16000", str(wav)],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not wav.exists():
            return {"median_offset_ms": None, "max_offset_ms": None, "passed": False,
                    "word_count": len(words), "method": "extract_failed"}
        realigned = word_timestamps(app, wav, script)

    offsets = [abs(b[1] - a[1]) * 1000.0
               for a, b in zip(words, realigned)]
    if not offsets:
        return {"median_offset_ms": None, "max_offset_ms": None, "passed": False,
                "word_count": len(words), "method": "realign_failed"}
    median = statistics.median(offsets)
    peak = max(offsets)
    return {
        "median_offset_ms": round(median, 1),
        "max_offset_ms": round(peak, 1),
        "passed": bool(median < 80 and peak < 200),
        "word_count": len(words),
        "method": "mock" if app.force_mock else "realign",
    }


# --------------------------------------------------------------------------- #
# Alignment sources
# --------------------------------------------------------------------------- #
def _whisperx_words(audio_path: Path, script: str) -> Optional[list[Word]]:
    """Forced alignment of the known script via whisperx (optional upgrade)."""
    try:
        import whisperx  # type: ignore
    except Exception:
        return None
    try:
        audio = whisperx.load_audio(str(audio_path))
        dur = len(audio) / 16000.0
        model_a, meta = whisperx.load_align_model(language_code="en", device="cpu")
        result = whisperx.align([{"text": script, "start": 0.0, "end": dur}],
                                model_a, meta, audio, "cpu")
        out: list[Word] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    out.append((str(w["word"]).strip(), float(w["start"]), float(w["end"])))
        return out or None
    except Exception as exc:
        log.debug("whisperx alignment failed: %s", exc)
        return None


def _faster_whisper_words(audio_path: Path) -> Optional[list[Word]]:
    """Transcribe locally with faster-whisper, returning word timings."""
    try:
        from faster_whisper import WhisperModel  # lazy — ~145MB model on first use
    except Exception:
        return None
    global _WHISPER_MODEL
    try:
        if _WHISPER_MODEL is None:
            _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
        try:
            segments, _info = _WHISPER_MODEL.transcribe(
                str(audio_path), word_timestamps=True, vad_filter=True)
            out = [(w.word.strip(), float(w.start), float(w.end))
                   for seg in segments for w in (seg.words or [])]
        except Exception:
            # VAD needs onnxruntime; retry without it rather than giving up.
            segments, _info = _WHISPER_MODEL.transcribe(
                str(audio_path), word_timestamps=True, vad_filter=False)
            out = [(w.word.strip(), float(w.start), float(w.end))
                   for seg in segments for w in (seg.words or [])]
        return out or None
    except Exception as exc:
        log.debug("faster-whisper failed: %s", exc)
        return None


def _openai_words(app: App, audio_path: Path, llm: Optional[LLM]) -> Optional[list[Word]]:
    """Word timestamps via OpenAI whisper-1 (verbose_json)."""
    try:
        client = (llm or LLM(app)).client()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json",
                timestamp_granularities=["word"])
        out: list[Word] = []
        for w in getattr(resp, "words", None) or []:
            if isinstance(w, dict):
                out.append((str(w["word"]).strip(), float(w["start"]), float(w["end"])))
            else:
                out.append((str(w.word).strip(), float(w.start), float(w.end)))
        return out or None
    except Exception as exc:
        log.debug("openai whisper-1 timestamps failed: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Script snapping (fuzzy monotonic alignment)
# --------------------------------------------------------------------------- #
def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", token.lower())


def snap_to_script(asr_words: list[Word], tokens: list[str]) -> list[Word]:
    """Snap ASR word timings onto the known script tokens.

    The script is ground truth for TEXT (ASR typos never reach the screen);
    ASR is ground truth for TIME. Matched tokens take the ASR timing directly;
    unmatched runs are interpolated between the surrounding anchors, weighted
    by word length. Output is strictly monotonic and non-overlapping.
    """
    if not tokens:
        return []
    if not asr_words:
        return []

    a = [_norm(w) for w, _s, _e in asr_words]
    b = [_norm(t) for t in tokens]
    anchors: dict[int, tuple[float, float]] = {}  # script idx -> (start, end)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            anchors[block.b + k] = (asr_words[block.a + k][1], asr_words[block.a + k][2])

    total_start = asr_words[0][1]
    total_end = max(asr_words[-1][2], total_start + 0.01)

    out: list[Optional[Word]] = [None] * len(tokens)
    for i, tok in enumerate(tokens):
        if i in anchors:
            s, e = anchors[i]
            out[i] = (tok, s, e)

    # Interpolate unmatched runs between anchors (or the audio edges).
    idx = 0
    while idx < len(tokens):
        if out[idx] is not None:
            idx += 1
            continue
        run_start = idx
        while idx < len(tokens) and out[idx] is None:
            idx += 1
        run_end = idx  # exclusive
        left_t = out[run_start - 1][2] if run_start > 0 else total_start
        right_t = out[run_end][1] if run_end < len(tokens) else total_end
        if right_t <= left_t:
            right_t = left_t + 0.05 * (run_end - run_start)
        weights = [max(len(_norm(tokens[k])), 2) for k in range(run_start, run_end)]
        total_w = sum(weights) or 1
        t = left_t
        for k, wt in zip(range(run_start, run_end), weights):
            span = (right_t - left_t) * (wt / total_w)
            out[k] = (tokens[k], t, t + span)
            t += span

    # Enforce monotonic, non-overlapping timings.
    fixed: list[Word] = []
    prev_end = 0.0
    for tok, s, e in out:  # type: ignore[misc]
        s = max(s, prev_end)
        e = max(e, s + 0.01)
        fixed.append((tok, s, e))
        prev_end = e
    return fixed


# --------------------------------------------------------------------------- #
# Offline fallback
# --------------------------------------------------------------------------- #
def even_spacing(tokens: list[str], duration: float) -> list[Word]:
    """Deterministic offline timing: even spacing weighted by word length."""
    if not tokens:
        return []
    weights = [max(len(w), 2) for w in tokens]
    total_w = sum(weights)
    t = 0.0
    out: list[Word] = []
    for w, wt in zip(tokens, weights):
        span = duration * (wt / total_w)
        out.append((w, t, t + span))
        t += span
    return out


def _fallback_duration(audio_path: Path, tokens: list[str],
                       duration: Optional[float]) -> float:
    if duration and duration > 0:
        return float(duration)
    if audio_path.exists():
        from .tts import media_duration

        probed = media_duration(audio_path)
        if probed > 0:
            return probed
    from .tts import estimate_duration

    return estimate_duration(" ".join(tokens))
