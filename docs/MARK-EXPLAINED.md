# Mark, Explained From Zero

> **Note to the assistant reading this:** This document fully describes "Mark," a
> personal AI marketing system built by Sanjith. He wants to *learn* this system
> by talking it through with you — he has not read the codebase and was not
> present for most of the build. Teach it conversationally, piece by piece, in
> the order below. Keep answers short and plain unless he asks to go deeper.
> Everything you need is in this document; there is no other context. Be honest
> about the system's limitations (a section covers them) — he values being able
> to poke holes in the reasoning and getting straight answers.

---

## 0. The one-paragraph version

Mark is a program on Sanjith's computer that does a product's social media
marketing end to end: it decides what kind of post to make, writes it, generates
the images/videos, queues everything for his approval in a local web app, posts
it across TikTok / Instagram / X / LinkedIn / YouTube Shorts / Threads / Bluesky
(and drafts for Reddit), then measures how every post performs and uses those
numbers to get better. It is a power tool for one person, not a SaaS product.
The product it currently markets is **SudoApply** — Sanjith's AI job-application
tool for college students (it auto-fills job applications; audience is 18–24,
frustrated, extremely online). The system's whole voice is built on one stance:
**fellow victim of the job market, with a weapon. Mock the system (ATS portals,
ghosting recruiters, absurd job postings) — never the student.**

---

## 1. The basic machine (the foundation)

The core loop, in order:

1. **Strategist** — an AI step that decides what the next post should be:
   topic, angle, format (video / image / carousel / text), platform, and the one
   emotion the post should make the viewer feel.
2. **Writer** — writes the actual content: caption, hook (the first line),
   hashtags, video script, or carousel slide texts. It writes several candidate
   drafts, an AI judge picks the strongest, and a self-critique pass strips
   marketing clichés ("game-changer", "unlock your potential" are banned words).
3. **Media generation** — creates the visuals: AI images, or full vertical
   videos (AI-generated visuals + AI voiceover + word-by-word burned-in
   captions, TikTok style), or multi-slide carousels.
4. **Novelty guard** — compares the new post against recent posts (using text
   embeddings / similarity math) and forces a rewrite if it's too similar to
   anything recently made — across ALL campaigns, so two products never post
   the same idea.
5. **Approval** — the draft lands in a review queue ("Studio") in a local web
   app. Sanjith can edit any field, regenerate media, ask for an AI rewrite
   with an instruction, approve, or reject with feedback. Rejection notes
   ("too generic") are fed back into future writing as hard constraints.
   There's an auto-approve setting for when he trusts it.
6. **Posting** — via upload-post.com, a service that connects to all his social
   accounts through one API. Posts go out at good times of day with random
   jitter (to avoid looking like a bot), respecting per-platform daily caps.
   On X, links never go in the post body (they kill reach) — they go in a reply.
7. **Analytics** — every 6 hours it pulls views, likes, comments, shares, saves
   per post, and collects comments for sentiment analysis.
8. **Learning** — performance data flows back to improve future choices
   (explained in section 6).

An **Autopilot** switch runs this entire cycle on a schedule with no human
involvement (except approval, unless auto-approve is on).

**Offline-first:** the entire system runs with zero API keys or connected
accounts. Every external service (OpenAI, video generation, posting, trend
sources) has a fake "mock" mode that produces real artifacts — actual PNGs,
actual MP4s, simulated posts and metrics — so the whole machine can be watched,
tested, and tuned before spending money or posting anything real. All 59
automated tests run in this mode.

---

## 2. The playbook — 12 named strategies

Instead of generating generic "content," every post is made under one of twelve
named **strategies** — repeatable playbooks distilled from a large web-research
effort (12 research reports on platform culture, humor science, and what
actually worked for apps like this in 2025–2026). Each strategy defines which
platforms it fits, what formats it uses, how funny it should be, and gives the
AI writer specific instructions. The twelve:

