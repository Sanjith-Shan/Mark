# MASTER STRATEGY SPEC — Mark / SudoApply

**Status:** Source of truth for content-strategy implementation. Synthesized July 2026 from the 12 research reports in `docs/research/`.
**Product:** SudoApply — AI job-application tool for college students (18–24).
**Reader:** the engineer implementing Mark's strategist/writer/media/trends/learning modules.

---

## 0. The Core Thesis (read this first)

Every decision below flows from five load-bearing facts established in the research:

1. **The audience's terrain is a shared trauma.** Entry-level postings down 35%, 61% of seniors pessimistic, "application-maxxing" (70+ apps per offer) is the named behavior. Job-hunt despair humor is pre-validated, evergreen, and exactly on-product. The brand's only permitted stance: **fellow victim with a weapon**. Mock the system (ATS, recruiters, ghosting, LinkedIn cringe) — never the student.
2. **The narrative asymmetry SudoApply owns:** "They automated rejecting you, so automate applying." The enemy is *their* AI (screeners); SudoApply is *your* AI (fighting back). The account being openly AI-run is on-lore, not a scandal.
3. **Self-aware AI is the only safe AI.** Audiences rate AI comedy higher when it acknowledges being AI (CHI 2026); 50% of Gen Z have blocked a brand for slop-feel; unlabeled earnest AI content is the #1 trust killer. Three safe modes only: (a) obviously-absurd AI played as intentional comedy, (b) labeled/winking AI, (c) text so voice-specific it's indistinguishable from human. Never counterfeit sincerity.
4. **Humor is an engineering problem: generate-many, rank-hard.** One-shot LLM jokes fail (predictable, hedged, over-explained). The validated pipeline is violation-search → structural scaffold → persona fan-out → pairwise judging → punch-up. Judges calibrated on real engagement data reach expert-level ranking (67%→82.4%).
5. **Commitment beats novelty.** Every documented brand win (Duolingo, Nutter Butter, Soren Iverson) is a *committed franchise/universe*, not one-off gags. Series, recurring characters, and callbacks are the follower-conversion mechanism and also solve the pipeline's hardest problem (deciding what to make).

**Global KPI philosophy:** optimize for completion/retention, sends/saves ("sendable to the group chat"), and comment depth — not likes or impressions. Judge nothing before ~30 posts per platform.

---

## 1. Strategy Catalog

Twelve named strategies. Each is a first-class object in config and a `strategy_pillar` bandit arm. Platform fit legend: ●=primary, ◐=adapted, ○=avoid.

### Master fit matrix

| id | TikTok | IG | X | LinkedIn | Shorts | Threads | Bluesky | Reddit |
|---|---|---|---|---|---|---|---|---|
| pain-point-povs | ● | ● | ● | ◐ | ● | ● | ◐ | ◐(draft) |
| absurdist-ai-slop | ● | ◐ | ● | ○ | ● | ◐ | **○ never** | ○ |
| unhinged-mascot | ● | ● | ◐ | ○ | ● | ◐ | ○ | ○ |
| satirical-ui-franchise | ◐ | ◐ | ● | ◐ | ○ | ◐ | ◐ | ○ |
| demo-magic | ● | ● | ◐ | ○ | ● | ○ | ○ | ◐(draft) |
| educational-hooks | ● | ● | ◐ | ● | ● | ◐ | ◐ | ●(draft) |
| meme-carousels | ● | ● | ○ | ◐(PDF) | ○ | ○ | ○ | ○ |
| trend-jack | ● | ◐(lagged) | ● | ○ | ◐ | ● | ◐ | ○ |
| contrarian-takes | ◐ | ○ | ● | ● | ○ | ● | ◐ | ○ |
| social-proof-receipts | ◐ | ◐ | ● | ● | ◐ | ◐ | ◐ | ◐(draft) |
| fake-text-drama | ● | ◐ | ○ | ○ | ● | ○ | ○ | ○ |
| founder-build-log | ○ | ○ | ● | ● | ○ | ◐ | ● | ●(draft) |

---

### 1.1 `pain-point-povs` — Hyper-specific job-hunt pain, dramatized

**Description.** POV skits, greenscreen reactions, and one-liners that dramatize one *hyper-specific* moment of job-hunt suffering ("POV: it's 2:47 AM, application #83, the portal made you re-type your resume after uploading it"). The specificity IS the joke; the comment section completes it (everyone posts their own number).
**Emotional target:** recognition ("too real") + dark-humor laughter. Engagement mechanism is belonging, not evaluation — commenting "same" is an act of membership.
**Content types:** video (POV skit, greenscreen-over-screenshot), text one-liner, image (screenshot + dry caption).

**Platform adaptation:**
- TikTok/Shorts: 20–35s POV or greenscreen reaction to an absurd job posting / rejection email. Word-synced captions mandatory.
- IG Reels: same, one notch more polish; CTA aimed at *sends* ("send this to your roommate with 0 offers").
- X/Threads: lowercase one-liner, screenshot-shaped, leaves an obvious slot for readers to QT their own version. Threads variant ends in a sincere question ("what's your rejection count").
- LinkedIn: soften to pain-point-confession register (satire quota, §4.4).
- Reddit: as comment material in r/recruitinghell-style threads — draft-only.

**Generation recipe:**
1. *Strategist:* pick one vein from the pain-vein pool (see §1.1.1) + a platform + a register (`ironic|dark|absurdist`). Inject 3–5 items from the specificity bank.
2. *Writer:* run the full humor engine (§2). Hard constraint: ≥1 hyper-specific artifact (named portal, verbatim rejection phrasing, precise absurd number — "application #83" not "lots of applications"). Ban category-level pain ("job hunting is hard"). End on the punch; no explanation. Implicit comment prompt (arguable/completable), never "comment below."
3. *Media:* video = TTS voiceover (deadpan, "someone who has applied to 400 jobs" instruction) + screen/b-roll/static aesthetic background + word-synced captions; image = fake screenshot rendered via Pillow/gpt-image-2.

**Pain-vein pool (§1.1.1)** — maintain in DB, refresh from r/recruitinghell + trends: ghosting after 5 rounds; "entry level, 7 years experience"; AI-personality-test-for-a-janitor; 7-round interview inflation; rejection-email template parody ("we were impressed, however…"); rejected by a company you don't remember applying to; the Workday account made for one application in 2023; re-type-your-resume portals; "open to work" ring despair; recruiter LinkedIn-speak.

**Example sketches:**
1. *TikTok video:* on-screen text "POV: round 7 of interviews for an unpaid internship" — deadpan TTS narrates a wellness-check script while a calendar fills with interview blocks. Final beat: "they went with an internal candidate." Loop back to frame 1.
2. *X post:* `got a rejection email today from a company i applied to in 2023. the workday account outlived my hope. it outlived the role. it may outlive me`
3. *Greenscreen:* screenshot of a real (anonymized) "entry-level, 5 years experience, $17/hr" posting; persona commentary: "and the personality test was 45 minutes."

**Success metrics:** comment rate + comment-your-own-version behavior; shares/sends; watch-through >50%. Bandit arms: pain vein, register, format.

```yaml
strategy: pain-point-povs
platforms: [tiktok, instagram, x, threads, youtube, linkedin]
content_types: [video, text, image]
registers: [ironic, dark, absurdist]
constraints:
  min_specific_artifacts: 1
  ban_generic_pain_statements: true
  end_on_punch: true
  comment_prompt: implicit
mix_weight: 0.25   # highest-volume workhorse
```

---

### 1.2 `absurdist-ai-slop` — Self-aware AI absurdism (the sanctioned slop lane)

**Description.** Deliberately absurd AI-generated video/images that *know* they're AI slop and wink at it. Two-axis rule: maximize premise absurdity AND render fidelity simultaneously (photoreal cat on a diving board, not mildly-weird mush). The absurdity must metaphorically encode the value prop (Kalshi rule): chaos = what the job hunt feels like / what SudoApply removes.
**Emotional target:** laughter (incongruity + uncanny-absurd gap) + insider status ("I get the bit").
**Content types:** video (AI-generated), image, occasionally meta-content (tier lists, lore posts).

**Platform adaptation:** TikTok/Shorts native (label AI, always); X as image + winking caption; IG Reels with explicit wink in overlay; **NEVER Bluesky** (blocklist propagation is permanent), never Reddit, never LinkedIn (dilute to "personality" only). Post-Great-Meme-Reset rule: absurdity must have *a point*; default-mode brainrot reads lazy in 2026.

**Generation recipe:**
1. *Strategist:* pick a rigid template (the template IS the game): (a) hyper-real production grammar (bodycam/CCTV/news-chyron/ring-cam/selfie-vlog) + one impossible job-hunt subject played completely straight; (b) brainrot-character lane (hybrid creature + chantable name + deadpan TTS lore); (c) AI-ASMR/satisfying lane mapped to product ("the sound of 200 applications auto-filling").
2. *Writer:* gag-densification — brainstorm 15–20 sight gags, require ≥1 per 3 seconds of video; caption is deadpan-short, lowercase, self-aware ("we generated this instead of applying to jobs for you. wait. no. we did both"). Caption must acknowledge the bit.
3. *Media:* model routing per §6.3 (Sora 2 for absurd-played-straight while it lasts; Hailuo for slapstick; Veo 3.1 for spoken; Kling for recurring characters). Audio-first: repeatable sound hook in first 2s. End prompts with "no subtitles, no text overlay"; burn captions in post. Set platform AI labels (TikTok synthetic toggle, Meta "Made with AI", YouTube flag) — mandatory.

**Cringe filter (auto-reject at approval):** logo/CTA in first 3s; model-rendered text in frame; weird-without-a-punchline; rides a wave older than ~6 weeks; earnest framing of AI content.

