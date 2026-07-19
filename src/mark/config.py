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
    video_i2v_model: str = "fal-ai/kling-video/v3/standard/image-to-video"  # character consistency
    video_duration: int = 8
    video_resolution: str = "720p"
    tts_provider: str = "openai"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "onyx"
    # Clip-economy templates.
    sfx_enabled: bool = True                # auto-place sound effects on every video EDL
    avatar_model: str = "fal-ai/kling-video/ai-avatar/v2/standard"       # ambassador talking-head
    broll_ref_model: str = "fal-ai/kling-video/o3/pro/reference-to-video"  # ambassador b-roll
    identity_image_model: str = "fal-ai/nano-banana-pro/edit"            # identity-pack stills
    identity_lora_trainer: str = "fal-ai/flux-lora-portrait-trainer"     # identity LoRA mint


class SchedulingConfig(_Base):
    timezone: str = "America/Los_Angeles"
    content_generation_cron: str = "0 6 * * *"
    analytics_collection_cron: str = "0 */6 * * *"
    trend_monitoring_cron: str = "0 8,16 * * *"
    feedback_loop_cron: str = "0 0 * * 0"
    posting_jitter_minutes: int = 15


class ApprovalConfig(_Base):
    """Autonomy is earned, not toggled. Modes:

    manual     — everything waits for human approval (plus auto_approve_types).
    graduated  — auto-approve only when BOTH hold: the draft's QA scores clear
                 the bar, AND this (strategy, platform) has a proven track
                 record (enough rewarded posts at/above baseline). Trust
                 expands automatically as evidence accumulates; a decayed or
                 collapsed track record pulls approval back to the human.
    full       — approve everything not marked never_auto_approve.
    """

    auto_approve: bool = False          # legacy switch; mode wins when set
    auto_approve_types: list[str] = Field(default_factory=list)
    mode: str = ""                      # "", "manual", "graduated", "full"
    min_track_record: int = 5           # rewarded posts a strategy+platform needs
    qa_bar: float = 6.5                 # min avg judge score (0-10) to self-approve


class SafetyConfig(_Base):
    """Self-monitoring for unattended operation — the guardrails that make
    full autonomy safe enough to actually leave running."""

    collapse_window: int = 5            # trailing rewarded posts examined
    collapse_threshold: float = 0.28    # avg graded reward below this = collapse
    pause_hours: int = 48               # platform cool-down after a collapse
    max_daily_spend_usd: float = 25.0   # freeze generation past this (real spend only)


class HumorConfig(_Base):
    """The comedy pipeline: violation search → scaffolded fan-out → pairwise rank
    → predictability filter. Applied when a strategy sets humor_level != none."""

    enabled: bool = True
    candidates: int = 6            # scaffolded joke candidates per piece ("full" humor)
    candidates_light: int = 3      # candidates when humor_level == "light"
    min_violation: float = 0.5     # BVT gate: below this = bland corporate safety
    min_benignness: float = 0.5    # BVT gate: below this = off-brand offense
    predictability_filter: bool = True  # kill jokes whose punchline is guessable
    model: str = ""                # override model for humor gen ("" = llm.text_model)


class LearningConfig(_Base):
    """The evolution machinery — how evidence turns into better choices.

    Rewards are graded (ratio/(ratio+1) around the per-platform baseline, so a
    10x post earns far more than a 1.05x post), applied exactly once per post
    after metrics mature, and old evidence decays so the system tracks a moving
    audience instead of averaging over a dead one.
    """

    decay_half_life_days: float = 45.0  # evidence half-life (0 = never decay)
    holdout_pct: float = 0.10           # ε of generations use a random policy — the
                                        # live control group that PROVES learning lifts
    reward_maturity_hours: int = 48     # a post is rewarded once, after this age
    min_baseline_posts: int = 3         # measured posts a platform needs before rewards flow
    strategy_prior_strength: float = 4.0  # pseudo-observations encoding research mix weights
    # Owner-taste channel (mobile review feed → learning). The owner's rating is
    # available pre-posting and reflects taste directly, so it gets its own
    # weighted reward path alongside audience engagement.
    human_reward_weight: float = 1.0    # bandit pseudo-observations per owner rating
    taste_max_lessons: int = 12         # active lessons injected per prompt (top-confidence)
    taste_merge_threshold: float = 0.86 # cosine ≥ this = same lesson (support += 1)
    max_active_experiments: int = 3     # concurrent creative experiments per campaign
    experiment_min_samples: int = Field(3, ge=1)  # rated samples per variant before concluding
    experiment_margin: float = 1.0      # mean-rating gap (1..10 scale) to declare a winner
    scientist_min_new_reviews: int = 3  # reviews since last run before the scientist re-runs


class TrendsConfig(_Base):
    """Real-time trend reaction — the fast path from a spiking trend to a draft."""

    auto_react: bool = False            # generate content the moment a hot trend appears
    react_threshold: float = 0.55       # min trend_score to be considered "hot"
    min_velocity: float = 0.0           # min score delta vs last sighting (0 = new or rising)
    max_reactions_per_day: int = 2      # per product — trend-jacking everything is spam
    react_platforms: list[str] = Field(default_factory=list)  # [] = all enabled platforms
    fast_poll_minutes: int = 30         # fast sources (Reddit rising / Bluesky / Google RSS)
    subreddits: list[str] = Field(default_factory=lambda: [
        "recruitinghell", "internships", "jobs", "csMajors",
        "cscareerquestions", "college",
    ])                                  # niche subs polled for rising posts (early-warning + material)


class HumorRadarConfig(_Base):
    """Curated-humor discovery — find what the internet finds funny RIGHT NOW
    and ride it, instead of writing jokes from scratch. Entertainment
    campaigns only; reposts always credit, never self-approve, and expire."""

    enabled: bool = True
    subreddits: list[str] = Field(default_factory=lambda: [
        "memes", "dankmemes", "me_irl", "wholesomememes", "shitposting",
    ])                                  # meme communities polled for rising humor
    auto_draft: bool = False            # top find → repost draft automatically
    max_drafts_per_day: int = 2         # per entertainment campaign
    min_funny: float = 0.6              # judge gate for auto-drafting
    draft_ttl_hours: int = 48           # meme freshness window — expire unposted drafts


class Settings(_Base):
    """The whole of ``default.yaml``."""

    upload_post: UploadPostConfig = Field(default_factory=UploadPostConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    platforms: dict[str, PlatformConfig] = Field(default_factory=dict)
    media: MediaConfig = Field(default_factory=MediaConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    trends: TrendsConfig = Field(default_factory=TrendsConfig)
    humor: HumorConfig = Field(default_factory=HumorConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    humor_radar: HumorRadarConfig = Field(default_factory=HumorRadarConfig)

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
    strategies: Optional[list[str]] = None  # allowlist of strategy ids (None = all)
    specificity_bank: list[str] = Field(default_factory=list)  # concrete audience-life artifacts (humor fuel)
    knowledge: dict[str, list[str]] = Field(default_factory=dict)  # pain_veins / fact_base / take_pool


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
