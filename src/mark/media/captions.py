"""Word-level captions for videos.

Timestamp sources, best first: whisper-timestamped (local alignment) when
installed, OpenAI's hosted transcription API when a key is live, and finally
even spacing weighted by word length. Rendering produces an ASS subtitle file
with TikTok-style karaoke (2-3 words at a time, ONLY the currently-spoken word
highlighted), which ffmpeg burns in via the ``subtitles`` filter — no moviepy
dependency required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..app import App
from ..llm import LLM

Word = tuple[str, float, float]  # (text, start, end)

Event = tuple[float, float, str]  # (start, end, rendered ASS text)


def word_timestamps(app: App, audio_path: Path, script: str, duration: float,
                    llm: Optional[LLM] = None) -> list[Word]:
    words = [w for w in script.split() if w.strip()]
    if not words:
        return []

    if not app.is_mock("openai"):
        # Try whisper-timestamped for real, accurate alignment.
        aligned = _whisper_timestamps(audio_path)
        # Not installed / failed → OpenAI's transcription API still gives real
        # word timings; even spacing is only the last resort.
        if not aligned:
            aligned = _openai_timestamps(app, audio_path, llm)
        if aligned:
            return aligned

    # Estimate: even spacing across the audio, weighted slightly by word length.
    weights = [max(len(w), 2) for w in words]
    total_w = sum(weights)
    t = 0.0
    out: list[Word] = []
    for w, wt in zip(words, weights):
        span = duration * (wt / total_w)
        out.append((w, t, t + span))
        t += span
    return out


def _whisper_timestamps(audio_path: Path) -> Optional[list[Word]]:
    try:
        import whisper_timestamped as whisper  # type: ignore

        model = whisper.load_model("base")
        result = whisper.transcribe(model, str(audio_path))
        out: list[Word] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                out.append((w["text"].strip(), float(w["start"]), float(w["end"])))
        return out or None
    except Exception:
        return None


def _openai_timestamps(app: App, audio_path: Path, llm: Optional[LLM]) -> Optional[list[Word]]:
    """Word timestamps via OpenAI's transcription API (whisper-1)."""
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
    except Exception:
        return None


def karaoke_events(words: list[Word], chunk: int = 3,
                   highlight: str = "&H0000FFFF") -> list[Event]:
    """One dialogue event per word state: the chunk renders white and ONLY the
    word whose timestamp is live carries the highlight color (inline override).

    Plain ``\\k`` karaoke is wrong here — it paints the *unspoken* words in the
    secondary color and the spoken ones in the primary, which reads inverted
    on screen.
    """
    hi = _inline_color(highlight)
    white = "&HFFFFFF&"
    events: list[Event] = []
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        for j, (_w, ws, we) in enumerate(group):
            # Hold each state until the next word starts so nothing flickers.
            end = group[j + 1][1] if j + 1 < len(group) else we
            parts = []
            for k, (w, _s, _e) in enumerate(group):
                text = _escape(w)
                parts.append(r"{\c%s}%s{\c%s}" % (hi, text, white) if k == j else text)
            events.append((ws, end, " ".join(parts)))
    return events


def _inline_color(style_color: str) -> str:
    """Convert a style color (&HAABBGGRR) to an inline override (&HBBGGRR&)."""
    digits = "".join(c for c in style_color if c in "0123456789abcdefABCDEF")
    return f"&H{digits[-6:]}&"


def build_ass(words: list[Word], width: int, height: int, out_path: Path,
              chunk: int = 3, highlight: str = "&H0000FFFF") -> Path:
    """Write an ASS subtitle file with the current word highlighted.

    Colors are ASS BGR hex. Default highlight is yellow; base text is white with a
    thick black outline. Positioned in the lower-center third.
    """
    out_path = Path(out_path)
    font_size = int(height * 0.058)
    margin_v = int(height * 0.28)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mark,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for start, end, text in karaoke_events(words, chunk=chunk, highlight=highlight):
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Mark,,0,0,0,,{text}")

    out_path.write_text(header + "\n".join(lines) + "\n")
    return out_path


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\\", "/")


def _ts(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"