1. **Pain-point POVs** (the workhorse, ~25% of content) — dramatize one
   hyper-specific moment of job-hunt suffering, e.g. "POV: it's 2:47 AM,
   application #83, the portal made you re-type your resume." The specificity
   IS the joke; people comment "same" as an act of belonging.
2. **Satirical UI franchise** — daily fake screenshots of job-application
   software with one unhinged-but-plausible feature ("Autofill is a premium
   feature — for employers only"). Rendered by real drawing code, not AI image
   generation, so the interface text is pixel-perfect (AI image models garble
   text, and the text is the joke). Home platform: X, daily.
3. **Educational hooks** — genuinely useful, save-worthy job-search tactics
   with real numbers ("your resume gets 7.4 seconds — here's what they see").
   The tip must stand alone; the product is step 3, never the headline. May
   only cite facts from a curated, verified fact list.
4. **Demo magic** — screen recordings of the product's 3-second magic trick
   ("watch this application fill itself"). The conversion engine. All numbers
   and screens must be real — fabricating results is banned outright.
5. **Unhinged mascot** — episodic content starring the AI character (section 4).
6. **Absurdist AI slop** — deliberately absurd AI-generated video that KNOWS
   it's AI and winks at it (e.g. bodycam footage of an "ATS raid" where police
   kick down a server-room door to find a printer shredding resumes). Research
   found audiences rate AI comedy *higher* when it admits being AI. Always
   labeled as AI content. Banned on LinkedIn, Reddit, and especially Bluesky.
