"""Word-level captions for videos.

Timestamps come from whisper-timestamped when installed + a real voiceover is
present; otherwise they're estimated by distributing words evenly across the audio
duration. Rendering produces an ASS subtitle file with TikTok-style karaoke (2-3
words at a time, current word highlighted), which ffmpeg burns in via the
``subtitles`` filter — no moviepy dependency required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..app import App

Word = tuple[str, float, float]  # (text, start, end)


def word_timestamps(app: App, audio_path: Path, script: str, duration: float) -> list[Word]:
    words = [w for w in script.split() if w.strip()]
    if not words:
        return []

    # Try whisper-timestamped for real, accurate alignment.
    if not app.is_mock("openai"):
        aligned = _whisper_timestamps(audio_path)
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


def build_ass(words: list[Word], width: int, height: int, out_path: Path,
              chunk: int = 3, highlight: str = "&H0000FFFF") -> Path:
    """Write an ASS subtitle file with karaoke word highlighting.

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
Style: Mark,Arial,{font_size},&H00FFFFFF,{highlight},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        start = group[0][1]
        end = group[-1][2]
        # Karaoke: \k is in centiseconds; highlight each word for its own span.
        text = ""
        for (w, ws, we) in group:
            cs = max(int((we - ws) * 100), 1)
            text += r"{\k%d}%s " % (cs, _escape(w))
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Mark,,0,0,0,,{text.strip()}")

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
