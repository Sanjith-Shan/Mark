"""Structured-output schemas shared across agents.

These are the typed contracts the LLM must fill. Keeping them in one module means
the prompt builders, the offline mock factories, and the DB writers all agree on
the same shape.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ContentPlan(BaseModel):
    """Strategist output — decides WHAT to post."""

    platform: str
    content_type: str          # "video", "image", "carousel", "text", "thread"
    topic: str
    angle: str
    hook_style: str            # "question", "bold_claim", "story", "statistic", "pain_point", "before_after"
    tone: str                  # "funny", "educational", "inspirational", "relatable", "controversial"
    emotional_target: str = ""  # ONE primary emotion (constants.EMOTIONAL_TARGETS)
    trend_tie_in: Optional[str] = None
    reasoning: str = ""


class ContentDraft(BaseModel):
    """Writer output — the actual copy + media prompts."""

    caption: str
    hashtags: list[str] = Field(default_factory=list)
    hook: str = ""
    script: Optional[str] = None            # video: the spoken script
    slide_texts: Optional[list[str]] = None  # carousel: text per slide
    cta: Optional[str] = None
    alt_text: Optional[str] = None
    image_prompt: Optional[str] = None
    image_prompts: Optional[list[str]] = None  # carousel: prompt per slide
    video_prompt: Optional[str] = None
    video_style: Optional[str] = None        # "talking_head", "b_roll", "text_overlay", "ai_generated"
    humor_mechanism: Optional[str] = None    # set by the humor engine (bandit-tracked)
    humor_persona: Optional[str] = None      # set by the humor engine (bandit-tracked)


class JudgeVerdict(BaseModel):
    """LLM-judge output when picking the best of several draft variants."""

    best_index: int = 0
    hook_strength: float = 0.0     # 0..10
    brand_fit: float = 0.0         # 0..10
    scroll_stopping: float = 0.0   # 0..10
    slop_violations: list[str] = Field(default_factory=list)
    reasoning: str = ""


class CritiqueResult(BaseModel):
    """Self-critique pass — flags problems and returns a revised caption/hook."""

    needs_revision: bool = False
    problems: list[str] = Field(default_factory=list)
    revised_caption: Optional[str] = None
    revised_hook: Optional[str] = None


class EngagementInsights(BaseModel):
    """Analyzer output — weekly patterns and recommended adjustments."""

    top_performing_topics: list[str] = Field(default_factory=list)
    worst_performing_topics: list[str] = Field(default_factory=list)
    best_hook_styles: list[str] = Field(default_factory=list)
    best_content_types: dict[str, str] = Field(default_factory=dict)   # platform -> type
    best_posting_times: dict[str, str] = Field(default_factory=dict)   # platform -> time
    audience_sentiment_summary: str = ""
    recommended_adjustments: list[str] = Field(default_factory=list)
    raw_analysis: str = ""


class PlatformPick(BaseModel):
    platform: str
    value: str


class EngagementInsightsWire(BaseModel):
    """LLM wire format for EngagementInsights.

    OpenAI strict structured outputs reject free-key dicts (additionalProperties),
    so the per-platform maps go over the wire as explicit (platform, value) pairs
    and are converted back with :meth:`to_insights`.
    """

    top_performing_topics: list[str] = Field(default_factory=list)
    worst_performing_topics: list[str] = Field(default_factory=list)
    best_hook_styles: list[str] = Field(default_factory=list)
    best_content_types: list[PlatformPick] = Field(default_factory=list)
    best_posting_times: list[PlatformPick] = Field(default_factory=list)
    audience_sentiment_summary: str = ""
    recommended_adjustments: list[str] = Field(default_factory=list)
    raw_analysis: str = ""

    def to_insights(self) -> "EngagementInsights":
        return EngagementInsights(
            top_performing_topics=self.top_performing_topics,
            worst_performing_topics=self.worst_performing_topics,
            best_hook_styles=self.best_hook_styles,
            best_content_types={p.platform: p.value for p in self.best_content_types},
            best_posting_times={p.platform: p.value for p in self.best_posting_times},
            audience_sentiment_summary=self.audience_sentiment_summary,
            recommended_adjustments=self.recommended_adjustments,
            raw_analysis=self.raw_analysis,
        )

    @classmethod
    def from_insights(cls, ins: "EngagementInsights") -> "EngagementInsightsWire":
        return cls(
            top_performing_topics=ins.top_performing_topics,
            worst_performing_topics=ins.worst_performing_topics,
            best_hook_styles=ins.best_hook_styles,
            best_content_types=[PlatformPick(platform=k, value=v)
                                for k, v in ins.best_content_types.items()],
            best_posting_times=[PlatformPick(platform=k, value=v)
                                for k, v in ins.best_posting_times.items()],
            audience_sentiment_summary=ins.audience_sentiment_summary,
            recommended_adjustments=ins.recommended_adjustments,
            raw_analysis=ins.raw_analysis,
        )


# --------------------------------------------------------------------------- #
# Humor engine (humor.py) — violation search → scaffold fan-out → pairwise rank
# --------------------------------------------------------------------------- #
class Violation(BaseModel):
    """One candidate 'benign violation' — the raw material of a joke."""

    violation: str            # what's wrong/absurd/secretly-true, stated plainly
    strength: float = 0.0     # 0..1 — how strongly it violates expectations
    benignness: float = 0.0   # 0..1 — how safe/harmless it is for this audience
    target: str = ""          # who/what the joke punches at (must be up/sideways)


class ViolationSearch(BaseModel):
    items: list[Violation] = Field(default_factory=list)


class JokeCandidate(BaseModel):
    """One scaffolded comedic rewrite of a draft."""

    persona: str = ""             # which comedic persona wrote it
    mechanism: str = ""           # which joke structure it uses
    hook: str = ""
    caption: str = ""
    script: Optional[str] = None  # rewritten spoken script (video only)
    target_assumption: str = ""   # what the setup makes the reader believe
    connector: str = ""           # the ambiguous element with two readings
    reinterpretation: str = ""    # the second reading the punchline reveals
    punch_word: str = ""          # the reveal — must appear at/near the very end


class JokeCandidates(BaseModel):
    items: list[JokeCandidate] = Field(default_factory=list)


class PairwiseVerdict(BaseModel):
    """Pairwise comparison of two candidates (Bradley-Terry style — pairwise
    beats absolute 1-10 scoring for humor preference)."""

    winner: int = 0               # 0 or 1
    violation_strength: float = 0.0   # 0..1 for the winner
    benignness: float = 0.0           # 0..1 for the winner
    guessable: bool = False           # could the punchline be predicted from the setup?
    reasoning: str = ""


class GuessCheck(BaseModel):
    """Predictability filter — completions of the setup WITHOUT seeing the punch."""

    completions: list[str] = Field(default_factory=list)


class SentimentResult(BaseModel):
    sentiment: str = "neutral"     # "positive", "negative", "neutral"
    score: float = 0.0             # -1..1


class TrendRelevance(BaseModel):
    relevance: float = 0.0         # 0..1 — how relevant a trend is to the product
    reasoning: str = ""
