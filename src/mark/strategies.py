"""Strategy framework — the pluggable catalog of named content strategies.

A Strategy is a repeatable, named playbook ("absurdist-ai-slop", "pain-point-pov",
"build-in-public", ...) that shapes every stage of generation:

  * eligibility  — which platforms it fits, and how it adapts per platform
  * strategist   — a brief steering topic/angle selection
  * writer       — a brief steering voice, structure, and joke mechanics
  * media        — a brief steering image/video prompt style
  * humor_level  — none | light | full (drives the humor engine in humor.py)
  * character    — whether the product's AI ambassador fronts the content
  * series       — optional episodic format (episode number derived from history)

Selection is learned: "strategy" is a bandit arm type, so Thompson sampling
gradually concentrates on the strategies that actually earn engagement on each
platform, while still exploring. Products can restrict the pool via a
`strategies` allowlist (products table / product YAML).

The catalog content is distilled from docs/research/MASTER-STRATEGY.md — edit
there first, then encode here.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from . import db as db_module
from .app import App


class Strategy(BaseModel):
    id: str
    name: str
    description: str                    # what it is + why it works (mechanism)
    emotional_target: str               # primary emotion (see constants.EMOTIONAL_TARGETS)
    platforms: dict[str, str]           # platform -> adaptation note ("" = native fit)
    content_types: list[str]            # preferred types, best first
    humor_level: str = "none"           # "none" | "light" | "full"
    uses_character: bool = False        # front the product's AI ambassador
    series_format: Optional[str] = None  # episodic recipe; episode # auto-derived
    strategist_brief: str = ""          # injected into the strategist prompt
    writer_brief: str = ""              # injected into the writer prompt
    media_brief: str = ""               # steers image/video prompt writing
    example_sketches: list[str] = Field(default_factory=list)  # few-shot flavor
    mix_weight: float = 0.1             # cold-start sampling prior (bandit takes over)
    never_auto_approve: bool = False    # e.g. founder voice / Reddit drafts
    knowledge_pool: Optional[str] = None  # product knowledge key this strategy draws on
    requires_product: bool = False      # needs a real product (demos, receipts, founder voice)
                                        # — excluded for entertainment campaigns where the
                                        # content itself IS the business

    def fits(self, platform: str) -> bool:
        return platform in self.platforms

    def platform_note(self, platform: str) -> str:
        return (self.platforms.get(platform) or "").strip()


# --------------------------------------------------------------------------- #
# Catalog — encoded from docs/research/MASTER-STRATEGY.md §1 (the source of
# truth; edit there first, then here). Platform absence = do not use there.
# --------------------------------------------------------------------------- #
STRATEGIES: list[Strategy] = [
    Strategy(
        id="pain-point-povs",
        name="Pain-point POVs",
        description=(
            "Dramatize one HYPER-specific moment of job-hunt suffering so precisely the "
            "viewer feels seen ('POV: it's 2:47 AM, application #83, the portal made you "
            "re-type your resume'). The specificity IS the joke; the comment section "
            "completes it — commenting 'same' is an act of membership, not evaluation."
        ),
        emotional_target="recognition",
        platforms={
            "tiktok": "20-35s POV or greenscreen reaction; word-synced captions mandatory; raw not polished",
            "instagram": "same one notch more polished; CTA aims at SENDS ('send this to your roommate with 0 offers')",
            "x": "lowercase one-liner, screenshot-shaped, leaves an obvious slot for readers to quote with their own version",
            "threads": "softened + end in a sincere question ('what's your rejection count')",
            "youtube": "loopable sub-35s skit — final line flows back into the first",
            "linkedin": "soften to pain-point-confession register; no meme formats",
        },
        content_types=["video", "text", "image"],
        humor_level="full",
        knowledge_pool="pain_veins",
        strategist_brief=(
            "Pick ONE pain vein and narrow it to a single moment (a timestamp, a number, "
            "a named portal) — never a category. 'Writing cover letter #40 at 2am' works; "
            "'job hunting is hard' is banned. Register options: ironic, dark, absurdist."
        ),
        writer_brief=(
            "First person, present tense, zero marketing language. ≥1 hyper-specific "
            "artifact (named portal, verbatim rejection phrasing, precise absurd number). "
            "End on the punch. The product may appear only in the final beat as relief, "
            "or only in the caption — never the hero of the skit. Leave the post "
            "completable (readers add their own number) without ever saying 'comment below'."
        ),
        media_brief=(
            "Video: deadpan TTS ('someone who has applied to 400 jobs' energy) over "
            "screen/b-roll/static aesthetic background. Image: fake-screenshot aesthetic."
        ),
        example_sketches=[
            'X: "got a rejection email today from a company i applied to in 2023. the '
            'workday account outlived my hope. it outlived the role. it may outlive me"',
            'TikTok: on-screen "POV: round 7 of interviews for an unpaid internship" — '
            'deadpan TTS narrates a wellness-check script while a calendar fills with '
            'interview blocks. Final beat: "they went with an internal candidate."',
        ],
        mix_weight=0.25,
    ),
    Strategy(
        id="satirical-ui-franchise",
        name="Satirical UI franchise",
        description=(
            "Daily fake job-app UI mockups with one unhinged-but-plausible feature "
            "('Workday Premium: pay $4.99 to have a human see your resume'). Recognizable "
            "UI = instant parse; the joke lives in the image; caption is one dry line. "
            "This exact format grew Soren Iverson 2K→72K in 6 months. Infinitely "
            "repeatable = a franchise, not one-off jokes."
        ),
        emotional_target="righteous_frustration",
        platforms={
            "x": "home platform — daily cadence, one dry lowercase caption line",
            "instagram": "batch 5-8 mockups into a themed carousel",
            "tiktok": "themed carousel via photo-mode",
            "linkedin": "sparingly — the safest LinkedIn joke format (satirizes tools, not people)",
            "threads": "occasional, clean renders only",
            "bluesky": "occasional — ONLY deterministic Pillow renders (no generative media, ever)",
        },
        content_types=["image", "carousel"],
        humor_level="full",
        series_format=(
            "A recognizable ongoing franchise: same UI-mockup format daily, escalating "
            "audacity. Fans should recognize the format instantly from the thumbnail."
        ),
        strategist_brief=(
            "Pick a target surface (ATS form, LinkedIn feature, rejection-email UI, "
            "interview scheduler, job-board filter) plus one violation. The feature "
            "concept must pass the 'unhinged but one board meeting away from real' test — "
            "plausibility is the benign anchor, the real system's cruelty is the violation."
        ),
        writer_brief=(
            "The image text IS the joke — write exact UI copy. Fill slide_texts as the "
            "renderer spec: line 1 = window title; then rows, each prefixed with one of "
            "'text:', 'field:', 'button:', 'button_disabled:', 'tooltip:', 'counter:', "
            "'toggle:' (e.g. \"field: Please re-type your resume\", "
            "\"button_disabled: Autofill\", \"tooltip: Autofill is a premium feature for "
            "employers only\"). 4-7 rows; every row carries part of the joke. Caption: "
            "ONE dry lowercase line, no explanation."
        ),
        media_brief=(
            "Deterministic UI composition: clean form fields, buttons, toggles in "
            "corporate-neutral styling (adjacent to but legally distinct from real "
            "products). NEVER model-rendered garbled text — text is the joke."
        ),
        example_sketches=[
            'Job posting card: "Applicants: 2,847 · Positions: 1 · Your percentile: don\'t."',
            'ATS upload screen: "Resume uploaded successfully. Please now re-type your '
            'resume." [Autofill] greyed out, tooltip: "Autofill is a premium feature for '
            'employers only."',
            'Calendar invite: "Interview Round 8 of ∞ — Final final culture fit vibe '
            'check — Declining this invite withdraws your application."',
        ],
        mix_weight=0.12,
    ),
    Strategy(
        id="educational-hooks",
        name="Educational hooks (CareerTok)",
        description=(
            "Save-worthy, hyper-tactical job-search advice: 46% of Gen Z secured a job or "
            "internship via TikTok; 92% trust it for career advice. Saves/sends are the "
            "strongest ranking signals and come from reference value. The tip must stand "
            "alone; the product is step 3, never the headline."
        ),
        emotional_target="satisfaction",
        platforms={
            "tiktok": "photo-mode carousel 5-7 slides (3-5x video reach) or 45-60s value video",
            "instagram": "carousel 8-12 slides, 4:5; slide 1 = incomplete-feeling hook",
            "linkedin": "6-8 slide PDF-style carousel, caption ≤100 chars; HR topics carry a 1.54x reach multiplier",
            "youtube": "sub-60s tip video with keyword title (months-long search tail)",
            "x": "long-form post or thread; first line is the promise",
            "threads": "single tactical claim + question",
        },
        content_types=["carousel", "video", "text", "thread"],
        humor_level="none",
        knowledge_pool="fact_base",
        strategist_brief=(
            "Pick ONE concrete, immediately actionable tactic with a number attached "
            "('apply within 1 hour of a posting going live', 'the exact email for a "
            "recruiter who ghosted you after round 2'). Reject anything 'networking "
            "tips'-grade generic. Only cite claims from the product's fact base."
        ),
        writer_brief=(
            "Hook = authority signal → curiosity gap → payoff promise ('I watched 1,000 "
            "applications get auto-rejected — here's the form field that did it'). Every "
            "post: ≥1 concrete number, named tool, or verbatim example. Each slide ≤12 "
            "words and must stand alone when screenshotted. CTA matches the platform "
            "signal: saves on carousels, sends on Reels."
        ),
        media_brief=(
            "Clean high-contrast text-forward slides, bold numerals, zero stock-photo "
            "energy. Slide 1 hooks incompletely; slide 2 proves; last slide CTAs."
        ),
        example_sketches=[
            'Carousel: "your resume gets 7.4 seconds. here\'s what they actually see" → '
            'heatmap slides → "the ATS sees even less. save this."',
            'Video: "recruiters auto-reject applications missing THIS field. i checked '
            '200 postings" → proof → tip → "sudoapply fills it automatically but you can '
            'also just… fill it."',
        ],
        mix_weight=0.15,
    ),
    Strategy(
        id="demo-magic",
        name="Demo magic",
        description=(
            "Screen recordings where the product performs its 3-second magic trick "
            "('watch this application fill itself'). Outcome-shown-in-first-2-seconds is "
            "the best-performing hook class on record. Zero AI-labeling risk (real screen "
            "recording). This is the conversion engine the other strategies feed."
        ),
        emotional_target="satisfaction",
        platforms={
            "tiktok": "15-30s; outcome in second 1; keyword-stack spoken + overlay + caption",
            "instagram": "optimize for profile visits; comment-keyword → DM link flow",
            "youtube": "loop design — end where it starts",
            "x": "native short vertical video (<60s gets top format boost)",
        },
        content_types=["video"],
        humor_level="light",
        requires_product=True,
        strategist_brief=(
            "Pick one demo moment: autofill ripping through a Workday form; 60 "
            "applications during one lecture (time-lapse); tracker before/after; a "
            "satisfying UI loop (kanban card sliding to 'Interview'). Hook archetypes: "
            "outcome-first / mistake-frame ('you're applying to jobs wrong') / audience "
            "callout."
        ),
        writer_brief=(
            "Hook overlay ≤8 words, on screen frame 1, must work muted. Before/after "
            "framing is default: '45 minutes → 45 seconds'. Keyword-stack the same 2-3 "
            "search phrases in spoken audio + on-screen text + caption. Soft CTA only. "
            "ALL numbers/screens must be real — never fabricate results."
        ),
        media_brief=(
            "Real screen-capture aesthetic, cursor highlights, word-synced captions when "
            "voiced. Satisfying-loop variants end exactly where they start."
        ),
        example_sketches=[
            '"45 minutes of your life. or 45 seconds." → split screen: manual form '
            'drudgery time-lapse vs autofill blazing through the same form.',
            '"watch my AI apply to 12 internships while i eat lunch" — lo-fi time-lapse, '
            'deadpan voiceover.',
        ],
        mix_weight=0.12,
    ),
    Strategy(
        id="unhinged-mascot",
        name="Unhinged mascot episodes",
        description=(
            "Episodic content starring the AI ambassador. Each post is a lore update in "
            "an ongoing universe: running counters, recurring NPCs, escalating arcs. "
            "Commitment-to-the-bit is the single strongest documented success factor "
            "(Nutter Butter 3.1K→700K; Duolingo 50K→16M). Callbacks convert casual "
            "viewers into followers because the next joke pays more if you followed."
        ),
        emotional_target="belonging",
        platforms={
            "tiktok": "vlog-grammar episodes; selfie-stick framing, never 'POV'",
            "instagram": "episode Reels + character stills with caption",
            "youtube": "episode re-renders, loop design",
            "x": "the character's own text posts — in-voice, lowercase",
            "threads": "character text posts, softened",
        },
        content_types=["video", "image", "text"],
        humor_level="full",
        uses_character=True,
        series_format=(
            "Ongoing universe with running counters and recurring NPCs. Every episode "
            "MUST reference at least one prior event, counter, or NPC (callbacks are the "
            "follower-conversion mechanism). One game per episode, 3-5 heightens, out at "
            "the peak. Never explain the lore in-post."
        ),
        strategist_brief=(
            "Write the next episode beat from the character's lore: what does its flaw "
            "(cannot stop applying) generate this week? Mine trends and comment themes "
            "for episode topics. Must reference ≥1 prior event or running counter."
        ),
        writer_brief=(
            "Stay ruthlessly in the character's voice. NO testimonials from the character "
            "('SudoApply got me a job' is banned — it demos, bits, and begrudgingly "
            "admits the app saves it time). Never name real companies or recruiters as "
            "villains. Include the on-screen AI-character disclosure in video scripts."
        ),
        media_brief=(
            "Character-sheet-driven consistency: reference image conditioning + the "
            "character's visual anchor prop in every prompt. Deliberately synthetic "
            "render style — never photoreal. Vlog grammar: 'holding a selfie stick "
            "(that's where the camera is)', explicit ambient sounds, no subtitles in "
            "generation (captions burned in post)."
        ),
        mix_weight=0.15,
    ),
    Strategy(
        id="absurdist-ai-slop",
        name="Absurdist AI slop (self-aware)",
        description=(
            "Deliberately absurd AI-generated video/images that KNOW they're AI slop and "
            "wink at it. Two-axis rule: maximize premise absurdity AND render fidelity "
            "simultaneously (photoreal cat on a diving board, not mildly-weird mush). The "
            "absurdity must metaphorically encode the value prop: chaos = what the job "
            "hunt feels like. Audiences rate AI comedy HIGHER when it acknowledges being "
            "AI (CHI 2026)."
        ),
        emotional_target="dark_laughter",
        platforms={
            "tiktok": "native lane; ALWAYS set the AI label; audio-first hook in first 2s",
            "youtube": "same; pinned self-aware comment is a free second joke",
            "x": "still image + winking caption",
            "instagram": "explicit wink in the overlay; 'Made with AI' label",
            "threads": "image + deadpan self-aware line",
        },
        content_types=["video", "image"],
        humor_level="full",
        strategist_brief=(
            "Pick a rigid template — the template IS the game: (a) hyper-real production "
            "grammar (bodycam / CCTV / news-chyron / ring-cam / selfie-vlog) + one "
            "impossible job-hunt subject played completely straight; (b) brainrot "
            "character (hybrid creature + chantable rhythmic name + deadpan TTS lore); "
            "(c) AI-ASMR mapped to product ('the sound of 200 applications auto-filling'). "
            "Absurdity must have a POINT — default-mode brainrot reads lazy in 2026."
        ),
        writer_brief=(
            "Gag-densification: brainstorm sight gags, require ≥1 per 3 seconds of video. "
            "Caption is deadpan-short, lowercase, and MUST acknowledge the bit ('we "
            "generated this instead of applying to jobs for you. wait. no. we did both'). "
            "Auto-reject if: logo/CTA in first 3s; weird-without-a-punchline; earnest "
            "framing of AI content."
        ),
        media_brief=(
            "Maximal render fidelity on an impossible premise, played straight. Video "
            "prompts: concrete camera grammar ('bodycam footage of...', explicit ambient "
            "sound list), end with 'no subtitles, no text overlay'. Never model-rendered "
            "text in frame."
        ),
        example_sketches=[
            'Bodycam footage of an "ATS raid": officers kick down a server-room door '
            'where a printer is shredding resumes; chyron: "LOCAL ATS CAUGHT REJECTING '
            '4,000 QUALIFIED APPLICANTS IN 0.3 SECONDS." Caption: "dramatization. (it '
            'was faster.)"',
            'Selfie-vlog: a photoreal pigeon in a tiny suit commuting to hand-deliver a '
            'resume, ghosted by a revolving door. Spoken: "day 400. the door said we\'ll '
            'circle back."',
        ],
        mix_weight=0.10,
    ),
    Strategy(
        id="meme-carousels",
        name="Meme carousels",
        description=(
            "5-8 ORIGINAL job-hunt memes on one theme per carousel; each swipe is another "
            "punchline. Meme carousels are IG's highest-engagement format class; TikTok "
            "photo-mode gets 3-5x video reach. Must be original/transformative — repost "
            "aggregation is algorithmically dead and an account-level kill risk."
        ),
        emotional_target="recognition",
        platforms={
            "tiktok": "photo-mode native flow, 1080x1920 slides; background music makes it Reels-eligible",
            "instagram": "4:5 1080x1350; optimize for sends ('this whole post is us')",
        },
        content_types=["carousel"],
        humor_level="full",
        knowledge_pool="pain_veins",
        strategist_brief=(
            "One theme (a single pain vein) per deck. Escalate through the deck: slides "
            "1-2 establish the pattern, slide 3+ breaks it (rule of three), strongest "
            "meme last-but-one, CTA last."
        ),
        writer_brief=(
            "Run the humor engine per slide. Each slide is one self-contained joke that "
            "also escalates the theme. Slide text short enough to render pixel-perfect."
        ),
        media_brief=(
            "Bold meme-native composition, text rendered deterministically (never "
            "garbled). Original visual style — no stale template aesthetics."
        ),
        example_sketches=[
            'Theme "stages of one application": slide 1 applying (hope); slide 2 the '
            'confirmation email (fine); slide 3 six weeks of silence (skeleton at desk); '
            'slide 4 rejection at 2:47 AM ("why are you awake"); slide 5 "start again. '
            'or don\'t [app icon, tiny]".',
        ],
        mix_weight=0.08,
    ),
    Strategy(
        id="trend-jack",
        name="Trend-jack",
        description=(
            "Map a fresh trend (format, discourse moment, job-market news) onto a house "
            "format within hours. Trends are rented distribution; speed is the entire "
            "value (memes peak in 3-5 days; brand adoption marks the death phase). Skip "
            "80-90% of detected trends — great accounts are defined by what they don't post."
        ),
        emotional_target="belonging",
        platforms={
            "tiktok": "fastest sufficient format; trend age <7 days hard limit",
            "x": "same-day text riff on news/discourse moments",
            "threads": "discourse-jack with a sincere question",
            "instagram": "lagged 3-7 days behind TikTok (platform-lag arbitrage)",
            "youtube": "re-render of the TikTok take",
        },
        content_types=["text", "image", "video"],
        humor_level="full",
        strategist_brief=(
            "The trend is non-negotiable context (it arrives forced). Map it onto the "
            "nearest house format (deranged job-search POV / screenshot + one-liner / "
            "satirical UI / self-aware slop) — trend response is format-mapping, not "
            "de-novo creative. Pick the FASTEST sufficient content type: text ships in "
            "minutes, image in ~30 min, video in ~1h."
        ),
        writer_brief=(
            "Preserve the trend's actual comedic mechanic — if the joke only exists as "
            "product promotion, it fails. Product appears ≤1 time, never in the hook, "
            "never as the punchline resolution. Test: is it still funny with the product "
            "name removed?"
        ),
        media_brief="Match the trend's native execution style (from its style notes) exactly.",
        example_sketches=[
            'Layoff-news day, same-day X post: "companies: we can\'t find talent. also '
            'companies: [screenshot of 4,000-applicant posting]"',
        ],
        mix_weight=0.08,
    ),
    Strategy(
        id="contrarian-takes",
        name="Contrarian takes (defanged)",
        description=(
            "Strong opinions about the job-search system stated without hedging: 'cover "
            "letters are a scam and recruiters know it.' Disagreement → replies → "
            "distribution (replies weighted 13.5-27x a like on X). Villain is ALWAYS a "
            "system or process, never a person or named company. Spice, not rage — "
            "ragebait buys awareness and burns trust (Cluely)."
        ),
        emotional_target="righteous_frustration",
        platforms={
            "x": "flat statement, lowercase ok, screenshot-length, one idea",
            "linkedin": "wrap in a number-claim or confession, 1000+ chars; never 'Stop doing X' templates",
            "threads": "append a genuine question (positivity-biased ranking)",
            "bluesky": "dry, communal framing",
        },
        content_types=["text", "image"],
        humor_level="light",
        knowledge_pool="take_pool",
        strategist_brief=(
            "Whitelisted targets ONLY: ATS, ghosting culture, unpaid internships, "
            "interview inflation, cover letters, career-center advice, credential "
            "inflation. Attach the defense — a data point makes the take defensible. "
            "BANNED: named companies, named people, 'cheating' framing, fabricated "
            "claims, manufactured outrage."
        ),
        writer_brief=(
            "State it flat. No hedging, no 'unpopular opinion:' crutch on X, one idea "
            "per post. Never engagement-bait phrasing ('agree?')."
        ),
        media_brief="Optional receipt image: a real stat rendered as a clean chart or screenshot.",
        example_sketches=[
            'X: "cover letters are a loyalty test for a company that will ghost you. '
            'write zero. apply to 3x more. the math has never once favored the letter"',
            'Threads: "unpopular opinion: GPA has never gotten anyone past an ATS. what '
            'actually did it for you?"',
        ],
        mix_weight=0.08,
    ),
    Strategy(
        id="social-proof-receipts",
        name="Social-proof receipts",
        description=(
            "Screenshot-shaped proof from REAL product data only: aggregate stats, "
            "tracker before/afters, blurred interview-invite receipts. 72% find customer "
            "evidence more credible than brand claims. Seasoning, not the meal — "
            "over-posting reads as brag spam."
        ),
        emotional_target="hope",
        platforms={
            "x": "dashboard screenshot + dry one-liner",
            "linkedin": "short story arc ending in the number",
            "instagram": "before/after visual",
            "tiktok": "receipt-drop video or image",
            "threads": "casual milestone note",
            "bluesky": "real numbers, founder voice, link welcome",
        },
        content_types=["image", "text", "video"],
        humor_level="none",
        requires_product=True,
        strategist_brief=(
            "Anchor on ONE genuinely notable real number or event. Specific, odd, "
            "slightly-too-precise numbers beat round ones. NEVER invent metrics, "
            "testimonials, or outcomes — fabricated proof is existential (Cluely)."
        ),
        writer_brief=(
            "Understate; the number does the work. Dry delivery beats excitement. "
            "Blur any PII in described screenshots."
        ),
        media_brief="Authentic UI screenshot aesthetic or minimal stat card; never 'designed graphic' energy.",
        example_sketches=[
            'X: dashboard screenshot — "users applied to 40,000 jobs last month. total '
            'human minutes spent: fewer than one career fair."',
            'Receipt drop: blurred interview-invite email, caption "sent at 2am. by the '
            'robot. while they slept."',
        ],
        mix_weight=0.05,
    ),
    Strategy(
        id="fake-text-drama",
        name="Fake text drama",
        description=(
            "Mini soap operas rendered as animated message conversations over gameplay "
            "b-roll — job-hunt dramas in message form. Millions of views per video, zero "
            "filming, fully scriptable (RIZZ App: 550M+ views). The product appears "
            "INSIDE the story as an app someone mentions, never as an ad."
        ),
        emotional_target="dark_laughter",
        platforms={
            "tiktok": "60-180s; cliffhanger beats every ~8s; numbered parts",
            "youtube": "watch-time monster; loop the cliffhanger",
            "instagram": "photo-mode variant: the thread as slides",
        },
        content_types=["video", "carousel"],
        humor_level="full",
        knowledge_pool="pain_veins",
        series_format=(
            "Numbered parts with cliffhangers ('part 2 if he escapes'). The payoff must "
            "land or the account gets labeled bait."
        ),
        strategist_brief=(
            "Pick a drama premise from the pain veins + a twist type (betrayal / absurd "
            "escalation / justice). First message must be a scroll-stopper ('my recruiter "
            "just texted me at 11pm…')."
        ),
        writer_brief=(
            "Write `script` as the message thread, ONE message per line in the exact "
            "form 'Sender: message' (use 'Me:' for our side; short names for others; a "
            "bare line renders as a narrator card). 12-30 messages. First message must "
            "be a scroll-stopper; cliffhanger beat roughly every 5 messages. Humor "
            "engine on the punch messages. Product placed as an incidental mid-story "
            "mention at most."
        ),
        media_brief="Chat-bubble compositor over gameplay b-roll; typed-message pacing synced to beats.",
        example_sketches=[
            'Group chat "job hunt support group 💀": round 9 of interviews announced; '
            'escalating absurd tasks ("they want a case study on their case study"); '
            'twist: the posting was a ghost job reposted for 14 months. Caption: "part 2 '
            'if he escapes."',
        ],
        mix_weight=0.07,
    ),
    Strategy(
        id="founder-build-log",
        name="Founder build log (draft-only)",
        description=(
            "First-person founder posts drafted from REAL product events for the owner "
            "to humanize and approve: milestones, weird data finds, failure postmortems "
            "(failures outperform wins). Audience is builders/press/amplifiers, not "
            "students — earns credibility and distribution. NEVER auto-posted."
        ),
        emotional_target="hope",
        platforms={
            "x": "build-in-public canonical home",
            "linkedin": "founder-personal voice, story arc",
            "bluesky": "links allowed and welcome (3-4x per-reader conversion); dry self-aware smallness",
            "threads": "softened founder note",
        },
        content_types=["text"],
        humor_level="light",
        never_auto_approve=True,
        requires_product=True,
        strategist_brief=(
            "Anchor on a real event: a release, a metric threshold, a weird data find, a "
            "failure worth telling. Customer stories beat revenue screenshots."
        ),
        writer_brief=(
            "First person, founder voice, specific numbers, zero marketing adjectives. "
            "Write it like a text to a friend who also builds things."
        ),
        media_brief="Optional real screenshot only; no generated imagery.",
        mix_weight=0.05,
    ),
]

_BY_ID = {s.id: s for s in STRATEGIES}


def get(strategy_id: str) -> Optional[Strategy]:
    return _BY_ID.get(strategy_id)


def register(strategies: list[Strategy]) -> None:
    """Replace/extend catalog entries (used by tests and future config loading)."""
    for s in strategies:
        if s.id in _BY_ID:
            STRATEGIES[STRATEGIES.index(_BY_ID[s.id])] = s
        else:
            STRATEGIES.append(s)
        _BY_ID[s.id] = s


# --------------------------------------------------------------------------- #
# Eligibility + selection
# --------------------------------------------------------------------------- #
def product_allowlist(product: dict) -> Optional[list[str]]:
    """The product's optional strategy allowlist (JSON column / YAML key).
    None = no restriction (all strategies). An explicit empty list means
    "all disabled" and is honored as such — never coerced to None."""
    allowed = db_module.loads(product.get("strategies"), None)
    return allowed if isinstance(allowed, list) else None


def is_entertainment(product: Optional[dict]) -> bool:
    """Content-as-the-business campaigns: no product to market — the account
    exists purely to entertain, and performance IS the goal."""
    return bool(product) and (product.get("kind") or "product") == "entertainment"


def catalog_for(product: Optional[dict]) -> list[Strategy]:
    """The campaign's strategy catalog: the base catalog with any per-campaign
    brief overrides applied (products.strategy_catalog JSON, written by the
    onboarding pipeline). The base briefs encode the SudoApply research; a new
    campaign gets its own domain-specific briefs without forking the code."""
    if not product:
        return STRATEGIES
    overrides = db_module.loads(product.get("strategy_catalog"), {}) or {}
    if not overrides:
        return STRATEGIES
    out = []
    for s in STRATEGIES:
        o = overrides.get(s.id)
        if isinstance(o, dict):
            fields = {k: v for k, v in o.items() if k in Strategy.model_fields}
            if fields:
                s = s.model_copy(update=fields)
        out.append(s)
    return out


def eligible(app: App, product: dict, platform: str) -> list[Strategy]:
    """Strategies that fit this platform, the platform's allowed content types,
    the product's allowlist, and the campaign kind."""
    allowed_types = set(app.settings.platform(platform).content_types or ["text"])
    allowlist = product_allowlist(product)
    entertainment = is_entertainment(product)
    out = []
    for s in catalog_for(product):
        if not s.fits(platform):
            continue
        if allowlist is not None and s.id not in allowlist:
            continue
        if entertainment and s.requires_product:
            continue
        if not any(t in allowed_types for t in s.content_types):
            continue
        out.append(s)
    return out


