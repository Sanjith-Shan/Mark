"""Shared enumerations used by the strategist and the bandit.

Kept here so the agent and the learner agree on the same discrete choice space.
"""

HOOK_STYLES = ["question", "bold_claim", "story", "statistic", "pain_point", "before_after"]
TONES = ["funny", "educational", "relatable", "inspirational", "controversial"]

# Comedy mechanisms the humor engine can scaffold (each is a bandit arm — the
# system learns which ones actually land with THIS audience on EACH platform).
HUMOR_MECHANISMS = [
    "setup_subversion",       # misdirection: target assumption shattered by reinterpretation
    "rule_of_three",          # establish, reinforce, surprise
    "escalation",             # one unusual thing + premise-consistent heightens
    "anti_humor",             # flat literal payoff against a saturated format
    "absurdist_lore",         # self-aware AI absurdism with rigid template + lore
    "observational_specific", # hyper-specific shared experience, said too honestly
    "callback",               # recurring bits/lore only followers get
]

# Comedic personas for candidate fan-out (HumorGen-style: each persona forces a
# different direction into low-probability space — diversity is the point).
HUMOR_PERSONAS = [
    "cynic",                 # dry, seen-it-all, dark edges
    "absurdist",             # commits to nonsense with a straight face
    "deadpan_observer",      # states devastating specifics flatly
    "neurotic_student",      # spiraling first-person anxiety comedy
    "corporate_parodist",    # speaks fluent HR/recruiter-ese, weaponized
    "unhinged_ai",           # self-aware machine identity played as the bit
]

# The discrete choices the bandit optimizes.
ARM_TYPES = ["hook_style", "content_type", "tone", "post_time", "strategy",
             "humor_mechanism", "humor_persona"]
