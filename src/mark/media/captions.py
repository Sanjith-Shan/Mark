"""Word-level captions for videos — back-compat facade.

The caption engine now lives in two focused modules:

  * :mod:`mark.media.align` — word timing (forced alignment of known scripts
    via faster-whisper/whisperx, OpenAI whisper-1 fallback, offline even
    spacing) plus :func:`align.verify_sync` QA.
  * :mod:`mark.media.ass_captions` — EDL captions block → styled ASS file
    (karaoke / static_scene / seam_band modes, YAML style presets, vendored
    fonts).

This module keeps the original public API (``word_timestamps``, ``build_ass``,
``karaoke_events``) so existing callers (``media/video.py``) work unchanged;
everything delegates to the new modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..app import App
from ..llm import LLM
from . import align as align_mod
from . import ass_captions as ass_mod

Word = tuple[str, float, float]  # (text, start, end)

Event = tuple[float, float, str]  # (start, end, rendered ASS text)


def word_timestamps(app: App, audio_path: Path, script: str, duration: float,
                    llm: Optional[LLM] = None) -> list[Word]:
    """Legacy signature; delegates to :func:`mark.media.align.word_timestamps`
    (``duration`` is only a hint for the offline even-spacing fallback)."""
    return align_mod.word_timestamps(app, audio_path, script, llm=llm,
                                     duration=duration)


def karaoke_events(words: list[Word], chunk: int = 3,
                   highlight: str = "&H0000FFFF") -> list[Event]:
    """One dialogue event per word state — see
    :func:`mark.media.ass_captions.karaoke_events`."""
    return ass_mod.karaoke_events(words, chunk=chunk, highlight=highlight)


def build_ass(words: list[Word], width: int, height: int, out_path: Path,
              chunk: int = 3, highlight: str = "&H0000FFFF") -> Path:
    """Write an ASS subtitle file with the current word highlighted.

    Delegates to :func:`mark.media.ass_captions.build_ass` with an inline style
    that preserves the legacy behavior (verbatim word case, caller-chosen
    highlight color and chunk size) while gaining the word-pop animation and
    the upgraded font stack.
    """
    edl_captions = {
        "mode": "karaoke",
        "style": {
            "font_size": 111,  # ≈ legacy int(height * 0.058) at 1920
            "uppercase": False,
            "chunk_size": chunk,
            "highlight_color": highlight,
            "outline": 4,
        },
        "words": [{"w": w, "t0": s, "t1": e} for w, s, e in words],
    }
    return ass_mod.build_ass(edl_captions, {"width": width, "height": height},
                             Path(out_path))
