"""Shared enumerations used by the strategist and the bandit.

Kept here so the agent and the learner agree on the same discrete choice space.
"""

HOOK_STYLES = ["question", "bold_claim", "story", "statistic", "pain_point", "before_after"]
TONES = ["funny", "educational", "relatable", "inspirational", "controversial"]

# The discrete choices the bandit optimizes.
ARM_TYPES = ["hook_style", "content_type", "tone", "post_time"]