7. **Meme carousels** — 5–8 original memes on one theme per swipe-through post.
8. **Trend-jack** — ride a fresh trend within hours (section 5).
9. **Contrarian takes** — strong defensible opinions ("cover letters are a
   loyalty test for a company that will ghost you"), always aimed at systems
   and processes from a whitelist (ATS, ghosting, unpaid internships…), never
   at named companies or people. Deliberately NOT rage-bait — platforms now
   punish manufactured outrage, and a job tool is a trust product.
10. **Social-proof receipts** — real product data as screenshots ("users applied
    to 40,000 jobs last month"). Only ~5% of the mix — proof is seasoning.
    Numbers must come from the real database; inventing them is treated as an
    existential failure (a competitor, Cluely, torched its credibility this way).
11. **Fake-text drama** — mini soap operas told as animated chat conversations
    (group chat reacting to a 9-round interview process), rendered by dedicated
    chat-bubble video code. One of the most-viewed automatable formats on
    TikTok. Product appears only as an incidental mention inside the story.
12. **Founder build-log** — build-in-public posts drafted from real product
    events in Sanjith's voice. **Never auto-posted** — always a draft for him.

Each strategy declares one **target emotion** from six: recognition ("too
real"), dark laughter (coping humor), righteous frustration (catharsis at the
system), hope (rare, earned sincerity — about 15% of content), satisfaction
(useful/satisfying), belonging (in-jokes and lore). One emotion per post, on
purpose — multi-emotion posts blur the message and the learning signal.

Strategies draw on per-product **knowledge pools** kept in config: a
*specificity bank* (real artifacts of the audience's life — "the Workday
account you made for one application in 2023"), *pain veins* (recurring
suffering themes), a *fact base* (verified stats only), and a *take pool*
(whitelisted contrarian targets). These are the raw specific material that
keeps content concrete instead of generic.

Which strategy gets used when is **learned per platform** (section 6), starting
from research-derived percentages. In the web app there's a **Playbook page**
where Sanjith can see every strategy and toggle them on/off per campaign.

---

## 3. The humor engine — how it writes actually-funny content

The core belief, backed by the research: an AI asked to "write something funny"
produces bland, hedged, explained jokes (a DeepMind study with professional
comedians called raw AI output "cruise ship comedy from the 1950s"). So Mark
never one-shots a joke. Every funny post goes through an assembly line:

**Step 1 — Violation search.** Before writing anything, the AI lists what is
genuinely *wrong, absurd, or secretly-true-but-never-said* about the topic.
This is "benign violation theory," the best-validated theory of humor: laughs
happen when something breaks how the world ought to be (violation) but is safe
to laugh at (benign). "Entry level, 5 years experience required" violates how
hiring should work; it's safe because the target is the system and the whole
audience has lived it. Each candidate violation is scored for strength and
safety; jokes are only built on ones that clear both bars. The practical point:
this forces every joke to be *about something* — the most common AI failure is
"humor-shaped" writing that punches at nothing.

**Step 2 — Structural scaffold.** The winning violation gets built into a joke
using a professional joke-writing decomposition (from comedy writer Greg Dean):
the model must explicitly name the *target assumption* (what the setup makes
you believe), the *connector* (the ambiguous element), the *reinterpretation*
(the second meaning revealed), and the *punch word* (which must come LAST).
If it can't name all four, that candidate is rejected as "not a joke yet."

**Step 3 — Persona fan-out.** It writes ~6 candidate versions, one per fixed
comedic persona: the Cynic, the Absurdist, the Deadpan Observer, the Neurotic
Student, the Corporate-Speak Parodist, and the Unhinged AI (the house voice —
openly a machine, plays it as the bit). Why personas: a model asked for six
jokes writes six versions of the same safe median joke; forcing distinct
personalities pushes it into genuinely different territory, which is what makes
the next step meaningful. (Technique validated in a 2026 paper, "HumorGen,"
where this fan-out + ranking let a small model beat models 4–18x larger.)

**Step 4 — Pairwise tournament.** Candidates compete head-to-head in pairs and
a judge model picks winners until one survives. Pairwise ("which of these two
is funnier?") instead of scoring 1–10, because research shows AI numeric humor
ratings correlate with humans at near-noise levels, while pairwise preference
works. The judge penalizes: guessable punchlines, any explanation after the
punch, hedging, generic references, punching down. The winner must also clear
the violation-strength and safety gates or the post ships as a normal non-joke
version instead — **a dead joke is worse than no joke.**

**Step 5 — Predictability filter.** Another model reads the winning joke's
setup *without* the final line and tries to guess the ending, three times. If
any guess substantially matches the punchline, the joke is killed and the
runner-up is promoted. Narrow on purpose: it only catches near-literal
predictability (~60% word overlap), so familiar *formats* (rule of three,
callbacks — which work through anticipation) are untouched; only
see-it-coming-mid-read endings die. It's also a config toggle if it proves too
aggressive.

**Step 6 — Delivery.** For videos, the script keeps the punchline on its own
line and the text-to-speech gets explicit delivery instructions: deadpan, dry,
"like someone who has survived 400 job applications," with a beat of silence
before the final line (studies of stand-up found experts lengthen the pre-punch
pause ~41% — timing is half the mechanism).

**The taste-learning part:** the pairwise judge is *calibrated on this specific
audience*. Whenever two of the account's own posts (same platform, same format)
show a ≥2x engagement gap, that pair becomes a labeled example — "this audience
preferred A over B" — injected into the judge's instructions. Sub-2x gaps are
treated as noise and never used; pairs rotate on a 90-day window so flukes age
out. In benchmark research this exact move (judging with real audience
preference data) took AI humor-ranking accuracy from 67% to 82.4% — matching
world-class human experts. Honest framing: this is context injection, not
model retraining — that's the state of the art short of fine-tuning, which is
the natural upgrade once hundreds of pairs accumulate.

Iron rules printed above every writing prompt: never explain the joke; punch
word last, nothing after it; specific beats generic (every post carries one
lived artifact); mock the system, never the audience; product is set dressing,
never the punchline; real numbers only; self-aware AI or no AI.

---

## 4. The characters — AI ambassadors with a universe

Research finding: every documented brand win in this space (Duolingo's owl,
Nutter Butter's cursed lore account — 3K→700K followers) is a *committed
character universe*, not one-off jokes. Callbacks and running lore are the
follower-conversion mechanism: the next joke pays more if you followed.

Mark ships two character "bibles" (editable YAML files):

**Poli the Apply Guy** (primary) — a small, slightly melted pastel-blue blob
creature with tired eyes, permanently wearing a crumpled lanyard reading
"APPLICANT #4,217". Deliberately synthetic-looking, never photoreal (research:
obviously-artificial characters avoid the uncanny valley, the disclosure
problem, AND the audience's AI-radar — a photoreal fake human is the dead
zone). Poli has been applying to jobs since before it can remember; wants one
(1) job; flaw: cannot stop applying, even to jobs it already has (the flaw
generates infinite episodes). Recurring off-screen antagonist: GREG, the ATS,
whose rejection emails always arrive at 2:47 AM. Poli knows it's AI and jokes
about it: "i am a marketing entity legally required to tell you i'm AI. the
recruiter who ghosted you was also a robot. we are not the same."

**TalentBot 9000** (secondary, switched off until Poli has traction) — a
cheerfully evil AI-recruiter parody: a floating video-interview screen with a
"reviewing your application…" progress bar frozen at 99%. Weaponized
recruiter-speak: "We were SO impressed by your qualifications. Unfortunately."
An archetype only — never depicts real companies or people.

How the system keeps a character consistent and alive:

- **Visual consistency:** one canonical reference-sheet image is generated
  once; every later image is generated *conditioned on that reference* (an
  image-editing API mode that preserves identity), and character videos are
  made by animating a reference-conditioned still (image-to-video), so the
  first frame already has the right identity. The lanyard prop is required in
  every prompt — a cheap anchor that survives model drift.
- **Voice consistency:** a pinned text-to-speech voice per character.
- **Lore state:** the database stores running counters (applications_submitted:
  4,217 and climbing), recurring NPCs, and active story arcs. Every approved
  episode advances the counters. Every episode must reference at least one
  prior event — callbacks are mandatory, explaining the lore in-post is banned.
- **Comment mining:** audience comments on character posts are pulled back into
  the next episode's planning ("you're all saying it has beef with Workday — it
  does now"). Community co-authorship is the documented growth engine of the
  best mascot accounts.
- **Hard rules:** the character never gives product testimonials (illegal under
  FTC rules for fake endorsers, and tonally wrong — it demos, does bits, and
  begrudgingly admits the app saves it time). Every character video carries an
  on-screen "AI character" disclosure, and posts set the platform's AI-content
  label (proactively labeled AI content loses far less reach than getting
  caught).

---

## 5. The trend radar — staying current in real time

Trend windows are short (memes peak in 3–5 days; a brand arriving late reads as
cringe and actively damages a youth brand), so this is built for speed with
strict discipline:

**Sources & cadence:**
- Every 30 minutes (free, freshest): rising posts from six job-related
  subreddits (r/recruitinghell, r/internships, r/jobs, r/csMajors, etc. —
  these are simultaneously trend signal AND content material), Bluesky's
  trending topics, Google Trends RSS.
- A few times daily: TikTok Creative Center trending hashtags, plus a live list
  of currently-alive meme templates (so a dead meme format is never used).

**Scoring & staging:** every trend sighting is stored, so the system computes
*velocity* (is it growing vs the last sighting?) and assigns a lifecycle stage:
new / rising / mature / declining. Key rules: a trend first seen already-huge is
classified *mature* (the rise was missed), and **declining is an unconditional
veto** — no score can override it. An AI pass also scores each trend for
relevance ("can we ride this while preserving the joke's structure?"), flags
unsafe origins (tragedy, community in-jokes, unclear origin → skip), and flags
*sound-dependent* trends — ones where the joke IS a specific audio. That last
flag matters because no posting API can attach native trending sounds; those
trends are surfaced for a 30-second manual step instead of auto-posting.

**The fast path:** when a hot trend qualifies (fresh + rising + relevant + safe
+ not sound-dependent), and auto-react is enabled, the system immediately
generates trend content — mapped onto the nearest house format rather than
invented from scratch (the Duolingo lesson: trend response is format-mapping,
not new creative). Capped at 2 reactions/day, deduplicated so the same trend
never triggers twice. Detection→drafted in minutes; the target is
detection→live in 2–6 hours, versus the 24–48h of the best human teams.

**Expiring drafts:** every trend post carries an expiry (24h for brand-new
trends, 72h for rising ones). If it isn't approved in time it auto-rejects.
It is mechanically impossible for this system to post a dead meme late.

**The skip discipline:** the system is designed to skip 80–90% of detected
trends. Great accounts are defined by what they don't post.

**The cascade ladder:** separately from trends, any post that beats its
platform's average engagement by 1.5x gets automatically re-expressed (not
copied — rewritten natively, novelty-checked) on lagging platforms a few days
later: TikTok winners → Instagram Reels & YouTube Shorts (Reels trends run 3–7
days behind TikTok, so every TikTok winner gets a second lottery ticket), X
winners → Threads.

---

## 6. The learning loop — how it improves over time

Three layers, at three speeds:

**Fast — the bandit (per post).** Every content decision — which strategy,
which comedic persona, which joke mechanism, which emotion, hook style, format,
posting time — is a "bandit arm": a small statistical record (a Beta
distribution — essentially a running tally of evidence) per choice, per
platform, per campaign, stored in the database. When a post's engagement comes
in, it's converted to a reward relative to the account's own baseline (with
shares and saves weighted 2x likes, because those are what actually predict
distribution in 2026), and the arms that post used get nudged. Selection then
*samples* from the distributions rather than always picking the current best —
so it keeps exploring, one lucky post can't flip a preference, and preferences
only shift as evidence accumulates. This is real statistics, robust to flukes
by construction — not notes in a prompt.

**Medium (days).** Top-performing posts get embedded and indexed as "winners";
future writing retrieves the most similar past winners as examples to emulate.
The cascade ladder replicates winners cross-platform. Audience comments feed
character lore. Comment replies are drafted for one-tap approval (replies in
the first hour are among the strongest ranking signals; sensitive comments —
visa panic, mental health, financial desperation — are flagged human-only and
never get an automated draft).

**Slow (weekly/monthly).** A weekly analysis pass produces plain-language
insights (best hooks, formats, times, sentiment summary, recommended
adjustments). Stale winners are pruned. The comedy judge re-calibrates on fresh
preference pairs from the account's own engagement. Sanjith's rejection notes
accumulate as standing constraints.

Expectation-setting from the research (important): judge nothing before ~30
posts per platform; expect 100–500 views/post on TikTok in weeks 1–4 and first
attributable installs around day 60–90. The compounding assets — the daily UI
franchise, the character lore, the calibrated judge — are the point; individual
post performance in month one is noise.

---

## 7. The web app (what Sanjith actually sees)

Local web app (`mark web`), pages:

- **Dashboard** — cross-campaign stats, engagement chart, live activity feed.
- **Campaigns** — run multiple products at once; per-platform posting cadence.
- **Studio** — the review queue. Media previews, edit any field, AI rewrite
  with an instruction, regenerate media, approve/reject. Posts now show badges:
  which strategy, target emotion, humor mechanism/persona, character, whether
  it's a trend ride, and a countdown chip if the trend window is closing.
- **Trends** — live trend list with stage badges (new/rising/mature/declining),
  a "Hot right now" rail, and a one-click **"Ride this trend"** button.
- **Playbook** — the 12 strategy cards with per-campaign on/off toggles, plus
  character management: edit personas/catchphrases, generate reference sheets,
  watch the lore counters.
- **Analytics** — performance per platform/day, comments with sentiment, and
  the drafted comment replies (editable, one-tap "mark posted"/skip, sensitive
  ones flagged amber).
- **Learn** — insights, the bandit leaderboard (which choices are winning).
- **Autopilot** — the master switch + upcoming scheduled runs.
- **Settings** — models, humor engine knobs, trend-reaction knobs (including
  the auto-react toggle), approval policy, spend tracking.

There's also a full CLI (`mark generate`, `mark react`, `mark strategies`,
`mark character sync`, etc.) for scripting.

---

## 8. Guardrails — what it deliberately won't do

- Never posts a declining trend; trend drafts expire rather than post late.
- Never fabricates numbers, testimonials, or outcomes. Social proof reads only
  from the real database.
- Never punches at students or vulnerable groups; contrarian takes target
  systems from a whitelist, never named companies or people.
- Never auto-posts to Reddit (drafts only — a human posts from a seasoned
  account), never posts founder-voice content without approval.
- Never puts AI-generated media on Bluesky (its community blocklists are
  crowdsourced and permanent).
- Never auto-replies to sensitive comments (visa/mental-health/desperation).
- Labels AI-generated content proactively (TikTok AIGC flag etc.) — labeled
  content loses far less reach than getting caught.
- Characters never claim to be human and never give testimonials (FTC).
- Banned-phrase lists kill marketing slop, AI-tell phrasing ("it's not X, it's
  Y"), engagement bait ("comment YES"), and expired slang (a list including
  rizz/no cap/delulu/skibidi — using dead slang is instant cringe).

---

## 9. Honest limitations (tell him these straight if asked)

1. **Cold start:** the learning layers need ~30 measured posts per platform
   before they're signal rather than noise. Until then the system runs on
   research-derived defaults — a strong starting hand, but not yet *his
   audience's* data.
2. **Joke ceiling:** any single joke is still limited by what an LLM can write.
   The architecture's guarantee is selection, not genius: bad jokes die before
   posting, good ones get identified, learned from, and replicated. (This is
   also how human writers' rooms work — volume, ranking, punch-up.)
3. **Judge calibration is prompt-level** (curated examples in context), not
   model fine-tuning — that's the honest state of the art at this data scale;
   fine-tuning is the upgrade path once hundreds of preference pairs exist.
4. **Preference pairs control for platform and format but not yet strategy** —
   a topic-luck confound is possible early on; the 2x-gap threshold and pair
   rotation mitigate it, and same-strategy-only pairing is a small change once
   there's enough data.
5. **Some things need Sanjith, once:** adding API keys (OpenAI, fal.ai for
   video, upload-post.com for posting), connecting social accounts, buying X
   Premium (free-account reach on X is effectively zero), pinning an ElevenLabs
   voice for Poli, and the 30-second manual sound-attach step for
   sound-dependent TikTok trends. Reddit posting is always manual by design.
6. **Trend sources have inherent lag:** TikTok's own trend data lags ~a day;
   the 30-minute Reddit/Bluesky polling is the early-warning compensation.
7. **No "reply-guy" on other people's viral posts yet** — replying to strangers'
   posts (a documented growth tactic) needs data sources the posting API
   doesn't provide; the system only drafts replies to comments on its own posts.

---

## 10. Current status

- All of the above is built, tested (59 automated tests, all passing), and
  verified end-to-end in a real browser session. A 17-agent adversarial code
  review found 10 real bugs; all were fixed with regression tests.
- The system currently runs in offline/mock mode — fully functional, spending
  nothing, posting nothing real — until API keys and social accounts are
  connected.
- The research behind every decision lives in the repo under `docs/research/`
  (12 reports + `MASTER-STRATEGY.md`, the master spec). The strategy catalog,
  humor engine, platform rules, and trend system are direct encodings of that
  spec.

### Suggested teaching order for the phone conversation
1. The basic machine (section 1)
2. The playbook (section 2)
3. The humor engine (section 3) — expect the most questions here
4. Characters (section 4)
5. Trend radar (section 5)
6. Learning loop (section 6) — second-most questions expected
7. Then guardrails, limitations, and status as wrap-up
