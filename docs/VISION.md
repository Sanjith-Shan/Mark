# VISION.md — What Mark Must Become

> For any session working on this repo: this is the owner's end vision, stated
> without reference to what currently exists. Below it is one audit of the gaps
> between today's system and that vision — do your own audit on top of it, then
> work recursively toward the vision. `docs/research/MASTER-STRATEGY.md` is the
> content-strategy source of truth; `CLAUDE.md` holds the build rules (bias to
> simplicity, offline-first, everything reviewable). The owner's standing
> feature bar: only overwhelmingly-impactful additions — no gimmicks that add 1%.

---

## The End Vision

**Anyone can build anything now. Who sells it best is what matters. Mark is the
selling — fully, genuinely autonomous — so the owner never has to be involved
in creating content, posting it, or studying the market.**

Concretely, the finished Mark:

1. **Performs like a genius marketer, not a content generator.** It understands
   the market for whatever product it's pointed at: who the audience is, what
   they feel, what they're sick of, what makes them laugh, share, and buy. Its
   output should be indistinguishable from — or better than — a top-tier social
   team that lives on these platforms.

2. **Genuinely understands humor and emotion.** Not "funny-labeled" content —
   content that people actually laugh at, feel seen by, and send to friends.
   It knows what each audience finds funny, on each platform, and it can invoke
   any target feeling on demand: recognition, dark laughter, catharsis, hope,
   satisfaction, belonging. When something isn't funny enough, it knows, and it
   doesn't post it.

3. **Is always on the platforms.** It knows what is trending *right now* — the
   formats, the sounds, the discourse, the memes — reacts within hours while a
   trend is still rising, and never touches a dying one. Platform-native to the
   point of invisibility: every post reads like it came from someone who lives
   on that platform.

4. **Runs many strategies, each with a real pipeline.** Humor is one lane.
   Education, demos, characters/brand-ambassadors, social proof, contrarian
   takes, serialized storytelling — each a deliberate, platform-tuned pipeline,
   not one prompt with a different adjective. Includes persistent AI characters
   that front the brand with consistent identity, voice, and evolving lore.

5. **Evolves relentlessly.** Every post is an experiment. Every result updates
   what it believes. It converges on this audience's taste, kills what
   underperforms, doubles down on what compounds (series, franchises, lore),
   and adapts to platform/algorithm shifts and brand-new trends immediately —
   without being told. Six months in, it should be measurably better than month
   one, on its own data.

6. **Closes the loop to business results.** Views are instrumental; the goal is
   users. It should know which content produces clicks, installs, and signups,
   and steer toward that — not vanity metrics.

7. **Zero-involvement operation, with taste.** Full autonomy is the default
   destination: it drafts, approves its own work when quality is proven, posts,
   replies, learns. The owner's role shrinks to occasionally glancing at a
   dashboard and enjoying the results. But autonomy is earned — it must be
   trustworthy enough (quality gates, guardrails, self-monitoring) that
   unattended operation is safe for the brand.

8. **Works for the next product too.** Point Mark at a brand-new product and it
   should research the market, build the audience model, the pain language, the
   strategy mix, and the character concepts itself — the same way it was done
   for the first product — rather than needing hand-curated config.

---

## Gap Audit (July 2026) — one assessment; do your own on top

Ordered roughly by expected impact toward the vision.

### 1. It has never run live
Everything is verified offline/mock (59 tests + browser e2e), but no real API
call has ever been made: OpenAI image `images.edit` reference params, fal.ai
image-to-video argument names, upload-post platform params (TikTok `is_aigc`
passthrough is a guess), Creative Center scraping against 2026 bot detection —
all untested against reality. **Gap:** a go-live hardening pass — a live smoke
harness with a tiny budget cap that exercises every provider path once, fixes
the breakage, and a provider-degradation report in the UI. Highest-value next
step; everything else compounds only after real posts flow.

### 2. Reward signal is thin and credit assignment is blunt
Learning quality is capped by what it optimizes. Today: one engagement rate per
post (shares/saves 2x), applied identically to every choice the post made — a
great hook on a bad topic rewards both. Missing: follower delta per post,
profile visits, per-platform primary KPIs (X quote/like ratio, IG sends, Shorts
loop rate — where obtainable), watch-time proxies, and any *negative* signals.
**Gap:** richer per-platform reward composition; smarter credit assignment
(contextual bandit, or judge-attributed partial credit per dimension).