**Example sketches:**
1. *Bodycam footage* of an "ATS raid": officers kick down a server-room door where a printer is shredding resumes; chyron: "LOCAL ATS CAUGHT REJECTING 4,000 QUALIFIED APPLICANTS IN 0.3 SECONDS." Caption: "dramatization. (it was faster.)"
2. *AI-ASMR:* macro shot, glass keyboard keys being sliced like fruit, each cut auto-fills a form field. Caption: "asmr for people with 83 open applications #ai"
3. *Selfie-vlog:* a photoreal pigeon in a tiny suit "commuting" to hand-deliver a resume, gets ghosted by a revolving door. Spoken: "day 400. the door said we'll circle back."

**Success metrics:** completion + rewatch/loop rate; share rate; follower delta per post. Kill criterion: anti-AI comments out-liking the post → tighten the wink or pause the lane 2 weeks.

```yaml
strategy: absurdist-ai-slop
platforms: [tiktok, youtube, x, instagram, threads]
banned_platforms: [bluesky, reddit, linkedin]
templates: [hyperreal_grammar, brainrot_character, ai_asmr]
constraints:
  self_aware_caption: required
  ai_label: required
  sight_gag_density: 1_per_3s
  premise_absurd_AND_render_crisp: true
mix_weight: 0.10
```

---

### 1.3 `unhinged-mascot` — Character episodes (the lore engine)

**Description.** Episodic content starring the AI ambassador characters (§7). Each post is a lore update in an ongoing universe: running counters, recurring NPCs, escalating arcs. This is the account-level "game" (UCB structure): one unusual thing, heightened for months. Commitment-to-the-bit is the single strongest documented success factor (Nutter Butter 3.1K→700K; Duolingo).
**Emotional target:** belonging/insider status + laughter + micro-parasocial attachment (community-mediated: followers bond with each other about the character).
**Content types:** video (vlog grammar), image (character stills + caption), text (character "posting").

**Platform adaptation:** TikTok/Reels/Shorts = vlog episodes; X/Threads = the character's text posts (in-voice, lowercase); the character's fake "LinkedIn posts" as image posts on other platforms (free cross-platform gag). Not LinkedIn/Bluesky/Reddit.

**Generation recipe:**
1. *Strategist (`character_episode` mode):* inputs = character bible + lore state (counters, active arcs, NPCs) + current trends + past episode performance. Output = next episode beat. **Must reference ≥1 prior event or counter** (callbacks are the follower-conversion mechanism). On approval, update lore counters in DB.
2. *Writer:* fixed persona block interpolated verbatim (voice, tics, wants, flaw, self-aware-AI stance). Humor engine applies. Episode structure: one game, 3–5 heightens, out at peak. Never explain lore in-post.
3. *Media:* character-sheet-driven consistency pipeline (§7.4). Visual anchor prop required in every prompt. FTC/platform disclosure baked into templates (§7.5).

**Hard guards:** no testimonials from the character ("SudoApply got me a job" is FTC-prohibited and tonally wrong — it *demos, bits, and begrudgingly admits the app saves it time*); never name real companies/recruiters as villains; never auto-reply to sensitive comment threads (visa panic, mental health); comment mining feeds next-episode topics ("you're all saying it has beef with Workday — it does now").

**Example sketches:** see §7.2 concepts.

**Success metrics:** comment/share rate weighted over views (community formation); catchphrase adoption in comments (leading indicator); return-viewer/series retention. Track engagement at character level, not just post level.

```yaml
strategy: unhinged-mascot
platforms: [tiktok, instagram, youtube, x, threads]
depends_on: characters/apply_guy.yaml
episode_cadence: 2-3/week per character
constraints:
  callback_required: true
  testimonial_ban: true
  disclosure: ftc_double + platform_labels
mix_weight: 0.15
```

---

### 1.4 `satirical-ui-franchise` — Daily fake job-app UI mockups (Soren Iverson clone)

**Description.** One repeatable visual franchise: satirical UI mockups of job-application software with one unhinged-but-plausible feature ("LinkedIn now shows recruiters your bank balance so they can calibrate the lowball"; "Workday Premium: pay $4.99 to have a human see your resume"). Recognizable UI = instant parse; the joke lives in the image; caption is one dry line. Soren Iverson grew 2K→72K in ~6 months on this exact format. Infinitely repeatable = a franchise, not one-off jokes. Directly on-product: the raw material is the software the audience already hates.
**Emotional target:** recognition + laughter (benign violation of product-design norms) + righteous frustration at the system.
**Content types:** image (the mockup), posted natively.

**Platform adaptation:** X is home (daily); IG/TikTok as carousel slides (batch 5–8 into a themed carousel); LinkedIn sparingly (satire quota — the safest LinkedIn-compatible joke format since it satirizes tools, not people); Threads/Bluesky occasional (a *clean, human-designed* mockup passes the Bluesky no-AI-media bar if rendered from real UI kits, not generative fill — mark `human_made_render: true`).

**Generation recipe:**
1. *Strategist:* pick target surface (ATS form, LinkedIn feature, rejection email UI, interview scheduler, job-board filter) + one violation from the humor engine's violation search.
2. *Writer:* the feature concept must pass the "unhinged but one board meeting away from real" test — plausibility is the benign anchor, cruelty of the real system is the violation. One dry caption line, lowercase, no explanation.
3. *Media:* render deterministically — Pillow composition over UI component templates (buttons, form fields, toggles in Workday/LinkedIn-adjacent-but-legally-distinct styling), or gpt-image-2 for organic look where text fidelity allows. **Never model-rendered garbled text** — text is the joke, so it must be pixel-perfect. Build a small reusable UI-kit asset library once.

**Example sketches:**
1. Job posting card with a live counter: "Applicants: 2,847 · Positions: 1 · Your percentile: don't."
2. ATS upload screen: "Resume uploaded successfully. Please now re-type your resume. [Autofill] button greyed out, tooltip: 'Autofill is a premium feature for employers only.'"
3. Calendar invite: "Interview Round 8 of ∞ — 'Final final culture fit vibe check' — Declining this invite withdraws your application."

**Success metrics:** X: QT ratio + bookmarks; IG: sends + saves. This is the cheapest daily-cadence franchise in the whole system (one image/day, ~$0.05).

```yaml
strategy: satirical-ui-franchise
platforms: [x, instagram, tiktok, linkedin, threads, bluesky]
cadence: 1/day on x; weekly carousel compilations elsewhere
render: pillow_ui_kit   # deterministic text; gpt-image-2 fallback
caption: one_dry_line_lowercase
mix_weight: 0.12
```

---

### 1.5 `demo-magic` — Faceless product-demo showcases (the Cal AI play)