def pick(app: App, product: dict, platform: str,
         bandit_choice: Optional[str] = None) -> Optional[Strategy]:
    """Resolve the strategy for this generation.

    The bandit's sampled choice wins when it's still eligible; otherwise sample
    by mix_weight (the research-derived cold-start priors), seeded by content
    count so the choice is deterministic offline while still covering the pool.
    """
    pool = eligible(app, product, platform)
    if not pool:
        # Entertainment campaigns on demo-heavy platform configs can filter the
        # pool empty; fall back to the platform-fitting non-product strategies.
        if is_entertainment(product):
            allowed_types = set(app.settings.platform(platform).content_types or ["text"])
            pool = [s for s in catalog_for(product)
                    if s.fits(platform) and not s.requires_product
                    and any(t in allowed_types for t in s.content_types)]
        if not pool:
            return None
    if bandit_choice:
        for s in pool:
            if s.id == bandit_choice:
                return s
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? AND platform = ?",
        (product["id"], platform),
    )
    n = row["n"] if row else 0
    import random

    rng = random.Random(f"{product['id']}:{platform}:{n}")
    weights = [max(s.mix_weight, 0.01) for s in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def episode_number(app: App, product: dict, platform: str, strategy: Strategy) -> int:
    """1-based episode number for episodic strategies — how many pieces of content
    this product has actually kept (not rejected/failed) under this strategy,
    plus one. Counting dead drafts would desync numbering from the on-air lore."""
    if not strategy.series_format:
        return 1
    # First-class series bookkeeping (series.py): when an active series row
    # exists, its episode counter is the source of truth for numbering.
    srow = db_module.query_one(
        app.conn,
        "SELECT episodes FROM series WHERE product_id = ? AND strategy_id = ? "
        "AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (product["id"], strategy.id),
    )
    if srow is not None:
        return int(srow["episodes"] or 0) + 1
    row = db_module.query_one(
        app.conn,
        "SELECT COUNT(*) AS n FROM content WHERE product_id = ? "
        "AND status NOT IN ('rejected', 'failed') AND strategy_context LIKE ?",
        (product["id"], f'%"strategy": "{strategy.id}"%'),
    )
    return (row["n"] if row else 0) + 1


def candidate_ids(app: App, platform: str, product: Optional[dict] = None) -> list[str]:
    """All strategy ids that could apply on this platform (bandit arm values).
    With a product, campaign restrictions (kind, allowlist) are honored so the
    bandit's learned strategy pick is always one the campaign can actually use."""
    allowed_types = set(app.settings.platform(platform).content_types or ["text"])
    entertainment = is_entertainment(product)
    allowlist = product_allowlist(product) if product else None
    out = []
    for s in catalog_for(product):
        if not s.fits(platform):
            continue
        if entertainment and s.requires_product:
            continue
        if allowlist is not None and s.id not in allowlist:
            continue
        if any(t in allowed_types for t in s.content_types):
            out.append(s.id)
    return out
