"""Edit decision list (EDL) — the single assembly representation for video.

Contract 1 of the content-templates build (docs/design/CONTENT-TEMPLATES-BUILD.md):
every video template emits one ``edit.json`` describing the visual timeline
(clips), overlays, captions, and audio tracks; ``media/render.py`` executes it;
the web editor edits it. Captions, overlays, and audio are anchored to the
MASTER (voiceover) timeline and are invariant under visual clip reorder/trim.

Paths in ``src`` fields are relative to the EDL's own directory, or absolute
under ``data/`` (the renderer enforces that — web editors POST these).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPEED_MIN, SPEED_MAX = 0.5, 2.0  # atempo's native range — keeps A/V in lockstep
_MIN_TRANSITION = 0.05           # below this a crossfade is a plain cut


class Canvas(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    background: str = "#000000"

    @field_validator("width", "height", "fps")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("canvas dimensions/fps must be positive")
        return v


class Window(BaseModel):
    """Placement rect for ``fit: window`` (the letterbox composer)."""

    x: int = 0
    y: int = 420
    w: int = 1080
    h: int = 1080


class Transition(BaseModel):
    """Transition INTO the next clip."""

    type: Literal["crossfade"] = "crossfade"
    duration: float = 0.4

    @field_validator("duration")
    @classmethod
    def _sane(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("transition duration must be > 0")
        return min(v, 2.0)


class Clip(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    src: str
    in_: float = Field(0.0, alias="in")
    out: float
    order: int = 0
    fit: Literal["cover", "contain", "window"] = "cover"
    window: Optional[Window] = None
    speed: float = 1.0
    mute: bool = True
    transition: Optional[Transition] = None

    @field_validator("speed")
    @classmethod
    def _clamp_speed(cls, v: float) -> float:
        return min(max(float(v), SPEED_MIN), SPEED_MAX)

    @model_validator(mode="after")
    def _sane_times(self) -> "Clip":
        if self.in_ < 0:
            raise ValueError(f"clip {self.id}: in < 0")
        if self.out <= self.in_:
            raise ValueError(f"clip {self.id}: out ({self.out}) must be > in ({self.in_})")
        if self.fit == "window" and self.window is None:
            self.window = Window()
        return self


class Overlay(BaseModel):
    kind: Literal["png", "text"]
    src: Optional[str] = None      # png
    text: Optional[str] = None     # text
    t0: float = 0.0
    t1: float = 0.0
    x: Optional[int] = None
    y: Optional[int] = None
    y_frac: Optional[float] = None
    style: Optional[str] = None    # text style preset (render._TEXT_STYLES)

    @model_validator(mode="after")
    def _sane(self) -> "Overlay":
        if self.kind == "png" and not self.src:
            raise ValueError("png overlay needs a src")
        if self.kind == "text" and not (self.text or "").strip():
            raise ValueError("text overlay needs text")
        if self.t0 < 0 or self.t1 <= self.t0:
            raise ValueError(f"overlay times insane: t0={self.t0} t1={self.t1}")
        return self


class CaptionWord(BaseModel):
    w: str
    t0: float
    t1: float
    emphasize: bool = False
    emoji: Optional[str] = None


class CaptionEvent(BaseModel):
    text: str
    t0: float
    t1: float


class Captions(BaseModel):
    mode: Literal["karaoke", "static_scene", "seam_band", "none"] = "none"
    style: str = "hormozi"
    words: list[CaptionWord] = Field(default_factory=list)
    events: list[CaptionEvent] = Field(default_factory=list)


class AudioTrack(BaseModel):
    src: Optional[str] = None      # None only for kind=original (clips' own audio)
    kind: Literal["voiceover", "music", "original", "sfx"]
    gain_db: float = 0.0
    duck_db: Optional[float] = None  # music only: how far to duck under voiceover
    t0: float = 0.0
    label: Optional[str] = None    # sfx: which effect (for the editor UI / audit)

    @model_validator(mode="after")
    def _sane(self) -> "AudioTrack":
        if self.kind not in ("original",) and not self.src:
            raise ValueError(f"{self.kind} audio track needs a src")
        if self.t0 < 0:
            raise ValueError("audio t0 < 0")
        return self


class EDL(BaseModel):
    version: int = 1
    ai_generated: bool = False
    canvas: Canvas = Field(default_factory=Canvas)
    clips: list[Clip]
    overlays: list[Overlay] = Field(default_factory=list)
    captions: Captions = Field(default_factory=Captions)
    audio: list[AudioTrack] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sane(self) -> "EDL":
        if not self.clips:
            raise ValueError("EDL needs at least one clip")
        self.clips.sort(key=lambda c: c.order)
        for c in self.clips:
            if c.fit == "window" and c.window is not None:
                win = c.window
                if (win.w <= 0 or win.h <= 0 or win.x < 0 or win.y < 0
                        or win.x + win.w > self.canvas.width
                        or win.y + win.h > self.canvas.height):
                    raise ValueError(f"clip {c.id}: window rect outside canvas")
        return self


# --------------------------------------------------------------------------- #
# Duration math (shared with the renderer so both always agree)
# --------------------------------------------------------------------------- #
def clip_seconds(clip: Clip) -> float:
    """Effective on-timeline duration of one clip (trim / speed)."""
    return (clip.out - clip.in_) / clip.speed


def transition_seconds(edl: EDL) -> list[float]:
    """Clamped crossfade duration at each seam (len = clips - 1). A transition
    longer than either neighbor collapses toward a cut — xfade needs both
    inputs to outlive the overlap."""
    durs = [clip_seconds(c) for c in edl.clips]
    out = []
    for i in range(len(edl.clips) - 1):
        t = edl.clips[i].transition
        d = 0.0
        if t is not None:
            d = min(t.duration, durs[i] - _MIN_TRANSITION, durs[i + 1] - _MIN_TRANSITION)
        out.append(d if d >= _MIN_TRANSITION else 0.0)
    return out


def visual_duration(edl: EDL) -> float:
    """Length of the rendered visual timeline (crossfades overlap the seams)."""
    return sum(clip_seconds(c) for c in edl.clips) - sum(transition_seconds(edl))


def total_duration(edl: EDL) -> float:
    """Master-timeline extent: visuals plus any overlay/caption that outlives
    them. Audio file lengths aren't probed here — the renderer clamps audio to
    the visual timeline anyway."""
    ends = [visual_duration(edl)]
    ends += [o.t1 for o in edl.overlays]
    ends += [w.t1 for w in edl.captions.words]
    ends += [e.t1 for e in edl.captions.events]
    return max(ends)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def edl_path_for(out_dir: Path) -> Path:
    """Canonical EDL location inside a content's media dir."""
    return Path(out_dir) / "edit.json"


def load(path: Path) -> EDL:
    return EDL.model_validate_json(Path(path).read_text())


def save(edl: EDL, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = edl.model_dump(by_alias=True, exclude_none=True)
    path.write_text(json.dumps(payload, indent=2))
    return path
