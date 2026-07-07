"""ASS subtitle generation for the EDL caption block (Contract 2).

Renders TikTok-style captions as an ASS file that ffmpeg burns in via libass
(``ass=captions.ass:fontsdir=<assets/fonts>``) — one encode, no MoviePy.

Modes (from the EDL ``captions`` block):
  * ``karaoke``      — 2-3 word chunks, one Dialogue event per WORD-STATE; the
    whole chunk pops (``\\t`` scale transform) at each word boundary and the
    active word carries the highlight color.
  * ``static_scene`` — one centered event per ``events[]`` entry (animal-story
    mode), soft fade in/out.
  * ``seam_band``    — karaoke placed in the seam between stacked videos.
  * ``none``         — header only, no events.

Style presets load from ``config/caption_styles/*.yaml`` with hardcoded safe
defaults when files are absent. ASS color footgun: values are ``&HAABBGGRR``
(BGR, not RGB) — gold is ``&H0000D7FF``, not ``&H00FFD700``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

Event = tuple[float, float, str]  # (start, end, rendered ASS text)

# Everything a style can set, with platform-safe defaults. ``y_frac`` 0.64 puts
# the anchor at y=1230 on a 1920 canvas — inside TikTok/Reels/Shorts safe zones
# (clear of the bottom ~324px UI band and the right-side engagement rail).
_BASE_STYLE = {
    "font": "Montserrat ExtraBold",
    "font_size": 84,               # for a 1920-high canvas; scaled for others
    "primary_color": "&H00FFFFFF",   # white (AABBGGRR)
    "highlight_color": "&H0000D7FF", # gold #FFD700 → BGR 00D7FF
    "outline_color": "&H00000000",
    "back_color": "&H64000000",
    "outline": 5,
    "shadow": 2,
    "bold": True,
    "uppercase": True,
    "chunk_size": 3,
    "y_frac": 0.64,          # karaoke anchor (\an5), fraction of canvas height
    "static_y_frac": 0.5,    # static_scene anchor
    "seam_y_frac": 0.5,      # seam_band anchor (the seam between stacked clips)
    "margin_x": 120,         # px side margins → wrap width, safe of side rails
    "pop_scale": 128,        # \fscx/\fscy peak of the word pop
    "emphasize_scale": 140,  # pop peak when the active word is emphasized
    "pop_ms": 120,
    "settle_ms": 220,
    "fade_ms": 120,          # static_scene fade in/out
}

# Shipped presets, mirrored in config/caption_styles/*.yaml — these hardcoded
# copies keep the engine working when the config dir is absent (installed pkg).
DEFAULT_STYLES = {
    "hormozi": {},  # the base style IS the hormozi look
    "clean": {
        "font": "Montserrat ExtraBold", "font_size": 64, "uppercase": False,
        "highlight_color": "&H00FFCC66",  # soft sky blue #66CCFF
        "outline": 3, "shadow": 1, "chunk_size": 2,
        "pop_scale": 112, "emphasize_scale": 120, "y_frac": 0.66,
    },
    "meme": {
        "font": "Anton", "font_size": 96, "uppercase": True,
        "highlight_color": "&H0000FFFF",  # pure yellow
        "outline": 6, "shadow": 2, "chunk_size": 2,
        "pop_scale": 135, "emphasize_scale": 150, "y_frac": 0.60,
    },
}


def fonts_dir() -> Path:
    """Vendored OFL fonts — pass as ``fontsdir`` to the ffmpeg ``ass`` filter."""
    return Path(__file__).resolve().parents[1] / "assets" / "fonts"


# --------------------------------------------------------------------------- #
# Style presets
# --------------------------------------------------------------------------- #
def load_style(style) -> dict:
    """Resolve a style preset name (or inline dict) to a full style mapping."""
    resolved = dict(_BASE_STYLE)
    if isinstance(style, dict):
        resolved.update({k: v for k, v in style.items() if v is not None})
        return resolved
    name = str(style or "hormozi")
    resolved.update(DEFAULT_STYLES.get(name, DEFAULT_STYLES["hormozi"]))
    path = _style_file(name)
    if path is not None:
        try:
            import yaml

            data = yaml.safe_load(path.read_text()) or {}
            resolved.update({k: v for k, v in data.items() if k in _BASE_STYLE})
        except Exception:
            pass  # malformed preset → shipped defaults still render
    return resolved


def available_styles() -> list[str]:
    """Preset names: shipped defaults plus any config/caption_styles/*.yaml."""
    names = set(DEFAULT_STYLES)
    for base in _config_dirs():
        d = base / "caption_styles"
        if d.is_dir():
            names.update(p.stem for p in d.glob("*.yaml"))
    return sorted(names)


def _config_dirs() -> list[Path]:
    dirs = []
    env_home = os.environ.get("MARK_HOME")
    if env_home:
        dirs.append(Path(env_home) / "config")
    dirs.append(Path.cwd() / "config")
    dirs.append(Path(__file__).resolve().parents[3] / "config")  # repo checkout
    return dirs


def _style_file(name: str) -> Optional[Path]:
    for base in _config_dirs():
        p = base / "caption_styles" / f"{name}.yaml"
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_ass(edl_captions: dict, canvas: dict, out_path: Path) -> Path:
    """Render the EDL ``captions`` block to an ASS file.

    ``edl_captions``: ``{"mode", "style", "words": [{"w","t0","t1","emphasize",
    "emoji"}], "events": [{"text","t0","t1"}]}`` (words also accepted as
    ``(text, start, end)`` tuples). ``canvas``: ``{"width", "height", ...}``.
    """
    out_path = Path(out_path)
    width = int(canvas.get("width", 1080))
    height = int(canvas.get("height", 1920))
    mode = (edl_captions or {}).get("mode", "karaoke")
    style = load_style((edl_captions or {}).get("style", "hormozi"))
    font_size = int(round(style["font_size"] * height / 1920))

    lines: list[str] = []
    if mode in ("karaoke", "seam_band"):
        y_frac = style["seam_y_frac"] if mode == "seam_band" else style["y_frac"]
        words = [_as_word(w) for w in (edl_captions.get("words") or [])]
        for start, end, text in _karaoke_state_events(
                words, style, x=width // 2, y=int(round(y_frac * height))):
            lines.append(_dialogue(start, end, text))
    elif mode == "static_scene":
        x, y = width // 2, int(round(style["static_y_frac"] * height))
        fade = int(style["fade_ms"])
        for ev in (edl_captions.get("events") or []):
            text = _display(str(ev.get("text", "")), style)
            prefix = rf"{{\pos({x},{y})\fad({fade},{fade})}}"
            lines.append(_dialogue(float(ev.get("t0", 0)), float(ev.get("t1", 0)),
                                   prefix + text))
    # mode "none" (or unknown): header only.

    header = _header(width, height, style, font_size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(lines) + ("\n" if lines else ""))
    return out_path


def karaoke_events(words: list[tuple[str, float, float]], chunk: int = 3,
                   highlight: str = "&H0000FFFF") -> list[Event]:
    """Plain word-state events (legacy shape — no positioning/animation tags).

    One dialogue event per word state: the chunk renders in the primary color
    and ONLY the word whose timestamp is live carries the highlight override.
    Plain ``\\k`` karaoke is wrong here — it paints the *unspoken* words in the
    secondary color, which reads inverted on screen.
    """
    hi = _inline_color(highlight)
    white = "&HFFFFFF&"
    events: list[Event] = []
    for group in _chunks(words, chunk):
        for j, (_w, ws, we) in enumerate(group):
            end = group[j + 1][1] if j + 1 < len(group) else we
            parts = []
            for k, (w, _s, _e) in enumerate(group):
                text = _escape(w)
                parts.append(r"{\c%s}%s{\c%s}" % (hi, text, white) if k == j else text)
            events.append((ws, end, " ".join(parts)))
    return events


# --------------------------------------------------------------------------- #
# Rendering internals
# --------------------------------------------------------------------------- #
def _as_word(w) -> dict:
    if isinstance(w, dict):
        return {"w": str(w.get("w", "")), "t0": float(w.get("t0", 0.0)),
                "t1": float(w.get("t1", 0.0)),
                "emphasize": bool(w.get("emphasize", False)),
                "emoji": w.get("emoji") or None}
    text, t0, t1 = w
    return {"w": str(text), "t0": float(t0), "t1": float(t1),
            "emphasize": False, "emoji": None}


def _chunks(seq: list, size: int) -> list[list]:
    size = max(int(size), 1)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _karaoke_state_events(words: list[dict], style: dict, x: int, y: int) -> list[Event]:
    """One event per word-state; the whole chunk pops at each word boundary and
    the active word is highlighted. Emphasized words keep the highlight color
    in every state and pop bigger while active."""
    hi = _inline_color(style["highlight_color"])
    primary = _inline_color(style["primary_color"])
    pop_ms, settle_ms = int(style["pop_ms"]), int(style["settle_ms"])
    events: list[Event] = []
    for group in _chunks(words, style["chunk_size"]):
        for j, active in enumerate(group):
            # Hold each state until the next word starts so nothing flickers.
            end = group[j + 1]["t0"] if j + 1 < len(group) else active["t1"]
            scale = int(style["emphasize_scale"] if active["emphasize"]
                        else style["pop_scale"])
            prefix = (rf"{{\pos({x},{y})"
                      rf"\t(0,{pop_ms},\fscx{scale}\fscy{scale})"
                      rf"\t({pop_ms},{settle_ms},\fscx100\fscy100)}}")
            parts = []
            for k, word in enumerate(group):
                text = _display(word["w"], style)
                if word["emoji"]:
                    text += f" {word['emoji']}"
                if k == j or word["emphasize"]:
                    parts.append(r"{\c%s}%s{\c%s}" % (hi, text, primary))
                else:
                    parts.append(text)
            events.append((active["t0"], end, prefix + " ".join(parts)))
    return events


def _header(width: int, height: int, style: dict, font_size: int) -> str:
    bold = -1 if style.get("bold", True) else 0
    margin_x = int(style["margin_x"])
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mark,{style['font']},{font_size},{style['primary_color']},{style['primary_color']},{style['outline_color']},{style['back_color']},{bold},0,0,0,100,100,0,0,1,{int(style['outline'])},{int(style['shadow'])},5,{margin_x},{margin_x},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _dialogue(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ts(start)},{_ts(end)},Mark,,0,0,0,,{text}"


def _display(text: str, style: dict) -> str:
    text = _escape(text.strip())
    return text.upper() if style.get("uppercase") else text


def _inline_color(style_color: str) -> str:
    """Convert a style color (&HAABBGGRR) to an inline override (&HBBGGRR&)."""
    digits = "".join(c for c in str(style_color) if c in "0123456789abcdefABCDEF")
    return f"&H{digits[-6:]}&"


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\\", "/")


def _ts(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"
