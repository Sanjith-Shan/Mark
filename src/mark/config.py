"""Configuration: Pydantic models + YAML/.env loading.

All global settings come from ``config/default.yaml``; per-product settings come
from ``config/products/*.yaml`` (and the ``products`` table once added). Secrets
come from ``.env`` / environment variables and are never stored in YAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Pydantic config models (mirror the YAML files)
# --------------------------------------------------------------------------- #
class _Base(BaseModel):
    # Forgiving by default so adding keys to YAML never crashes an old build.
    model_config = ConfigDict(extra="allow")


class UploadPostConfig(_Base):
    profile_username: str = "my-profile"


class LLMConfig(_Base):
    text_model: str = "gpt-5.4-mini"
    judge_model: str = "gpt-5.4-nano"
    embedding_model: str = "text-embedding-3-small"
    variants: int = 1
    self_critique: bool = True
    novelty_threshold: float = 0.93
    novelty_lookback: int = 40


class PlatformConfig(_Base):
    enabled: bool = True
    max_posts_per_day: int = 1
    content_types: list[str] = Field(default_factory=lambda: ["text"])
    optimal_times: list[str] = Field(default_factory=lambda: ["12:00"])
    hashtag_count: int = 3
    privacy_level: Optional[str] = None


class MediaConfig(_Base):
    image_model: str = "gpt-image-1.5"
    image_quality: str = "medium"
    video_model: str = "fal-ai/kling-video/v3/standard/text-to-video"
    video_fallback: str = "fal-ai/wan/v2.7/text-to-video"
    video_duration: int = 8
    video_resolution: str = "720p"
    tts_provider: str = "openai"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "onyx"


class SchedulingConfig(_Base):
    timezone: str = "America/Los_Angeles"
    content_generation_cron: str = "0 6 * * *"
    analytics_collection_cron: str = "0 */6 * * *"
    trend_monitoring_cron: str = "0 8,16 * * *"
    feedback_loop_cron: str = "0 0 * * 0"
    posting_jitter_minutes: int = 15


class ApprovalConfig(_Base):
    auto_approve: bool = False
    auto_approve_types: list[str] = Field(default_factory=list)


class Settings(_Base):
    """The whole of ``default.yaml``."""

    upload_post: UploadPostConfig = Field(default_factory=UploadPostConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    platforms: dict[str, PlatformConfig] = Field(default_factory=dict)
    media: MediaConfig = Field(default_factory=MediaConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)

    def enabled_platforms(self) -> list[str]:
        return [name for name, p in self.platforms.items() if p.enabled]

    def platform(self, name: str) -> PlatformConfig:
        return self.platforms.get(name, PlatformConfig())


class ProductConfig(_Base):
    """A single product YAML (used to seed the ``products`` table)."""

    id: str
    name: str
    description: str
    target_audience: str
    brand_voice: str
    website_url: Optional[str] = None
    platforms: list[str] = Field(default_factory=list)
    posting_cadence: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Paths + secrets
# --------------------------------------------------------------------------- #
class Paths:
    """Resolves all on-disk locations relative to a single home directory.

    Home defaults to the current working directory, overridable with ``MARK_HOME``.
    """

    def __init__(self, home: Optional[Path] = None):
        self.home = Path(home or os.environ.get("MARK_HOME") or Path.cwd()).resolve()
        self.config_dir = self.home / "config"
        self.products_dir = self.config_dir / "products"
        self.default_config = self.config_dir / "default.yaml"
        self.data_dir = self.home / "data"
        self.media_dir = self.data_dir / "media"
        self.winners_dir = self.data_dir / "winners"
        self.db_path = self.data_dir / "mark.db"

    def ensure(self) -> None:
        for d in (self.config_dir, self.products_dir, self.data_dir,
                  self.media_dir, self.winners_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_dotenv(home: Path) -> None:
    """Load ``.env`` into ``os.environ``.

    Uses python-dotenv when available, otherwise a minimal built-in parser so the
    tool has no hard dependency on it.
    """
    env_path = home / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv as _load  # type: ignore

        _load(env_path)
        return
    except Exception:
        pass
    # Minimal fallback parser.
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Don't clobber values already exported in the shell.
        if key and key not in os.environ:
            os.environ[key] = value


class Keys:
    """Snapshot of which provider credentials are available."""

    def __init__(self) -> None:
        self.openai = os.environ.get("OPENAI_API_KEY") or None
        self.fal = os.environ.get("FAL_KEY") or None
        self.upload_post = os.environ.get("UPLOAD_POST_API_KEY") or None
        self.elevenlabs = os.environ.get("ELEVENLABS_API_KEY") or None


def load_settings(paths: Paths) -> Settings:
    """Parse ``default.yaml`` into a validated :class:`Settings`."""
    if paths.default_config.exists():
        raw = yaml.safe_load(paths.default_config.read_text()) or {}
    else:
        raw = {}
    return Settings.model_validate(raw)


def load_product_yaml(path: Path) -> ProductConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return ProductConfig.model_validate(raw)