### 3. No conversion attribution (vision #6)
No UTM generation on links, no click→install→signup tracking, no
content→conversion feedback. The system optimizes engagement, not customers.
**Gap:** UTM-tagged links per post, a lightweight attribution ingest (even just
click counts per link), and conversion-weighted rewards once data exists.

### 4. Autonomy is binary, not earned (vision #7)
`auto_approve` is a global on/off. The vision needs *graduated* autonomy:
auto-approve when the content's QA scores are high AND that strategy/platform
has a proven track record; route to human only below the confidence bar; expand
autonomy automatically as trust accumulates. Also missing self-monitoring for
unattended safety: engagement-collapse detection with automatic cool-down,
platform kill-switches (e.g. freeze Bluesky queue on any AI accusation), spend
budgets with alerts, account-suppression heuristics.

### 5. Knowledge doesn't self-refresh (vision #1, #5)
The audience model (specificity bank, pain veins, fact base, take pool) is
hand-curated YAML. The system already collects the raw material to maintain
these itself (comments, Reddit rising posts, trend data). **Gap:** a periodic
job that mines fresh pain language and artifacts from collected data, proposes
pool updates, retires stale entries. Same for the expired-slang blocklist.

### 6. Media ceiling is well below "top-tier social team" (vision #1, #4)
Video is single-clip background + voiceover + captions. Missing: multi-shot
narrative assembly (chaining 7–8×8s generated clips into 60s arcs), concrete
multi-reference character video (Kling Elements / Veo Ingredients wiring),
model routing per content template (per MASTER-STRATEGY §6.3), a demo-capture
library pipeline (real screen recordings, re-cut per post), richer carousel
design system (current: text overlay on generated background). Character sheets
are a single still, not the 4–8 pose grid the spec calls for.

### 7. Humor learning upgrade path unexploited (vision #2)
Judge calibration is few-shot pairs in context. Once a few hundred preference
pairs accumulate: fine-tune a cheap judge model on them; mine pairs
same-strategy; persist per-mechanism/persona Elo from tournament outcomes
instead of discarding them; and validate humor QA against real outcomes (do
gate-passing jokes actually outperform? — auto-tune the thresholds).

### 8. Trend radar blind spots (vision #3)
No trending *sounds* data (and the sound-dependent → TikTok draft-mode
(`MEDIA_UPLOAD`) + push-notification flow is classified but not implemented);
no X trends (paid API — ~$5/mo via third parties); no KnowYourMeme enrichment
for meme context/safety; Creative Center scraper has no hardened fallback
(Apify/Playwright); no capability-window trigger (new video-model release →
boost the slop lane — every documented slop hit was a first-mover capability
play).

### 9. Series aren't first-class (vision #5)
Episodic strategies derive an episode number, but there are no series objects
with premises, per-series retention stats, and the kill-rule (retire a series
underperforming baseline 3 episodes running; spawn a replacement premise).
Franchise compounding is the core growth asset — it deserves real bookkeeping.

### 10. Community layer is one-way (vision #3, #5)
Replies are drafted only for comments on own posts. Missing: the reply-guy
program (drafting replies to fresh posts from a watchlist of large adjacent
accounts — the #1 documented sub-1K X growth tactic), Reddit comment-draft
workflow with karma tracking, and first-hour reply scheduling tied to post
times.

### 11. New-product onboarding is manual (vision #8)
Strategy catalog, knowledge pools, and characters are SudoApply-tuned by hand.
**Gap:** an onboarding pipeline that, given a new product description, runs the
research (audience, pain language, platform fit, character concepts, fact
base) and generates the campaign config automatically — the repeatable version
of what was done manually for SudoApply.

### 12. Experimentation is implicit only
The bandit explores, but there's no deliberate A/B mechanism: no hook/thumbnail
variants of the same post across platforms, no Instagram Trial Reels usage at
1K followers, no holdout comparisons to validate that the learning loop is
actually lifting performance vs. baseline.

---

*Whoever picks this up: re-audit first (the codebase moves fast), rank by
impact-toward-vision ÷ effort, and remember the owner's bar — build the things
that change the trajectory, skip the things that decorate it.*