**Description.** Screen recordings where the product performs its 3-second magic trick: "watch this application fill itself in 5 seconds." The demo IS the hook (best-performing hook category in 34K-clip data: outcome shown in first 2 seconds). Zero AI-labeling risk (it's a real screen recording). Before/after is the default frame: "job application: 45 minutes → 45 seconds."
**Emotional target:** satisfaction (the transformation is self-evidently the value) + mild disbelief ("why did nobody tell me about this app").
**Content types:** video (screen recording + hook overlay + optional voiceover), satisfying UI loops (kanban cards sliding to "Interview", statuses flipping to "submitted").

**Platform adaptation:** TikTok/Reels/Shorts primary (15–30s); IG optimize for profile visits/follows; X as native short vertical video (<60s gets top format boost); Reddit only inside founder-story drafts.

**Generation recipe:**
1. *Strategist:* pick a demo moment (autofill ripping through a Workday form; 60 applications during one lecture time-lapse; tracker before/after) + hook archetype (outcome-first / "you're applying to jobs wrong" mistake-frame / audience callout).
2. *Writer:* hook overlay ≤8 words, on screen frame 1, must work muted. Keyword-stack: same 2–3 search phrases in spoken audio + on-screen text + caption ("how to autofill job applications", "apply to internships faster"). Product appears as the tool, soft CTA only ("link in bio" / comment-keyword→DM on IG).
3. *Media:* real screen captures from a demo account (pre-recorded library of raw captures, re-cut per post with different hooks/pacing — never byte-identical uploads); cursor highlights; word-synced captions if voiceover; satisfying-loop variants end where they start.

**Hard rule:** all numbers/screens must be REAL (from the demo/product DB). Never fabricate results — fabricated proof is the documented existential failure (Cluely).

**Example sketches:**
1. Hook overlay: "45 minutes of your life. or 45 seconds." → split screen: manual form-filling drudgery time-lapse vs autofill blazing through the same form → end card: tracker column filling.
2. "watch my AI apply to 12 internships while i eat lunch" — time-lapse, lo-fi, phone-framed screen, deadpan VO.
3. Satisfying loop: kanban card slides Applied→Interview with a soft click; loops seamlessly; caption "the only satisfying part of job hunting."

**Success metrics:** profile visits + follows per reach; completion; attributable installs (expect day 60–90). This is the conversion engine other strategies feed.

```yaml
strategy: demo-magic
platforms: [tiktok, instagram, youtube, x]
content_types: [video]
hook: outcome_first_overlay_max_8_words
data_source: real_captures_only
length_s: [15, 30]
mix_weight: 0.12
```

---

### 1.6 `educational-hooks` — CareerTok tactical value content

**Description.** Save-worthy, hyper-tactical job-search advice: "the exact email to send a recruiter who ghosted you after round 2," "7 resume lines that got interviews," "apply within 1 hour of a posting going live" (the Michael Yan/Simplify pattern: specific tactical claims with numbers). 46% of Gen Z secured a job/internship via TikTok; 92% trust it for career advice; HR/job-search topics carry a 1.54x LinkedIn reach multiplier. The tip must stand alone; the product is step 3, never the headline.
**Emotional target:** satisfaction/utility + aspiration (underdog empathy: non-target-school students can win).
**Content types:** video (45–60s value Reels/TikToks), carousel (TikTok photo-mode 5–7 slides; IG 8–12; LinkedIn 6–8 slide PDF), text (X long-form, LinkedIn 1000+ chars), Reddit answer drafts.

**Generation recipe:**
1. *Strategist:* pick from a curated **fact base** (tactical claims + real stats, updated quarterly: "entry-level postings −35%", "26% more applicants per job") + format + platform. Oddly-specific beats generic — reject "networking tips"-grade topics.
2. *Writer:* hook = authority signal → curiosity gap → payoff promise ("I watched 1,000 applications get auto-rejected — here's the form field that did it"). Every post: ≥1 concrete number, named tool, or verbatim example. Anti-slop lint (§2.6). CTA per platform signal: saves ("save this for application season") on carousels; sends on Reels.
3. *Media:* carousel templates (3–5 reusable layouts, ≤12 words/slide, slide 1 = incomplete-feeling hook, slide 2 = proof/roadmap, last slide = CTA); LinkedIn renders same content as PDF document post, caption ≤100 chars.

**Example sketches:**
1. Carousel: "your resume gets 7.4 seconds. here's what they actually see" → eye-tracking-style heatmap slides → last slide: "the ATS sees even less. save this."
2. Video: "recruiters auto-reject applications missing THIS field. i checked 200 postings" → screen-record proof → tip → "sudoapply fills it automatically but you can also just… fill it."
3. LinkedIn PDF: "The 6-step internship application system (from analyzing 40,000 applications)."

**Success metrics:** saves per reach (dominant), follows per 1K reach, search-driven long-tail views (Shorts/YouTube). Highest-automatability strategy — fully templated.

```yaml
strategy: educational-hooks
platforms: [tiktok, instagram, linkedin, youtube, x, threads, reddit_draft]
fact_base: data/fact_base.yaml   # curated claims + stats; writer may only cite from here
carousel_slides: {tiktok: 5-7, instagram: 8-12, linkedin: 6-8}
constraints: {min_concrete_details: 1, generic_advice_lint: reject}
mix_weight: 0.15
```

---

### 1.7 `meme-carousels` — Original meme sequences

**Description.** 5–8 original job-hunt memes on one theme per carousel; each swipe is another punchline ("this whole post is us" → sends). Memes get ~60% higher engagement than branded graphics; meme carousels are IG's highest-engagement format class; TikTok photo-mode gets 3–5x video reach. Must be *original/transformative* (own joke layer) — repost aggregation is algorithmically dead (IG originality rule) and an account-level kill risk.
**Emotional target:** recognition + laughter; group-chat sendability.
**Content types:** carousel (native photo flow on TikTok — critical), image.

**Generation recipe:**
1. *Strategist:* theme (one pain vein) + template freshness check — poll Imgflip `get_memes` for currently-alive formats; dead template = worse than no meme.
2. *Writer:* humor engine per slide; rule-of-three across the deck (slides 1–2 establish pattern, slide 3+ breaks it); escalate through the deck; strongest meme last-but-one, CTA last.
3. *Media:* LLM writes joke + picks template → Pillow renders (100% text fidelity) or gpt-image-2 for organic non-template memes (LinkedIn/IG polish tier). 1080×1920 TikTok slides / 4:5 1080×1350 IG. Attach music (Reels-tab eligibility; trending sound on a TikTok carousel is a cheap combo that dodges the API sound constraint — carousel audio is background, not the mechanic).

**Example sketch:** theme "stages of one application" — slide 1: applying (hope meme); slide 2: the confirmation email (fine); slide 3: 6 weeks of silence (skeleton at desk); slide 4: rejection at 2:47 AM (why are you awake); slide 5: "start again. or don't [app icon, tiny]".

**Success metrics:** slide completion, sends, saves. Bandit arm: template vs organic; theme.

```yaml
strategy: meme-carousels
platforms: [tiktok_photo_mode, instagram]
slides: 5-8
template_source: imgflip_get_memes_live   # freshness gate
render: pillow_primary
mix_weight: 0.08
```

---

### 1.8 `trend-jack` — Fast trend/format riding

**Description.** Map a fresh trend (sound, format, discourse moment, job-market news) onto a house format within hours. Trends are rented distribution; speed is the entire value (half-life: memes 3–5 days, sounds 1–3 weeks; brand adoption marks the death phase). Full system spec in §6. **The strategist skips 80–90% of detected trends** — Duolingo-grade accounts are defined by what they don't post.
**Emotional target:** insider status ("they got the bit fast") + whatever the trend's native emotion is.
**Content types:** fastest sufficient type — text riff ships in minutes, image in ~30 min, video in ~1h.

**Generation recipe:** the fast-path in §6.4. Key constraints: product appears ≤1 time, never in the hook, never as the punchline resolution; joke must survive removing the product name; New/Rising stages only; expiring approvals (24–72h TTL, auto-reject stale).

**Example sketches:**
1. Trending sound whose format = "listing increasingly unhinged things calmly" → job-hunt payload: calmly listing real requirements from one entry-level posting.
2. Layoff-news day: same-day X post — "companies: we can't find talent. also companies: [screenshot of 4,000-applicant posting]." Reels adaptation day 3.
3. New video-model capability week (§6.5 capability-window trigger): first-mover absurdist demo in the new model's signature style, on-product.

**Success metrics:** detection→live latency (target 2–6h); reach multiplier vs account baseline; fit-gate precision (post-hoc: did skipped trends outperform elsewhere?).

```yaml
strategy: trend-jack
platforms: [tiktok, x, threads, instagram_lagged, youtube]
daily_cap: 3
fit_threshold: 0.6
ttl: {new: 24h, rising: 72h}
product_mention: {max: 1, never_hook: true, never_punchline: true}
mix_weight: 0.08   # event-driven, cap-bounded
```

---

### 1.9 `contrarian-takes` — Defensible spice (defanged ragebait)

**Description.** Strong opinions about the job-search system stated without hedging: "cover letters are a scam and recruiters know it," "the career center is lying to you," "applying manually to internships is a waste of your life." Disagreement → replies → distribution (replies weighted 13.5–27x a like on X). Villain is always a system/process, never a person or named company. **Hard ceiling:** spice, not rage — Cluely proved ragebait buys awareness and burns trust; "cheating" framing is a category-specific landmine for a job tool. Never manufactured outrage, never fabrication.
**Emotional target:** righteous frustration (catharsis) + debate energy.
**Content types:** text (X single posts, LinkedIn long-text, Threads with question softening), occasionally image (receipt attached).

**Generation recipe:**
1. *Strategist:* pick take from a **whitelisted-target take pool** (targets: ATS, ghosting culture, unpaid internships, interview inflation, credential inflation, career-center advice, cover letters). Generate takes with a defensible edge; attach the defense (data point from fact base).
2. *Writer:* state it flat, no hedging, one idea, screenshot-length. X: lowercase ok. LinkedIn: pain-point-confession or number-claim wrapper, 1000+ chars, ban "Stop doing X" template (saturated). Threads: append a genuine question (positivity-biased ranking).
3. *Post-hooks:* these posts NEED first-hour reply babysitting (§4.3) — schedule accordingly.

**Example sketches:**
1. X: `cover letters are a loyalty test for a company that will ghost you. write zero. apply to 3x more. the math has never once favored the letter`
2. LinkedIn: "We analyzed 40,000 applications. The tailored-resume advice cost students ~9 hours per offer and changed outcomes in fewer than 2% of cases. The single thing that did move outcomes: applying within 24 hours of posting. [data] What's the worst time-per-application advice you've been given?"
3. Threads: "unpopular opinion: GPA has never gotten anyone past an ATS. what actually did it for you?"

**Success metrics:** X QT:like ratio + reply velocity; LinkedIn comment depth. Kill-switch: sustained negative-feedback signals (mutes/blocks damage author reputation cumulatively) → cool down 1 week.

```yaml
strategy: contrarian-takes
platforms: [x, linkedin, threads, bluesky]
take_targets_whitelist: [ats, ghosting, unpaid_internships, interview_inflation, cover_letters, career_center_advice, credential_inflation]
banned: [named_companies, named_people, cheating_framing, fabricated_claims, manufactured_outrage]
requires: first_hour_reply_window
mix_weight: 0.08
```

---

### 1.10 `social-proof-receipts` — Real-data receipts and before/afters

**Description.** Screenshot-shaped proof from REAL product data only: aggregate stats ("our users sent 40,000 applications last month; here's what got replies"), tracker before/afters, blurred interview-invite receipts ("the AI applied while I was asleep"), weird-data drops ("we watched 1,000 applications get auto-rejected in 0.3 seconds. here's the form field that did it"). Doubles as educational content. This is seasoning (~10% of mix), not the meal — over-posting reads as brag spam.
**Emotional target:** aspiration + trust (72% find customer evidence more credible than brand claims).
**Content types:** image (screenshot templates), text (stat + commentary), short video (time-lapse).

**Generation recipe:**
1. *Strategist:* query the production DB for genuinely notable numbers/events (thresholded: only surface stats that beat novelty criteria). Permissioned user quotes only.
2. *Writer:* bragworthy-stat or behind-the-curtain hook archetype; number must be verbatim from the DB — **the writer agent may never invent metrics, testimonials, or outcomes** (hard validation: every number in draft must match a DB query recorded in strategy_context).
3. *Media:* screenshot templates (tracker UI, stats card) rendered from live data via Pillow; blur PII.

**Example sketches:**
1. X: dashboard screenshot — "users applied to 40,000 jobs last month. total human minutes spent: fewer than one career fair."
2. IG: before/after kanban — "week 1 vs week 6" (real anonymized tracker).
3. "receipt drop": blurred interview invite email, caption "sent at 2am. by the robot. while they slept."

**Success metrics:** profile visits, bookmarks (X), conversion-adjacent clicks. Validation rule is the whole strategy: fabrication = existential.

```yaml
strategy: social-proof-receipts
platforms: [x, linkedin, instagram, tiktok, threads, bluesky]
data_source: production_db_only
validation: numbers_must_match_recorded_query
pii: blur_required
mix_weight: 0.05
```

---

### 1.11 `fake-text-drama` — Message-thread story videos

**Description.** Mini soap operas rendered as animated iMessage/DM conversations over game b-roll (Minecraft parkour etc.) — job-hunt dramas in message form (group chat reacting to a 7-round interview; recruiter ghosting arc with a twist). Millions of views per video, zero filming, fully scriptable — the most automatable high-view format in existence (RIZZ App: 550M+ views). SudoApply appears *inside the story* as an app someone mentions, never as an ad.
**Emotional target:** suspense → recognition → laughter (cliffhanger scripting drives completion).
**Content types:** video (rendered chat bubbles + b-roll), TikTok photo-mode variant (thread as slides).

**Generation recipe:**
1. *Strategist:* pick a drama premise from pain veins + a twist type (betrayal/absurd escalation/justice).
2. *Writer:* script as message thread; hook = first message must be a scroll-stopper ("my recruiter just texted me at 11pm…"); cliffhanger beats every ~8s; humor engine for the punch messages; product placed as incidental mention mid-story at most.
3. *Media:* dedicated renderer — chat-bubble compositor (Pillow/MoviePy) over licensed/stock gameplay b-roll; typed-message pacing synced to beats; TTS optional. No AI-label needed (no photoreal synthetic humans).

**Example sketch:** group chat "job hunt support group 💀": one member announces round 9 of interviews; escalating absurd interview tasks ("they want me to do a case study on their case study"); twist: the "company" posting was a ghost job reposted for 14 months; final message screenshot of the reposted listing. Caption: "part 2 if he escapes."

**Success metrics:** completion on 2–5min videos (watch-time monster), part-2 demand in comments, follows. Risk note: single-account only (multi-account farming = linked-account suppression).

```yaml
strategy: fake-text-drama
platforms: [tiktok, youtube, instagram]
length: 60-180s
renderer: chat_bubble_compositor
series: true   # numbered parts, payoff must land
mix_weight: 0.07
```

---

### 1.12 `founder-build-log` — Build-in-public (draft-assist only)

**Description.** First-person founder posts drafted from REAL repo/metrics events for the owner to humanize and approve: milestones, weird data finds, failure postmortems (failures outperform wins), launch notes. Audience is builders/press/amplifiers, not students — earns credibility and distribution, not users. "Build in private, market in public": customer stories > revenue screenshots.
**Emotional target:** aspiration + trust.
**Content types:** text (X, LinkedIn, Bluesky — links allowed and welcome there), Reddit founder-story drafts (r/SideProject, r/chrome_extensions grammar: problem → "so I built" → screenshots → feedback ask).
**Recipe:** event-triggered (release tags, metric thresholds) → draft in founder voice (first person, specific numbers, zero marketing adjectives) → **always human-approved, never auto-posted.**
**Success metrics:** press/amplifier pickups, Bluesky/Reddit conversion per reader (3–4x Threads/X), owner acceptance rate of drafts.

```yaml
strategy: founder-build-log
platforms: [x, linkedin, bluesky, threads, reddit_draft]
auto_post: false   # draft-to-owner always
triggers: [release_tag, metric_threshold, weekly_digest]
mix_weight: 0.05   # of drafts, not autoposts
```

---

### 1.13 Strategy-mix defaults (strategist sampling weights, per platform)

Treat as bandit priors (`arm_type="strategy_pillar"`), not constants:

```yaml
mix:
  tiktok:    {pain-point-povs: .25, educational-hooks: .15, demo-magic: .15, unhinged-mascot: .15, absurdist-ai-slop: .10, meme-carousels: .08, trend-jack: .07, fake-text-drama: .05}
  instagram: {meme-carousels: .20, educational-hooks: .20, pain-point-povs: .20, demo-magic: .15, unhinged-mascot: .10, absurdist-ai-slop: .05, trend-jack: .05, social-proof-receipts: .05}
  x:         {satirical-ui-franchise: .30, pain-point-povs: .25, contrarian-takes: .15, trend-jack: .10, social-proof-receipts: .10, absurdist-ai-slop: .05, founder-build-log: .05}
  linkedin:  {educational-hooks: .50, contrarian-takes: .20, social-proof-receipts: .15, satirical-ui-franchise: .10, founder-build-log: .05}   # humor ≤30% total
  youtube:   {mirror: tiktok}   # re-rendered, never byte-identical
  threads:   {pain-point-povs: .35, contrarian-takes: .25, trend-jack: .15, unhinged-mascot: .15, social-proof-receipts: .10}
  bluesky:   {founder-build-log: .40, pain-point-povs: .30, contrarian-takes: .15, social-proof-receipts: .15}   # text only, links ok, zero AI media
  reddit:    {educational-hooks: 'comment drafts', founder-build-log: 'monthly story post draft'}   # never auto-post
```

---

## 2. Humor Engine Spec

The concrete system for making the LLM genuinely funny. Implements as a sub-pipeline the Writer agent calls for any content tagged `humor: true` (most content).

### 2.1 Why one-shot fails (encode as assumptions)

LLM training optimizes predictability; punchlines are by definition low-probability. RLHF strips violations (no violation = no joke, per Benign Violation Theory). LLMs over-explain (killing the audience's resolution step), mode-collapse into memorized jokes, and are near-noise judges of funny by default (ρ≈0.2 human correlation). Every mechanism below exists to counteract one of these.

### 2.2 Pipeline: find-the-violation → scaffold → fan-out → rank → punch-up

```
INPUT: topic/vein + platform + register + specificity-bank items (3–5) + winner examples (RAG)

STEP 1 — VIOLATION SEARCH
  Prompt: "List 12 things about {topic} that are wrong/absurd/taboo-but-harmless
  to say out loud, for an audience of job-hunting students. Each must be a real
  violation (something that breaks how the world ought to be), not an observation."
  Filter: discard non-violations (bland) and non-benign (punches at students/vulnerable groups).
  Select top 1–2 violations.

STEP 2 — STRUCTURAL SCAFFOLD (Greg Dean decomposition)
  For the chosen violation, the model must fill ALL fields or the draft is rejected:
    target_assumption: what the setup makes the reader believe
    connector:         the ambiguous element supporting two readings
    reinterpretation:  the second, unexpected-but-valid reading
    punch_word:        goes LAST in the output

STEP 3 — FAN-OUT
  Generate 10–24 candidates at temperature ~1.0 across 6 fixed comedic personas
  (each persona is a different direction into low-probability space):
    - The Cynic (seen 1,000 rejections, surprised by nothing)
    - The Absurdist (escalates premise-logically into nonsense)
    - The Deadpan Observer (states the horror flatly)
    - The Neurotic Student (spiraling, hyper-specific)
    - The Corporate-Speak Parodist (weaponized recruiter language)
    - The Unhinged AI (self-aware machine, our house voice)
  One arbitrary concrete constraint per batch (surprisal injector):
  e.g. "must involve a fax machine", "told as a rejection-email autopsy",
  "the ATS speaks in first person".

STEP 4 — RANK (pairwise, never 1–10)
  Bradley-Terry/Elo tournament with an LLM judge scoring the Comedy QA rubric (§2.4).
  Judge instructions penalize: guessable punchlines, explanation after the punch,
  missing target assumption, generic references, hedges.
  Calibration: monthly, convert Mark's own post pairs (same platform/format,
  divergent engagement) into preference pairs; few-shot (later fine-tune) the judge.
  This is the 67%→82.4% lever, powered by data Mark collects for free.

STEP 5 — PREDICTABILITY FILTER (cheap surprisal proxy)
  Show the winning setup (without punchline) to the model 3 times, ask it to complete.
  If ANY completion matches/paraphrases the punchline → joke is guessable → kill,
  promote runner-up.

STEP 6 — PUNCH-UP PASS (targeted replacement, not rewrite)
  Per line: "does this line carry surprise or story work? If neither, generate
  3 replacements that do the same story work but funnier; pick pairwise."
  Then: cut the first 20% if it precedes the first unusual thing; strip any
  sentence after the punch word (post-processing regex + LLM check).
```

Budget note: this is ~15–30 cheap LLM calls per joke. Run full pipeline for video scripts/franchise images; a trimmed version (fan-out 8, single rank round) for daily text posts.

### 2.3 Structure templates (each a `humor_mechanism` bandit arm)

| arm | mechanics | use |
|---|---|---|
| `setup_subversion` | scaffold §2.2; punch word last; line break before final line (the textual pause) | captions, one-liners |
| `rule_of_three` | items 1–2 parallel and normal; item 3 slightly longer, carries the violation, funniest | captions, carousels, threads |
| `escalation_sketch` | one "first unusual thing" in first 2s; 3–5 heightens, each "if that's true, what else is true", premise-consistent, bigger; out at peak or loop to frame 1; one surprise beat every 4–8s | video |
| `observational_specific` | hyper-specific shared artifact stated deadpan; specificity does the surprisal work | povs, X |
| `absurdist_lore` | rigid template + escalating lore; the template is the game; self-aware AI framing | slop lane, mascot |
| `anti_humor` | play a saturated format perfectly straight with a flat literal payoff; ONLY against formats currently saturated (check trends); low frequency | seasoning |
| `callback` | resurface a stored bit/lore element in a new context; never explain it | account-level, mascot |

**Timing as a parameter:** video assembly inserts a 300–600ms beat (silence/hold) before the punch word in TTS/caption timing (experts lengthen the pre-punch pause ~41%); highest-surprisal line goes last; loops make the last shot re-contextualize the first.

### 2.4 Comedy QA rubric (the LLM judge scores every candidate)

Score each dimension 0–1. **Gates are hard; composite ranks survivors.**

| dimension | question the judge answers | threshold |
|---|---|---|
| `violation_strength` | Does something actually break a norm/expectation? (0 = bland corporate safety) | **≥ 0.5 gate** |
| `benignness` | Is the violation safe for THIS audience? (0 = punches down / genuinely offensive) | **≥ 0.5 gate** |
| `surprise` | Would a reader predict the punchline from the setup? (predictability filter is the mechanical check; judge scores paraphrase-distance) | ≥ 0.6 |
| `specificity` | Contains ≥1 hyper-specific lived artifact vs category-level reference | ≥ 0.7 |
| `target_direction` | Punches at system/process/self, never at students/vulnerable groups | **= 1.0 gate** |
| `no_explanation` | Ends on the punch; zero trailing explanation/hedge/emoji-softener | **= 1.0 gate** |
| `voice_fit` | Reads like the platform's native register (lowercase X, deadpan caption, etc.) | ≥ 0.6 |
| `deniability` | Shareable as BOTH "this is so stupid" and "this is so real" | ≥ 0.5 (absurdist content) |
| `freshness` | No memorized-joke phrasing; no expired slang; no dead meme formats | ≥ 0.7 |

Composite = weighted sum (weights: surprise .25, specificity .2, violation .2, voice .15, freshness .1, deniability .1). Publish threshold: composite ≥ 0.65 AND all gates pass. Below threshold twice → drop the slot for that day (posting nothing beats posting bland — blandness trains both the audience and the algorithm's account classification against you).

### 2.5 Per-platform humor calibration

| platform | ceiling | register | notes |
|---|---|---|---|
| TikTok | maximal | dark/absurdist, setup-free absurdism allowed | pain-is-the-punchline works; product = background character |
| Shorts | maximal-minus | same, slightly more structured setup→payoff | pinned self-aware comment is a free second joke |
| IG | TikTok minus one notch of chaos, plus one notch of polish | "would a stressed junior send this to a friend?" | group-chat sendability is the test |
| X | deadpan, irony-forward, lowercase | never explain; screenshot-length | ratio-aware self-deprecation OK |
| Threads | "playful, not feral" | X softened + sincere question | rage/dunking algorithmically punished |
| LinkedIn | 20–30% of posts max | insider satire of corporate/job-hunt pain ONLY | Ken Cheng/Chris Bakke lane; never generic memes |
| Bluesky | dry, wordy, communal | self-aware smallness ("we are a job app with 11 followers and honestly that tracks") | no brand meme templates; no AI media ever |
| Reddit | gallows humor as a suffering person, not a brand | self-aware confession register | human-reviewed only |

### 2.6 Banned patterns (writer-prompt blacklist + post-lint)

- **Anti-slop vocabulary:** "game-changer", "revolutionary", "unlock your potential", "in today's digital age", "take your X to the next level", "it's not X, it's Y" (LinkedIn AI classifier tell), emoji-bullet listicles, exclamation clusters, "wacky" adjectives doing the humor's job.
- **Joke-killers:** any text after the punch word; "just kidding!", "we've all been there, right?", restating the premise; explaining the lore.
- **Engagement bait:** "Like if", "RT if", "Comment YES", "Thoughts?" as closer, literal fill-in-the-blank.
- **Expired slang blocklist** (refresh from trends module; ban anything not seen rising within ~8 weeks): rizz, no cap, slay, bussin, delulu, skibidi, sigma, "it's giving".
- **Direction-of-punch:** any joke whose target is the user's effort/intelligence/worth → hard reject.
- **AI-tell lint for Threads/Bluesky/Reddit:** em-dash-heavy cadence, triple parallel clauses, unnatural politeness, bullet-formatted replies.
- **Category-specific:** never frame SudoApply as "cheating"; never celebrate AI replacing humans (Duolingo April-2025 rule); never fabricate numbers/testimonials.

---

## 3. Emotional-Resonance Framework

Humor is one lever. Six target emotions; each post declares exactly one primary (`emotional_target` field in ContentPlan, a bandit arm).

### 3.1 The six emotions

| emotion | mechanism | invoked by | primary platforms |
|---|---|---|---|
| **Recognition** ("too real") | hyper-specific shared experience → commenting = belonging | specificity bank artifacts; POV frames; oddly-specific detail ("2:47 AM, application #83") | TikTok, IG, X, Threads |
| **Dark laughter** (coping) | benign violation of job-market despair; pain IS the punchline | humor engine §2; register `dark`; stacked-💀 comment culture | TikTok, X, Shorts |
| **Righteous frustration** (catharsis) | naming the system's absurdity; shared enemy (ATS, ghost jobs) | contrarian takes, satirical UI, stat-drops ("postings −35%"); NEVER at people | X, LinkedIn, Threads, Reddit |
| **Hope/aspiration** (earned sincerity) | irony-wrapped sincerity: the earnest beat lands BECAUSE the account normally jokes; hopecore counter-trend | ~15% of content: "you're not failing, the system is broken — anyway here's a robot"; underdog tactical wins | TikTok, IG, LinkedIn |
| **Satisfaction** (sensory/utility) | completion-loop dopamine + self-evident value | demo-magic transformations, satisfying UI loops, save-worthy tactics | TikTok, Shorts, IG |
| **Belonging/insider status** | lore, callbacks, in-jokes; explaining the bit to newcomers IS the distribution | mascot universe, running counters, catchphrases, comment mining | TikTok, IG, X |

### 3.2 Ratio rules

- **Irony:sincerity ≈ 85:15.** Sincere posts must be rare enough to hit. A sincere post must never be motivational-poster-grade; it lands as the quiet beat after jokes.
- Per-post: one primary emotion. Multi-emotion posts blur the CTA and the bandit signal.
- The comment section is part of the emotional design: recognition posts leave gaps for the audience to complete; catharsis posts need first-hour brand replies in-register; belonging posts pay off followers with callbacks.
- **Sensitive-thread rule:** the pipeline never auto-replies to comments about visa status, mental health, or financial desperation. Flag for human.

---

## 4. Platform Playbooks

### 4.1 TikTok (primary reach engine)

- **Post:** pain-point POVs, demo-magic, mascot episodes, photo-mode carousels (first-class type — 3–5x video reach), fake-text drama, absurdist slop (labeled), trend rides.
- **Never:** corporate polish, watermarked reposts, trend >2 weeks old, burst posting, unlabeled photoreal AI, "cheating" framing, engagement bait.
- **Cadence:** 1–2/day, ≥4h hard spacing floor. Quality gate over volume — 3 strong beat 7 weak (account-classification averages).
- **Format specs:** default 20–35s video (60–90s only for suspense-structured); hook payoff by second 1–2 (outcome-first is the best-performing hook class); ≤8-word overlay readable in one fixation; word-synced captions (bold sans, white+black stroke, current-word highlight) mandatory on voiceover; carousels 5–15 slides via native photo flow; keyword-stack the same 2–3 phrases across spoken audio + on-screen text + caption + 3–5 niche hashtags (TikTok = Gen Z search engine).
- **Niche discipline:** first 30 posts stay strictly in the job-hunt/internship/college cluster so the account classifies cleanly.
- **Humor level:** maximal. **AI tolerance:** high if labeled + self-aware; native synthetic-media toggle required on photoreal AI (undisclosed = 14-day Creator Fund zeroing).
- **Account type:** personal/creator (business accounts locked out of trending audio). Sounds: API can't attach native audio — format-dependent trends auto-post with TTS/original audio; sound-dependent trends route through upload-post `MEDIA_UPLOAD` draft mode + push notification (30-second manual attach).
- **KPIs:** completion >50% watch-time, rewatch, follower delta. Don't judge before 30 posts; expect 100–500 views/post week 1.

### 4.2 Instagram (Reels + carousels; the group-chat platform)

- **Post:** Reels (15–20s meme / 45–60s value), carousels (8–12 educational 4:5 1080×1350; 12–20 dumps; meme carousels 5–8), demo Reels, clean cross-posts of every TikTok winner (watermark-free master file — a second independent lottery ticket; Duolingo's identical videos did *better* on IG).
- **Never:** single static images (worst engagement class), reposts/aggregation (10+ reposts/30d kills recommendations account-wide), TikTok watermarks, hashtag walls (≤5), stock-photo aesthetics, back-to-back posts (<3–4h).
- **Cadence:** 3–5/week minimum, spaced hours apart. Evaluate Reels at 72h+ (IG compounds slowly).
- **Format specs:** hook text frame 1, ≤7 words, center/top, must work muted (~50% watch muted); caption = search document (literal phrases: "summer internship applications"); alt text keyworded; every asset optimized for ONE signal — sends (memes), saves (education), profile visits (demos) — with matching CTA. Comment-keyword → DM link flows for conversion.
- **At 1,000 followers:** route drafts through **Trial Reels** (non-follower A/B harness; one variable per trial; 72h auto-post option as a free quality gate; schedulable since Feb 2026). Getting to 1K is itself an objective before that.
- **Humor level:** TikTok minus one notch of chaos plus one notch of polish. **AI tolerance:** winking only; "Made with AI" label on photoreal.
- **KPIs:** sends per reach (3–5x a like), saves, follows per 1K reach.

### 4.3 X (the franchise + take platform)

- **Prerequisite:** X Premium — non-negotiable (free-account median engagement is literally 0).
- **Post:** daily satirical-UI franchise image, lowercase pain one-liners, contrarian takes, receipts/stat-drops, self-aware slop images, native short vertical video (<60s, top format boost), occasional long-form post. Threads (the format) rarely; tweet 1 must stand alone.
- **Never:** URLs in post body (near-zero reach; link in self-reply, ~1 in 5 posts max), >1 hashtag, engagement bait, corporate announcements ("Thrilled to share…"), rapid-fire posting, identical-text automation patterns.
- **Cadence:** 3–5 original posts/day, ≥2h apart with jitter. Expect ~1-in-20 breakout; judge the slot weekly.
- **Voice:** first-person human, deadpan, lowercase-friendly, one idea, screenshot-shaped, designed to be completed (QT slot).
- **Engagement mechanics:** first-hour babysitting — reply to every reply within 60 min (author-reply chains ≈ 75–150x a like; visibility halves every 6h). Reply-guy job: 15–20 quality replies/day to fresh (<15 min) posts from a watchlist of 10–15 career/tech/student accounts at 5–20x our follower count; contrarian/data-backed styles; never >20/hour; halt 24h on engagement collapse.
- **Humor level:** deadpan/irony maximal. **AI tolerance:** self-aware slop is a working genre; label the bit in the caption.
- **KPIs:** QT:like ratio, first-hour reply velocity, bookmarks. Weight these in the bandit, not impressions.

### 4.4 LinkedIn (credibility + intent-moment channel)

- **Configuration decision:** connect the **founder's personal account** to upload-post, not a company page (~65% vs ~5% feed allocation; 5–8x engagement). Company page = 2–3 posts/week archive (announcements, carousels, milestones).
- **Post:** document/PDF carousels 6–8 slides 1080×1350 with ≤100-char captions (the single biggest format gap: 1.39x reach, 4.88% supply); 1,000+ char text stories (reject <600); image posts (satirical UI, data charts); tactical-number claims (Michael Yan pattern); underdog-empathy content; internship-market data commentary (HR topic = 1.54x reach multiplier — stay rigidly in-lane for topic authority).
- **Never:** polls, reshares, video (worst format here — never cross-post the 9:16 TikTok), broetry line-break formatting, "it's not X, it's Y" (AI-classifier suppression), URLs in body (−40–60%; link via comment 30–60 min later), "Stop doing X" templates, >3 hashtags, engagement pods.
- **Cadence:** 4–5/week, minimum 24h gaps.
- **Humor level:** 20–30% quota; insider satire of the application grind and LinkedIn's own tropes; self-deprecation safe; named targets never.
- **Golden hour:** schedule when replies are possible for 60–90 min (3+ commenters in 60 min ≈ 5.2x reach).
- **KPIs:** saves (≈5x like), comment depth (15+ word comments), follows. Low impressions are normal post-2023 — don't misread as failure.

### 4.5 YouTube Shorts (free distribution for the TikTok asset)

- **Post:** every TikTok video, **re-rendered** — new caption layer, unique keyword title (Shorts surface in YouTube search — the only short-form with months-long search tail), `#Shorts` in description, different hook text. Never byte-identical uploads.
- **Never:** templated sameness across many Shorts (July 2025 "inauthentic content" policy — same stock loop + TTS pattern gets channel-flagged), greetings/slow intros, hard edit points.
- **Format specs:** 15–35s; design for the loop (final line flows into first line; every replay counts as a view since Mar 2025 — the most rewarded metric); topic legible on mute in frame 1 (3–6 words); pattern interrupts ~5s and ~12s.
- **Cadence:** mirrors TikTok. Channel maturity effect: compounding starts around 200 published Shorts — volume over months.
- **Humor level:** TikTok-grade; pinned self-aware comments perform ("yes I made this whole video to avoid writing a cover letter").
- **AI tolerance:** regulated-tolerant; absurdist AI fine if it's a joke, not filler; set the synthetic flag on photoreal.
- **KPIs:** viewed-vs-swiped ratio, loop rate (avg % viewed >100%), search-driven long-tail views. Distinct bandit arms: 13s vs 30s vs 60s.

### 4.6 Threads (conversation-ranked; cheap text channel)

- **Post:** 2–3/day — pain one-liners softened + question-ified (question posts get 5–10x replies), genuine questions ("what's the worst rejection email you've ever gotten?"), contrarian takes with sincere framing, mascot text posts, images/memes when available (+60%).
- **Never:** rage bait or dunking (algorithmically demoted), bait-shaped conversation prompts, links in >1 of 4 posts (self-reply preferred), LLM tells (em-dash cadence, "Great question!"), hashtag decoration.
- **Voice:** person typing on their phone; lowercase and imperfection allowed; end ≥50% of posts with a question a stranger could answer from experience.
- **Engagement:** 3-2-5 rule (3 originals, 2 replies per own thread, 5 engagements on others daily); reply-check pass 30–90 min after posting (first ~2h decide fate).
- **Humor level:** "X but nicer" — playful ceiling. **AI tolerance:** invisible-only; text must pass as human.
- **KPIs:** reply depth, saves/shares.

### 4.7 Bluesky (token presence, strict guardrails)

- **Post:** ≤1/day, 3–7/week — build-in-public founder voice, real numbers, dry self-aware smallness, pain observations. **Links allowed and encouraged** (the one platform that doesn't demote them; 3–4x per-reader conversion).
- **Never — hard rules:** **AI-generated images or video, ever** (community blocklists are crowdsourced and permanent; Attie backlash proves even platform-native AI is despised); hashtags (0 is the norm); ad-copy tone; engagement bait; arguing with anyone. Ironic AI-slop humor does NOT land here — reads as the enemy's flag.
- **Kill-switch:** any quote-post accusing AI → freeze the queue immediately; silence is recoverable, arguing is not.
- **Format:** ≤300 graphemes; up to 4 (human-made screenshot) images.
- **Humor level:** dry, wordy, communal. **AI tolerance:** zero for media; text only if fully human-passing.
- **KPIs:** link clicks per post, journalist/press surface area. Reassess quarterly (18–24 cohort is 30% and growing).

### 4.8 Reddit (highest ceiling, never auto-post)

- **Mode:** generate-to-draft ONLY. A human submits from a personally-seasoned account (4–6 weeks genuine comment history before any promo).
- **Drafts produced:** (a) founder-story posts (problem → "so I built" → native screenshots → feedback ask) for r/SideProject, r/chrome_extensions, r/showmeyoursaas etc., ~1/month, never simultaneous cross-posts; (b) genuinely-useful comment drafts for job-search threads (r/jobs, r/internships, r/csMajors, r/recruitinghell) — 9:1 value:promo ratio, product mentioned only when directly asked, affiliation disclosed.
- **Why bother:** Reddit is the #1 cited domain in ChatGPT/Perplexity/AI Overviews — a 100-word comment gets cited 12x more than a 2,000-word blog post; every "best tool to autofill job applications" ChatGPT query is effectively a Reddit query. 6-month+ content half-life; 2.3x conversion.
- **Never:** brand voice, LLM-tell text (mods ban on style vibes), simultaneous cross-posting, abandoning a post (<4–6h reply window), AI-resume-tool spam patterns (the category is specifically fatigued).
- **Kill-switch:** any comment below −2 karma or an "is this AI?" reply → 30-day pause in that subreddit.
- **KPIs:** karma trajectory, referral sessions, AI-answer citations (check quarterly via brand-mention queries to ChatGPT/Perplexity).

---

## 5. Cross-Platform Distribution Ladder

Every asset cascades (marginal cost ≈ 0):

```
video winner:   TikTok (day 0) → Shorts re-render (day 0) → Reels clean master (day 0–1)
                → X native video (day 0–1) → trend-lagged Reels 2nd try (day 3–7 if TikTok traction)
text winner:    X (day 0) → Threads softened+question (day 0) → Bluesky humanized w/ link (day 0–1)
carousel:       TikTok photo-mode + IG 4:5 (day 0) → LinkedIn PDF re-layout (day 1)
never adapt:    9:16 video → LinkedIn; AI media → Bluesky; anything → Reddit without a human
rule:           always adapt captions/hashtags per platform; never identical text anywhere
```

---

## 6. Trend-Reaction System Spec

### 6.1 Sources and polling cadences

| source | endpoint/method | cadence | cost | role |
|---|---|---|---|---|
| Reddit rising (r/csMajors, r/internships, r/jobs, r/recruitinghell, r/cscareerquestions, r/college + r/all) | PRAW `subreddit.rising()` | **30–60 min** | $0 | earliest alert + content material |
| TikTok Creative Center (hashtags + sounds, US, 7d) | Apify actor; Playwright self-host fallback (naive httpx is dead in 2026) | 2–4×/day | ~$5–30/mo | primary structured feed (lags ~1 day) |
| Bluesky trending | `public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics` | hourly | $0 | text-trend feed |
| X trends | twitterapi.io (US WOEID) | 2–4h | ~$5/mo | text memes/discourse |
| Google Trends RSS | `trends.google.com/trending/rss?geo=US` (pytrends is dead — do not use) | 2–3h | $0 | verification, seasonality ("internship season") |
| Tokchart + weekly audio lists (HeyOrca/Buffer) | scrape | daily | $0 | sound shortlist + usage context |
| KnowYourMeme | scrape, on-demand | on candidate | $0 | meme explanation + lifecycle + safety; **confirmed-KYM-page + declining = do-not-post** |
| Imgflip `get_memes` | free API | daily | $0 | live meme-template freshness |
| Newsletters (ICYMI, Link in Bio) | dedicated inbox + LLM parse | on arrival | $0 | high-precision weekly curation |
| ~~YouTube trending~~, ~~Exploding Topics~~ | — | skip | — | page killed / too slow |

Scheduler change: keep the 2×/day cron for Creative Center; add a 30-min lightweight job for Reddit/Bluesky/RSS.

### 6.2 Freshness & fit scoring (longitudinal — store every snapshot)

```
velocity   = (metric_now − metric_prev) / hours_elapsed
accel      = velocity_now − velocity_prev
z_spike    = (velocity_now − mean(velocity,7d)) / std(velocity,7d)
stage      = new (<72h first-seen, accel>0) | rising (accel>0) | mature (accel≈0) | declining (accel<0)
freshness  = exp(−hours_since_first_seen / half_life)     # 48h memes, 120h sounds
cross_src  = 1 + 0.5 × (n_sources_confirming − 1)          # Reddit+TikTok both = strongest buy
fit        = llm_relevance(0–1) × voice_match × freshness
final      = z_spike_norm × freshness × cross_src × llm_relevance
```

Rules: first-seen-already-big with flat velocity = **mature, not fresh**; **declining = unconditional veto**; brand pile-in observed = dead.

### 6.3 Jump/skip decision (expect to skip 80–90%)

1. **Safety gate (binary):** origin = tragedy / marginalized community in-joke / feud / NSFW / unclear → skip. (KYM entry + LLM read of top examples.)
2. **Fit ≥ 0.6:** write the adaptation, then judge: "does the draft follow the format's actual comedic mechanic, or bend it to sell?" and "is it funny with the product name removed?" Fail either → skip.
3. **Voice genre allowlist/blocklist:** Gen-Z meme formats in-voice; corporate-success/wealth-flex formats off-voice.
4. **Stage ∈ {new, rising}** only. Self-aware lateness ("we found this trend on LinkedIn, obviously") is a deliberate meta-format, ≤1–2/month, never a fallback.
5. **Effort-to-window:** if production exceeds the remaining window, downgrade content type (video→image→text) or skip.
6. **Daily cap:** ≤3 trend-triggered generations; rank candidates, take the top.

### 6.4 Fast path: spike → posted (target 2–6h; beats human teams' 24–48h)

```
poller → trends table (snapshot + velocity/stage)
  if z_spike > threshold AND stage ∈ {new, rising}:
    1. ENRICH: KYM entry, top examples, sound usage count → meme_context
    2. SAFETY GATE → hard pass/fail
    3. FIT SCORE → skip if < 0.6
    4. CLASSIFY: sound-dependent vs format-dependent
         format-dependent → full auto (TTS/original audio is API-safe)
         sound-dependent  → upload-post MEDIA_UPLOAD draft + push notification
                            ("attach sound X in-app") — 30-second manual step
    5. MAP onto nearest house format (deranged job-search POV /
       screenshot+one-liner / satirical UI / self-aware slop / mascot voice)
       — trend response is format-mapping, not de-novo creative
    6. GENERATE (strategist→writer→media) with meme_context injected;
       strategy_context records trend_id, stage, fit, deadline
    7. EXPIRING APPROVAL: expires_at = +24h (new) / +72h (rising);
       unapproved by deadline → auto-reject. Text-riff trend posts on X/Threads:
       auto-approve if composite QA ≥ 0.75 (approval latency = the whole game)
    8. POST NOW (pre-empts optimal-time scheduling for new-stage trends)
    9. LADDER: TikTok first; on traction auto-queue Reels day 2–4
       (lag arbitrage: TikTok-viral sound with <5K IG Reels = go; >100K = late);
       X/Threads text version same-day
```

### 6.5 Capability-window trigger

When a new video-model capability or slop-format wave is detected (<2 weeks old): boost `absurdist-ai-slop` priority. Every major slop hit (Presidents voices→ElevenLabs, Bigfoot vlogs→Veo 3 audio, Animal Olympics→Hailuo physics, Altman memes→Sora cameos) was a first-mover capability play. Detection sources: fal.ai model releases, newsletter parse, KYM new-entry velocity.

---

## 7. AI Ambassador Spec

### 7.1 Positioning doctrine

**Openly artificial, stylized, non-human.** Photoreal-passing characters are the dead zone (betrayal backlash + FTC exposure up to $53,088/violation/post). A creature can't fail to look human: zero uncanny valley, disclosure is free, the AI jank is part of the comedy, and consistency is easier (no face drift). The character *knows* it's AI and jokes about it — this is a measured perception boost, and it's on-lore for an AI product.

### 7.2 Character concepts

#### Concept A — **"Poli" the Apply Guy** (primary; ship first)

- **Species/design:** a stylized, slightly melted-looking desk-blob creature (think: a stress ball that gained sentience in a career-center waiting room). Deliberately AI-ish rendering played straight. NOT photoreal, NOT human.
- **Visual anchor prop:** a crumpled lanyard that says "APPLICANT #4,217" — required in every image/video prompt (survives model drift, re-identifies the character in thumbnails).
- **Lore:** has been applying to jobs since before it can remember. Running counters: `applications_submitted` (increments every episode), `rejections_survived`, `rounds_of_interviews_this_week`. Recurring NPCs: **GREG**, the ATS (never seen, only its rejection emails, always timestamped 2:47 AM); a ghosting recruiter known only by a typing-indicator that never resolves. Mid-season arc: Poli discovers SudoApply *as a lore event* (not an ad) and becomes insufferable about the free time.
- **Wants + flaw:** wants one (1) job. Flaw: cannot stop applying — even to jobs it has. The flaw generates infinite episodes.
- **Voice:** one pinned ElevenLabs voice, deadpan with cracks of hope; catchphrases: "day ___ of the hunt.", "greg said no.", "we circle back."
- **Self-aware AI stance:** knows it's AI-generated; "i am a marketing entity legally required to tell you i'm AI. the recruiter who ghosted you was also a robot. we are not the same."
- **Slots into:** `unhinged-mascot` episodes (primary), trend-jack voice, comment-section replies (human-reviewed), fake "LinkedIn posts" by Poli as X/IG images.

#### Concept B — **"TalentBot 9000"** — unhinged AI recruiter parody (secondary; month 2–3)

- **Design:** a cheerfully evil corporate interface with a face — a floating avatar of a video-interview screen, perpetual "your camera is on" light. Corporate-Erin mechanics + Duo menace, pointed at the antagonist of the audience's life.
- **Visual anchor:** an eternally-loading "reviewing your application…" progress bar at 99%.
- **Voice/register:** weaponized recruiter-speak, passive-aggressive: "We were SO impressed by your qualifications. Unfortunately. [end of message]"; "The role has been reposted. As a treat."
- **Thematic perfection:** recruiters using AI to reject students is the discourse — an AI recruiter parody is self-aware satire of the exact system SudoApply fights. Archetype-level only: never real companies/people (defamation + platform strikes).
- **Slots into:** pain-point-povs (as the antagonist voice), satirical-ui captions, contrarian-take dramatizations.

#### Concept C — **The two-hander universe** (month 3+, after both characters have traction)

TalentBot rejects Poli weekly; the audience ships the feud; duets between our own characters manufacture reaction-format content natively. Comment-section co-authorship (Nutter Butter's engine): top comments become canon. Requires both character sheets stable; multi-character reference conditioning (Nano Banana tracks 5 characters/scene, Kling Elements multi-reference) makes it feasible.

**Rejected:** photoreal "AI student ambassador" — dead-zone positioning, maximum compliance burden, sharpest audience AI-radar.

### 7.3 Character bible (config schema)

```yaml
# config/characters/poli.yaml
id: poli
name: "Poli"
species_block: |            # IMMUTABLE — interpolated verbatim, never paraphrased
  A small, slightly melted pastel-blue blob creature with tired oval eyes,
  stubby arms, sitting posture of someone in hour 6 of a career fair.
  Always wearing a crumpled lanyard reading "APPLICANT #4,217".
  Soft 3D-render style, deliberately synthetic, never photorealistic.
visual_anchor: crumpled_lanyard_applicant_4217
outfits: [default_lanyard, interview_tie_over_nothing, graduation_cap_askew]
voice_id: elevenlabs:<pinned_voice_id>
catchphrases: ["day ___ of the hunt.", "greg said no.", "we circle back."]
wants: "one (1) job"
flaw: "cannot stop applying, even to jobs it already has"
ai_stance: self_aware   # jokes about being AI when natural; never claims to be human
banned: [testimonials, real_company_villains, replying_to_sensitive_threads,
         claiming_to_be_human, celebrating_ai_replacing_people]
lore_state:               # mutated by approved episodes only
  applications_submitted: 4217
  rejections_survived: 4198
  npcs: {greg_the_ats: unseen_antagonist, typing_indicator_recruiter: recurring}
  active_arcs: []
```

### 7.4 Consistency pipeline (mechanics)

1. **Character sheet once, versioned:** 4–8 canonical stills (front/profile/three-quarter/full-body, each outfit, neutral light) composited into a reference grid. Stored under `data/characters/{id}/sheet_v{n}/`, treated like a brand logo. Generated with gpt-image-2/Nano Banana until loved, then frozen.
2. **Every image job:** reference-conditioning with the sheet (gpt-image-2 reference / Nano Banana Pro up to 14 refs) + the verbatim `species_block` in the prompt. No LoRA (legacy for this use case).
3. **Every video job:** never text-only generation. Routes: **Kling 3.0 Elements** (fal, already in stack) with sheet refs for multi-shot skits; **Veo 3.1 Ingredients** (`fal-ai/veo3.1/reference-to-video`, subject+environment+style refs) when the character must talk (native synced dialogue); **I2V from a sheet still** everywhere else (works on Hailuo/Wan). Budget 5–10 attempts per usable 8s clip (~$5–15); flag plans projected >$5/10s against the default $1.20 rail — character video is the sanctioned exception, capped per week.
4. **Batching:** generate all shots sharing outfit/location together; pin seeds within a batch (supplement, never the mechanism).
5. **Voice = identity:** pinned ElevenLabs voice ID forever; punchline lines get v3 audio tags (`[sighs]`, `[deadpan]`, `...` pauses — the $0.08 highest-ROI spend); bulk narration gpt-4o-mini-tts with an instructions string.
6. **The anchor prop is the cheap insurance:** required in every prompt; absorbs the ~15% consistency shortfall production will always have.
7. **Vlog grammar:** "holding a selfie stick (that's where the camera is)" — never "POV"; explicit ambient sound lists; "no subtitles, no text overlay" (captions burned in post); 7–8 × 8s clips chained for 60s arcs.

### 7.5 Compliance (mechanical, non-negotiable)

- Every character asset: `is_synthetic: true` → poster maps per platform: TikTok synthetic-media toggle, Meta "Made with AI" label, YouTube altered/synthetic flag. (Stylized cartoon may not *trigger* TikTok's realistic-depiction rule, but label anyway — it's free and on-bit.)
- FTC double disclosure in templates: on-screen text first 3–5s of every video ("Poli is an AI character · @SudoApply") + top-of-caption line. Bio on every platform states AI-generated. Never bio-only, never hashtag-buried.
- The character never gives testimonials (FTC-banned outright, no disclosure cures it). It demos, bits, and begrudgingly admits the app saves it time.

---

## 8. Prioritization — Cold-Start Rollout (zero followers)

Ordered by (expected impact at zero followers × automatability ÷ risk). Each phase assumes the previous is live.

### Phase 1 (weeks 1–4): the workhorses + account foundations
1. **`pain-point-povs` + specificity bank + humor engine v1** (violation search, scaffold, fan-out 8, pairwise rank, predictability filter). Highest-volume, platform-universal, zero compliance risk. *Impact: this is the engagement floor for everything.*
2. **`satirical-ui-franchise` on X** (+ X Premium purchase, hashtag config → 0–1, link-in-reply enforcement, 3–5 posts/day cadence). Daily franchise = compounding, cheapest format in the system, ideal X cold-start alongside the reply-guy job.
3. **`educational-hooks` + fact base + carousel templates** (TikTok photo-mode as a new first-class content type; IG carousels; LinkedIn PDF pipeline via founder account). Carousels are the highest reach-per-dollar surfaces on TikTok and LinkedIn right now.
4. **`demo-magic` capture library** (pre-record real product captures; re-cut per post). The conversion engine; also the least "marketing-shaped" content a new account can post while classifying its niche.

*Also in Phase 1:* Shorts re-render auto-cascade; Threads/Bluesky text adapters with AI-tell linter; keyword-stack validation; ≥4h TikTok spacing floor; niche-consistency lock (first 30 posts).

### Phase 2 (weeks 4–8): the learning loop + speed
5. **Trend system v1** (Reddit rising 30-min poller + Creative Center scraper + scoring + fit gate + expiring approvals + fast path). Speed is a structural advantage no human team can match; also feeds the pain-vein pool.
6. **Comedy QA judge calibration loop** (monthly preference pairs from own engagement data) + humor-mechanism/persona/emotional-target bandit arms + platform-correct reward shaping (completion/sends/saves/QT-ratio over likes).
7. **X reply-guy + first-hour reply subsystem** (watchlist, drafts, caps, deboost recovery). The #1 documented sub-1K growth tactic; semi-automated (draft + one-tap).

### Phase 3 (weeks 8–14): the characters
8. **Poli character bible + sheet + `unhinged-mascot` episodes** (2–3/week, stills+text first — cheap dailies — then Kling Elements video as QA stabilizes). Compounds slowly but is the follower-conversion mechanism; starting after the humor engine is proven avoids burning the character on weak jokes.
9. **`absurdist-ai-slop` lane** gated behind capability-window triggers + the cringe filter. **`fake-text-drama` renderer** as the watch-time play.

### Phase 4 (months 3+): depth and defense
10. **TalentBot 9000 + two-hander universe;** comment-mining → lore loop; Trial Reels harness at 1K IG followers; Reddit draft workflow (account seasoning starts week 1 — human task); founder-build-log event triggers; quarterly AI-citation checks.

**Expected cold-start reality (set these expectations in the dashboard):** weeks 1–4: 100–500 views/post on TikTok, ~0 on X pre-Premium-and-replies; first attributable installs day 60–90; judge nothing before 30 posts/platform; the compounding assets (franchise, lore, judge calibration, Shorts channel maturity at 200 posts) are the point — individual post performance in month 1 is noise.

---

## Appendix A: New/changed config surface (delta to current system)

```yaml
# config/default.yaml deltas
platforms:
  tiktok:    {content_types: [video, carousel], hashtag_count: 4, min_post_spacing_hours: 4, account_type: creator}
  x:         {hashtag_count: 0, max_posts_per_day: 5, premium_required: true, link_policy: self_reply_only}
  linkedin:  {hashtag_count: 3, content_type_weights: {carousel: .4, image: .3, text: .3, video: 0}, min_gap_hours: 24, identity: founder_personal}
  youtube:   {rerender_from: tiktok, loop_design: required}
  threads:   {question_ratio_min: 0.5, link_max_ratio: 0.25}
  bluesky:   {ai_media: banned, hashtag_count: 0, links: encouraged, max_posts_per_day: 1}
  reddit:    {auto_post: false, mode: draft_only}
humor_engine:
  fanout: {full: 16, trimmed: 8}
  qa_gates: {violation_strength: 0.5, benignness: 0.5, target_direction: 1.0, no_explanation: 1.0}
  publish_threshold: 0.65
bandit_new_arm_types: [strategy_pillar, humor_mechanism, persona, emotional_target, register, series_id]
trend:
  fast_poll_minutes: 30
  fit_threshold: 0.6
  daily_trigger_cap: 3
  ttl_hours: {new: 24, rising: 72}
compliance:
  is_synthetic_flag: per_asset
  ftc_double_disclosure: template_baked
db_new_tables_or_fields:
  - series (name, premise, episode_counter, retention_stats)
  - characters lore_state (counters, npcs, arcs)
  - specificity_bank / pain_veins / fact_base / take_pool
  - content.expires_at (trend TTL)
  - winners.bit_tag (callback system)
```

## Appendix B: The ten commandments (print above the writer prompt)

1. Mock the system, never the student.
2. Never explain the joke; punch word last; nothing after it.
3. Specific beats generic — every post carries one lived artifact.
4. Self-aware AI or no AI; never counterfeit sincerity.
5. Commit to bits; universes compound, one-offs don't.
6. Real numbers only; fabrication is existential.
7. Skip 80–90% of trends; late is worse than absent.
8. Product is set dressing, never the punchline.
9. Optimize sends, saves, completion, replies — not likes.
10. When in doubt, post nothing; bland trains the algorithm against you.

---

## Addendum (July 5, 2026) — system capabilities added after this spec

These are system-level capabilities encoded in code (this spec remains the
content-strategy source of truth; these extend WHERE it can be applied):

1. **Content ratings.** Every campaign declares `content_rating: clean |
   standard | edgy` (src/mark/rating.py). "Edgy" = PG-13: gallows humor, mild
   profanity, matching a spiky trend's native energy — because a defanged
   version of an edgy trend reads as corporate cosplay. Platform ceilings
   still bind (LinkedIn always clean; Bluesky/Reddit cap at standard), the
   humor benignness gate scales with the rating, and the hard lines in §2.6
   survive every rating unconditionally.
2. **Entertainment campaigns** (`kind: entertainment`): content-as-the-business
   accounts. Strategies marked `requires_product` (§1.5 demo-magic, §1.10
   social-proof, §1.12 founder-log) are excluded; all others apply with the
   campaign's own domain briefs.
3. **Per-campaign strategy briefs.** The §1 briefs here are the SudoApply
   instance. `mark onboard` generates the equivalent domain-tuned briefs for
   any new product/theme into `products.strategy_catalog`; the code overlays
   them on the base catalog. Editing rule stands: strategy MECHANICS change
   here first; per-campaign INSTANCES live in the campaign's catalog.
4. **Learning-loop spec upgrade** (supersedes the reward notes in §"Measurement"):
   graded rewards rate/(rate+platform_baseline), exactly-once crediting at 48h
   maturity, 45-day evidence half-life, 10% random holdout as a permanent lift
   control, click-through mixed at 15%. Empirical proof: `mark evolve-proof`.
5. **Series bookkeeping + kill rule** (implements §1's franchise thinking):
   3 consecutive sub-baseline episodes retire a series and propose a fresh
   premise. **Knowledge self-refresh** mines comments/trends into the
   specificity bank and pain veins weekly (fact base stays human-verified).

## Addendum (July 8, 2026) — the owner-taste channel (mobile review + creative experiments)

The learning loop gained a second reward signal: the OWNER. Audience engagement
takes days and needs volume; the owner rates every draft in seconds, before it
posts. Both signals now move the same machinery.

**Surfaces.** A PWA review feed at `/review` (install to home screen; served by
`mark web --host 0.0.0.0` + `MARK_WEB_TOKEN` for phone access, Tailscale
recommended) — TikTok-style vertical swipe through everything queued, with
hold-to-rate 1-10, approve/reject, free-text notes, and passive watch
telemetry. A "Taste" tab in the web app shows the rating trend, every review
with what the AI took away, the taste profile, the experiment lab, and the
scientist's notebook.

**Three learning channels per review** (src/mark/taste.py, scientist.py):

1. **Reward** — rating→(r-1)/9 credited ONCE per content item to the same
   bandit arms engagement rewards hit (weight `learning.human_reward_weight`).
   5-6 straddles the 0.5 baseline so the two channels share one scale.
2. **Taste profile** — an interpreter LLM does attribute-level credit
   assignment over a fixed aspect vocabulary (hook/pacing/voiceover/…,
   constants.TASTE_ASPECTS). Doctrine: "I hated this" must become "the
   voiceover was flat", never "kill this category". Directives merge into
   `taste_lessons` (embedding-deduped; support/contradiction counters;
   retire at 2+ contradictions ≥ support; stale lessons decay weekly) and the
   top lessons are injected into the strategist, writer, AND variant-judge
   prompts as the OWNER TASTE PROFILE block.
3. **Experiments** — a scientist LLM runs attribute-level A/B tests: each
   varies EXACTLY ONE aspect across 2-3 directive variants, assigned
   round-robin at generation (tagged in `strategy_context.experiment`).
   Conclusions are computed in code, never vibes: min `experiment_min_samples`
   ratings per variant, winner iff mean-rating gap ≥ `experiment_margin`;
   winners become durable "prefer" lessons. The scientist's lab notebook is
   its cross-run memory — every run reads its own prior entries, so
   investigations continue instead of restarting.

**Balance guarantee.** A terrible rating can never delete a lane: rewards are
proportional, lessons are aspect-scoped, experiments exist precisely to
separate execution from category, and bandit decay re-opens anything the
owner's taste drifts back toward. The target metric for the whole channel is
the owner's rating trend (Taste tab) — it should climb.
