# TikTok Platform Research: Content Culture & Algorithm Meta for Small/New Accounts (2025–2026)

*Researched July 2026 for Mark (Autonomark). Product context: SudoApply — AI job-application tool for college students 18–24.*

> Sourcing note: TikTok publishes almost nothing official about ranking. The numbers below come from creator-tooling blogs, agency studies, and case-study writeups (2025–2026). Specific percentages should be treated as directional, not gospel; the *mechanisms* are consistently corroborated across independent sources and are the load-bearing findings.

---

## 1. What's winning right now (formats, lengths, hooks, overlays, sounds)

### Formats with momentum in 2025–2026

- **"Lead with the thing" product/outcome showcases.** The single best-performing hook category in a 34,635-clip dataset ([OpusClip](https://www.opus.pro/blog/tiktok-hooks-that-go-viral-2026)) is showing the finished result/transformation in the first 2 seconds — the after, the number, the product doing its trick. Averaged ~6,037 views/clip, ~2× the weakest hook type. The viewer must know within 2 seconds exactly what payoff they get for staying.
- **Lo-fi tutorials / faceless screen-recording content.** The polish-to-value ratio inverted in 2025: handheld, no transitions, "here's how to do one specific thing." Faceless niche channels (productivity, finance, AI tools) with tight scripts + screen recordings are a top-volume format ([unil.ink 2026 trends](https://unil.ink/blog/tiktok-trends-2026)). This is directly exploitable by a software product — the screen *is* the content.
- **Fake-texting story videos.** Mini soap operas rendered as animated iMessage/DM conversations over game b-roll (Minecraft parkour, Subway Surfers). Millions of views per video, zero filming required, fully scriptable/automatable ([Clippie](https://clippie.ai/blog/how-to-create-fake-text-message-story-videos)). See RIZZ App case study in §4.
- **Photo-mode carousels (swipeable slideshows).** Multiple 2026 sources report native Photo Mode posts getting 3–5× the reach of equivalent videos for the same accounts; every swipe is an engagement signal, and slide-completion is the ranking metric. Optimal 5–15 slides ([ReelBase](https://reelbase.io/blog/tiktok-photo-mode-algorithm-explained), [InstaCarousel](https://instacarousel.com/blog/tiktok-carousel-photo-mode-2026/)). Must be uploaded through the *native photo flow*, not as a video slideshow — the algorithm treats them differently.
- **Specific-frame "day in the life" / storytime.** Generic DITL is dead; "day in the life as a [hyper-specific identity]" is a top hook structure. 2026 storytime style: intimate delivery, line-by-line on-screen text, suspense over speed ([unil.ink](https://unil.ink/blog/tiktok-trends-2026)).
- **Longer short-form is back.** 1–3 minute videos now outperform 15-second clips on total watch time and FYP distribution *when retention holds* — but only when retention holds (see length data below).
- **Hopecore / earnest counter-trend.** Alongside brainrot, there's a documented counter-movement toward raw, earnest, encouraging content (#hopecore) — relevant because job-hunting despair→hope arcs fit it perfectly ([ContentGrip](https://www.contentgrip.com/tiktok-trends-gen-z-marketing-guide/)).

### Length & retention math (the actual constraint)

- Viral sweet spot: **21–38 seconds** for comedy/trend/entertainment content; **60–90s** for "deep dive" value content ([Retensis benchmarks](https://retensis.com/blog/tiktok-retention-rate-benchmarks-2026), [OpusClip](https://www.opus.pro/blog/how-long-should-a-tiktok-be-2026)).
- Retention benchmarks by length: <15s → 60–70% average retention; 15–30s → 50–60%; 30–60s → 40–50%; 1–3min → 30–40%.
- Distribution expands when **average watch time > ~50% of video length**; the completion bar for viral distribution has reportedly risen to ~70% (up from ~50% in 2024) ([Socialync](https://www.socialync.io/blog/tiktok-algorithm-2026-what-works-now)).
- **TikTok rewards retention, not length.** A 15s video watched fully beats a 60s video watched halfway. For an automated pipeline: default to 20–35s, only go long when the script structure genuinely sustains suspense.

### Hooks: the first 1–2 seconds

- The algorithm's first decision happens in ~1.5 seconds; ~71% of users decide to stay or scroll within 3 seconds. A failed hook = cold start the video never escapes.
- Winning hook patterns (data-backed, [OpusClip](https://www.opus.pro/blog/tiktok-hooks-that-go-viral-2026)):
  1. **Product/outcome showcase** — show the result first (best performer).
  2. **Authority signal → curiosity gap → promise of payoff** — most *common* structure ("I applied to 400 internships so you don't have to — here's what actually worked").
  3. **Disturbing/bold hypothetical opener** (storytime style).
  4. **Specific-identity frame** ("POV: you're a CS junior with 0 internship offers in March").
- Visual hook ≥ verbal hook: something must *move or change* on screen in second 1. Text overlay hook should be readable in one fixation (≤ ~8 words).

### Text overlay & caption norms (2026)

- **Native-looking beats branded.** TikTok's Creative Center data: 68% of top-performing ads use native-style text. In-app caption font (TikTok Sans, now open-source — [TikTok for Developers](https://developers.tiktok.com/blog/tiktok-sans-open-source)), hand-drawn arrows, informal styling outperform polished branded typography ([OverlayText](https://overlaytext.com/blog/text-overlay-for-reels-tiktok-viral-templates)).
- **Word-synced captions are the default expectation** for any talking-head/voiceover content: 1–3 words appearing in sync with speech, bold sans-serif (Montserrat Bold / TikTok Sans), white with black stroke, current word highlighted. Static full-sentence subtitles read as dated ([Blitzcut](https://blitzcutai.com/blog/best-caption-fonts-tiktok)).
- TikTok OCRs on-screen text and indexes it for search — on-screen text is an SEO surface, not just design.

### Sounds

- Trending audio is still a reach lever, but the 2026 play is **audio + format**: the sound signals the joke structure/pacing so viewers "get it" faster. Using the sound without the format template does nothing.
- **Trend half-life has collapsed:** a sound/format now peaks in ~72 hours and is dead in ~5 days ([Gain](https://blog.gainapp.com/tiktok-trends/)). "Spot at 6am, post by noon, or skip it." Weekly trend batching is structurally too slow — this is the strongest argument for Mark's trend-monitoring cron running at high frequency for TikTok.
- **Business-account constraint:** business/brand accounts are restricted to the Commercial Music Library by default — most viral trending sounds are unavailable to them. Personal/creator accounts have full audio access. This materially affects account-type choice for a product like SudoApply (creator-style account > official brand account for meme-audio play).
- Sources for programmatic trend discovery: TikTok Creative Center (region + time filters), [tokchart.com](https://tokchart.com/), weekly-updated lists (Buffer, HeyOrca, Dash Social).

---

## 2. How the algorithm treats new accounts

### The test-audience mechanic

Consistent picture across 2026 sources ([Socialync](https://www.socialync.io/blog/tiktok-algorithm-tips-new-accounts-2026), [posteverywhere](https://posteverywhere.ai/blog/how-the-tiktok-algorithm-works), [ReelForge](https://reelforgeai.io/blog/how-tiktok-algorithm-works-2026-complete-guide)):

1. Every upload gets pushed to a **small test batch** (~200–500 non-follower viewers for new accounts) chosen by inferred interest match from the video's caption/text/audio/visual signals.
2. The batch's **completion rate, rewatch, share, and comment velocity** determine whether the video graduates to the next, larger pool. Each tier is another test.
3. **Follower count is not a gate.** Zero-follower accounts regularly outperform established ones; content relevance beats creator popularity. New accounts effectively skip follower-testing and go straight to interest-matched strangers.
4. Weighting (one 2026 model): engagement signals ~40%, content signals (caption/hashtags/sound/text) ~35%, user-match signals ~25%. Completion + rewatch are the heaviest individual levers.

### Niche-finding / account classification

- TikTok classifies the *account* over its first ~10–30 posts by aggregating content signals. Scattered topics → the algorithm can't pick a test audience → chronically bad test batches → stall. Consistent niche signals (same keywords, same content category) → tighter interest-matched test audiences → higher baseline completion.
- Practical implication: one product niche per account; keep captions/on-screen text/spoken words converging on the same keyword cluster ("internships," "job applications," "resume," "college") so every video reinforces classification.

### Why accounts stall (the ~200-view ceiling)

- The infamous 100–300-view plateau = repeatedly failing the first test batch, or account-level suppression. Documented triggers ([Multilogin](https://multilogin.com/blog/tiktok-shadow-ban/), [dicloak](https://dicloak.com/blog-detail/why-your-tiktok-is-shadowbanned-stuck-at-200-views)):
  - **Burst posting**: 3–5 uploads in a short window → all stall at 100–300 views. Space uploads hours apart.
  - **Bot-like session signals**: multiple accounts on one IP/device, rapid network switching, API-ish behavior patterns. Linked accounts get suppressed together. (Directly relevant to an automated poster — jitter and human-like pacing are protective, which Mark already does.)
  - Watermarked/reposted content, engagement bait, banned-hashtag use.
  - Content that simply fails tests: weak hooks, no niche identity.
- Suppression isn't "lifted" — distribution resumes after the account behaves normally again (typically 2 weeks–1 month for real shadowbans; 3–5 days for minor cases).
- Realistic ramp for a good new account: week 1 → 100–500 views/video; week 4+ → 10K–100K possible; most SaaS accounts see first attributable conversions day 60–90 ([TokPortal](https://www.tokportal.com/use-cases/saas-tiktok-marketing-b2b-growth)). Sources converge on a **30-video minimum before judging anything**.

---

## 3. Humor norms: funny vs. cringe on 2026 TikTok

### The landscape

- **Brainrot/absurdism peaked and is now contested.** Italian Brainrot (AI-generated pseudo-Italian creature memes), "6-7," and layered irony dominated 2025 ([Wikipedia](https://en.wikipedia.org/wiki/Italian_brainrot)). By late 2025 a visible backlash formed — the "**Great Meme Reset of 2026**" ([Daily Dot](https://dailydot.com/great-meme-reset-of-2026-tiktok)) — users declaring meme culture bankrupt and demanding a refresh. Absurdism still works, but *default-mode* brainrot now reads as lazy. The safe posture in mid-2026: absurdity **with a point**, self-awareness about the slop itself.
- **What reads as cringe:** corporate polish pretending to be casual; chaos that feels pre-approved ("won't land if audiences can tell the chaos was pre-approved to adhere to brand guidelines" — [Pulsar](https://www.pulsarplatform.com/blog/2025/does-unhinged-marketing-work-and-can-anyone-do-it-from-utter-nutter-butter-chaos-to-duolingo-death)); joining a trend 2+ weeks late ("me when duolingo joined the trend, it got so boring"); millennial-pause energy; explaining the joke; forced product insertion.
- **What reads as funny:** hyper-specific relatability (the more specific the pain, the funnier — "the Workday account you made for one application in 2023" beats "job applications are annoying"); commitment to the bit without breaking character; self-aware lore-building; deadpan delivery of absurd claims; the product appearing as a background character rather than the punchline.

### The unhinged-brand playbook (does it actually work?)

- Mentions of "unhinged marketing" rose **25×** from end-2022 to end-2024. **Duolingo** reported a 51% increase in DAU in 2024 riding the unhinged-owl strategy (including killing Duo off). **Nutter Butter** built a surreal invented universe ("cooki," "nooder," recurring character Aidan) with multi-million-view posts — one hit 13.7M views / 133K shares ([Fast Company](https://www.fastcompany.com/91193826/nutter-butter-tiktok-marketing-strategy), [Pulsar](https://www.pulsarplatform.com/blog/2025/does-unhinged-marketing-work-and-can-anyone-do-it-from-utter-nutter-butter-chaos-to-duolingo-death)).
- Success factors: (1) **consistency** — a one-off weird post fails, a committed universe compounds ("commit to the bit"); (2) audience already fluent in internet absurdism (Gen Z — exactly SudoApply's audience); (3) posts function as **lore updates** that fans decode collaboratively in comments; (4) written by people with native internet instincts, not approval chains.
- Failures: Reese's/Oreo/Dunkin' got lower engagement than Nutter Butter despite far bigger followings — imitating the register without the commitment doesn't transfer.
- For deliberate "self-aware AI slop": TikTok is drowning in unmarked AI slop ([Futurism](https://futurism.com/artificial-intelligence/tiktok-taken-over-ai-slop)) and TikTok has shipped an AI-content slider/labeling. The differentiator that still lands is *acknowledged* absurdity — slop that knows it's slop and winks. Unlabeled sincere AI slop is increasingly penalized socially and (via labeling) algorithmically.

### Format-specific humor notes

- **POV format** evolved from character play into storytelling/product-demo hybrid; openers "POV:" and "When you…" + trending audio remain the standard container. POV setups are engineered to pull fast comments, which boosts the early test ([Accio](https://www.accio.com/business/pov_trend_on_tiktok), [Gain](https://blog.gainapp.com/tiktok-trends/)).
- **Greenscreen** = the "reacting to a screenshot/webpage" format — ideal for reacting to insane job postings ("entry level, 5 years experience required"), rejection emails, LinkedIn cringe. Low production, high relatability, naturally niche-classified.
- **Trend hijacking that works:** "This trend but make it [niche]" — take the trending sound/template and execute it inside job-hunt culture. Winners use trends as containers and add one twist that makes it theirs.

---

## 4. Software/app marketing on TikTok that actually worked

### Cal AI (calorie-scanning app) — the creator-network machine

- $0 → $1M/mo in ~6 months; $30M revenue 2025; ~$50M annualized by Jan 2026; acquired by MyFitnessPal ([Starter Story](https://www.starterstory.com/cal-ai-breakdown), [Superframeworks](https://superframeworks.com/case-study/cal-ai)).
- Mechanism: **not ads, not an official brand account** — a network of 250+ micro-influencers in fitness/food niches posting *native-style* videos. The core clip: creator points phone at a plate, calorie breakdown appears in ~3 seconds. **The product demo IS the hook** — value legible with zero explanation.
- Operational lesson: they messaged *hundreds* of creators, not ten. Volume outreach + a 3-second demoable moment.
- SudoApply translation: the equivalent money-shot is "watch this application fill itself in 5 seconds" — a screen recording of autofill ripping through a Workday form is the Cal-AI-plate moment.

### RizzGPT / Umax (Blake Anderson) — $50 creators + trending culture words

- Anderson built RizzGPT/Umax/looksmaxxing apps to ~$10M by paying **two unknown TikTok creators $50 each**; videos went viral overnight → hundreds of thousands of downloads ([Whop](https://whop.com/blog/looksmaxxing-blake-anderson/)).
- Mechanism: app concept itself was a trending-culture keyword ("rizz," "looksmaxxing") — the product name rides existing search/meme volume. Cheap unknown creators outperformed expensive ones because the *content concept* carried it.

### RIZZ App — faceless volume at industrial scale

- **550M+ views across 15+ faceless accounts** (@textcube averaged 1.4M views/video with a 25% viral rate) ([Shortimize](https://www.shortimize.com/blog/rizz-apps-b-roll-strategy-that-got-them-half-a-billion-views-on-tiktok)).
- Format: game b-roll (Minecraft) + animated fake-text conversation + cliffhanger scripting + subtle app appearance inside the story. 2–5 minute videos (long watch time), zero filming, fully script-drivable.
- Caveat for Mark: multiple accounts on shared infrastructure is exactly the linked-account suppression trigger from §2 — this play needs careful device/IP separation and is higher-risk under automation.

### Cluely (Roy Lee) — ragebait: works, then detonates

- "Cheat on everything" positioning → viral outrage → $15M a16z round ([TechCrunch](https://techcrunch.com/2025/10/29/cluelys-roy-lee-on-the-ragebait-strategy-for-startup-marketing/)). Lee's thesis: rage works because it threatens people's sense of competence/fairness; angry comments and dunk-shares are still distribution.
- Then: March 2026, Lee admitted fabricating revenue (~35% inflated); the company cratered ([Quasa](https://quasa.io/media/rage-bait-not-a-strategy-as-proven-by-cluely-s-implosion)). Verdict: ragebait is an ignition tactic, not a strategy. Usable in homeopathic doses (mildly contrarian takes: "cover letters are a scam") — not as identity. Notably, "cheating" positioning is specifically dangerous for a job-application product aimed at students.

### General SaaS-on-TikTok findings

- Software is inherently demonstrable: a 45-second screen recording of a feature saving 2 hours beats any explanation ([TokPortal](https://www.tokportal.com/verticals/tiktok-marketing-saas-companies)).
- 64% of users feel closer to brands posting human, unfiltered content (TikTok for Business research). Founder-face and "real person" content outperforms logo-brand content for early-stage products.
- Simplify (direct SudoApply competitor) markets via founder story ("dropped out of college to fix job applications") + free-forever positioning + job-search tips content — the education-first channel pattern.
- Expected timeline: ~30 days account warm-up, 30–60 days content testing, first attributable installs day 60–90. Do not judge the channel before ~30 posts.

---

## 5. Posting mechanics (cadence, hashtags/SEO, photo mode)

### Cadence

- Consensus for small/new accounts: **1–2 posts/day**, floor of 3–5/week ([Buffer 11M-post study](https://buffer.com/resources/how-often-should-you-post-on-tiktok/), [JoinBrands](https://joinbrands.com/blog/how-often-to-post-on-tiktok/)). Moving from 1×/week to 2–5×/week gave ~17% more views *per post* in Buffer's data.
- Quality dominates: three strong videos/week beat seven weak ones; low-effort volume dilutes account-level averages that feed classification.
- **Never burst-post**: 3–5 uploads within a short window reliably caps all of them at 100–300 views. Minimum several hours between posts.

### Hashtags & TikTok SEO (2026 reality)

- Hashtags are demoted to **supporting signals**. One cited weighting of the search algorithm: captions 40%, on-screen text 30%, hashtags 20%, audio 10% ([ALM Corp](https://almcorp.com/blog/tiktok-seo/), [SEO Sherpa](https://seosherpa.com/tiktok-seo/)).
- Use **3–5 specific hashtags** (niche + one mid-size), never 20 generic ones. Relevant hashtags still ~2× views vs. none.
- **Multi-layer keyword reinforcement** is the real mechanic: the same keyword cluster should appear in (a) the spoken audio, (b) on-screen text, (c) the caption, (d) hashtags. TikTok transcribes speech and OCRs overlays; each layer reinforces classification and search ranking. Keyword-optimized captions: +20–40% reach.
- Captions can now run to 4,000 characters; natural-language keyword phrasing ("how to apply to internships faster") beats hashtag-stuffing; mechanical keyword density trips spam filters.
- TikTok is a primary search engine for Gen Z — caption phrasing should match literal search queries ("internship application tips," "how to autofill job applications").

### Photo mode / carousels

- Uploaded via the native photo flow, carousels reach the FYP among non-followers immediately and are among the highest-reach organic formats in 2026 (multiple sources: 3–5× video reach, some accounts 10×).
- Mechanics: swipe = engagement signal; slide completion % = primary ranking input. 5–15 slides; 1080×1920 per slide; slide 1 is the hook (same rules as a video hook); background audio still applies (trending sound on a carousel is a cheap combo).
- Great fit for listicle/meme content: "8 red flags in a job posting," screenshot-meme dumps, fake-text stories rendered as slides.

### Timing

- Time-of-day matters far less than the first-hour engagement velocity it produces; heatmap data ([WaveGen](https://wavegen.ai/best-time-to-post-on-tiktok)) says post when the target audience is active — for US college students: late morning (11:00–13:00) and evening (19:00–23:00) local. Bandit-optimize rather than trusting static tables.

---

## Pipeline implications

Concrete rules an automated content system (Mark) should encode:

### Content strategy rules
1. **Hook = payoff-first.** Every video/carousel must show or state the outcome in second 1 (template: result on screen + ≤8-word overlay). Encode as a hard writer-agent constraint: "the first frame must show the transformation or make a specific promise."
2. **Default video length 20–35s**; allow 60–90s only for suspense-structured storytime scripts. Score generated scripts by estimated spoken duration and reject over-length.
3. **Prioritize three TikTok format archetypes** for SudoApply: (a) screen-recording demo with voiceover ("watch this application fill itself"), (b) greenscreen-style reaction to absurd job postings/rejection emails (image + persona commentary), (c) POV/relatable skit script ("POV: application #147"). These map cleanly onto Mark's existing video/image pipelines.
4. **Add native photo-mode carousels as a first-class TikTok content type** (currently TikTok is video-only in config). 5–15 slides, slide 1 = hook, listicle/meme structure. Highest reach-per-dollar format of 2026 — check upload-post.com support for TikTok photo posts.
5. **Fake-text story format** is the most automatable high-view format in existence (script → rendered chat bubbles → game b-roll). Worth a dedicated generator: LLM writes a job-hunt drama in message-thread form; renderer composites bubbles over stock gameplay; SudoApply appears inside the story, never as an ad.

### Humor calibration rules (writer-agent prompt constraints)
6. **Specificity is the joke.** Ban generic pain statements; require at least one hyper-specific detail per script (a real portal name like Workday, a real absurdity like "entry-level, 5 years experience"). The narrower the observation, the funnier.
7. **Self-aware absurdism only.** Deliberate AI-slop humor must wink at itself (acknowledge it's AI-generated slop); never play absurd content straight. Post-Great-Meme-Reset, unlabeled sincere brainrot reads lazy.
8. **Commit to the bit across posts.** Maintain persistent lore/characters/running gags in the DB (e.g., a recurring villain: "the ATS"; a recurring character arc) — unhinged one-offs fail, universes compound. Store bits in strategy_context and have the strategist reuse them.
9. **Ragebait ceiling:** allow mildly contrarian takes ("cover letters are a scam"), block outrage-positioning, and never frame SudoApply as "cheating" — category-specific reputational landmine (Cluely).
10. **Product placement rule:** SudoApply appears as background character/casual mention, never the punchline or a pitch. Cal AI/RIZZ pattern: the demo moment or the story carries the video; the product is incidental.

### Algorithm/SEO mechanics
11. **Keyword-stack every post across layers:** same 2–3 keyword phrases in spoken script + on-screen text + caption + 3–5 hashtags. Add a "keyword cluster" field to ContentDraft and validate all four layers contain it.
12. **Niche consistency:** keep every TikTok post inside the job-hunt/internship/college-career cluster for at least the first 30 posts so the account classifies cleanly. The strategist should not "explore" off-niche topics on TikTok early.
13. **Never burst-post:** enforce ≥4h minimum spacing between TikTok uploads in the scheduler (jitter already exists; add a hard spacing floor).
14. **Trend reaction latency target: <24h, ideally <12h.** Trend half-life is now ~72h peak / 5-day death. Mark's trend cron (2×/day) is the right frequency, but the generate→approve→post loop must complete same-day for trend-tagged content; consider auto-flagging trend-reactive drafts for priority approval.
15. **Word-synced captions are mandatory** on all voiceover video (already in Mark's pipeline — keep: bold sans-serif, white + black stroke, current-word highlight). Static subtitles read as dated.
16. **Account type:** use a personal/creator-style account, not a business account, to retain full trending-audio access (business accounts are locked to the Commercial Music Library).
17. **Success criteria & patience:** don't evaluate TikTok performance before ~30 posts; expect 100–500 views/post in week 1; treat >50% average watch-time and completion trends as the KPIs to feed the bandit (not likes). Reward function should weight completion-rate proxies (views growth per post over time) above raw engagement counts.
18. **Hashtag config:** set TikTok hashtag_count to 3–5 highly specific tags (current config already says 5 — keep, but bias generation toward niche tags, not #fyp-style generic ones).

### Key sources
- [OpusClip hook data (34,635 clips)](https://www.opus.pro/blog/tiktok-hooks-that-go-viral-2026) · [OpusClip length data](https://www.opus.pro/blog/how-long-should-a-tiktok-be-2026)
- [Socialync — algorithm for new accounts 2026](https://www.socialync.io/blog/tiktok-algorithm-tips-new-accounts-2026) · [Socialync — 2026 algorithm changes](https://www.socialync.io/blog/tiktok-algorithm-2026-what-works-now)
- [Buffer 11M-post cadence study](https://buffer.com/resources/how-often-should-you-post-on-tiktok/)
- [Retensis retention benchmarks](https://retensis.com/blog/tiktok-retention-rate-benchmarks-2026)
- [ReelBase photo-mode algorithm](https://reelbase.io/blog/tiktok-photo-mode-algorithm-explained)
- [ALM Corp TikTok SEO](https://almcorp.com/blog/tiktok-seo/) · [SEO Sherpa](https://seosherpa.com/tiktok-seo/)
- [Starter Story — Cal AI](https://www.starterstory.com/cal-ai-breakdown) · [Superframeworks — Cal AI](https://superframeworks.com/case-study/cal-ai)
- [Shortimize — RIZZ App b-roll strategy](https://www.shortimize.com/blog/rizz-apps-b-roll-strategy-that-got-them-half-a-billion-views-on-tiktok)
- [Whop — Blake Anderson / RizzGPT](https://whop.com/blog/looksmaxxing-blake-anderson/)
- [TechCrunch — Cluely ragebait](https://techcrunch.com/2025/10/29/cluelys-roy-lee-on-the-ragebait-strategy-for-startup-marketing/) · [Quasa — Cluely implosion](https://quasa.io/media/rage-bait-not-a-strategy-as-proven-by-cluely-s-implosion)
- [Pulsar — unhinged marketing analysis](https://www.pulsarplatform.com/blog/2025/does-unhinged-marketing-work-and-can-anyone-do-it-from-utter-nutter-butter-chaos-to-duolingo-death) · [Fast Company — Nutter Butter](https://www.fastcompany.com/91193826/nutter-butter-tiktok-marketing-strategy)
- [Daily Dot — Great Meme Reset 2026](https://dailydot.com/great-meme-reset-of-2026-tiktok) · [Wikipedia — Italian brainrot](https://en.wikipedia.org/wiki/Italian_brainrot)
- [Multilogin — shadowban mechanics](https://multilogin.com/blog/tiktok-shadow-ban/) · [dicloak — 200-view ceiling](https://dicloak.com/blog-detail/why-your-tiktok-is-shadowbanned-stuck-at-200-views)
- [unil.ink — 2026 trends](https://unil.ink/blog/tiktok-trends-2026) · [Gain — trend velocity](https://blog.gainapp.com/tiktok-trends/) · [ContentGrip — Gen Z trends](https://www.contentgrip.com/tiktok-trends-gen-z-marketing-guide/)
- [TokPortal — SaaS on TikTok](https://www.tokportal.com/verticals/tiktok-marketing-saas-companies)
- [Blitzcut — caption fonts](https://blitzcutai.com/blog/best-caption-fonts-tiktok) · [TikTok Sans open source](https://developers.tiktok.com/blog/tiktok-sans-open-source)
- [Clippie — fake text story format](https://clippie.ai/blog/how-to-create-fake-text-message-story-videos)
