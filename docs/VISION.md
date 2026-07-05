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

## Status after the July 5, 2026 improvement session

A 8-subsystem adversarial audit (100+ findings) was run and worked down. What
changed — mapped to the vision numbers above:

* **#5 Evolution (the core)** — rewrote the learning math: graded saturation-free
  rewards (`rate/(rate+baseline)`; a 10x hit ≠ a 1.05x post), per-platform
  baselines (medians; no more pooled-scale distortion), exactly-once reward
  crediting at 48h maturity (feedback now safely runs every analytics sweep, not
  weekly), evidence decay with a 45-day half-life (adaptation to shifts is now
  mechanically possible), informative strategy priors from the research mix
  weights, per-platform freshness-windowed winners, same-strategy+view-floor
  calibration pairs, clicks folded into the reward, analyzer insights fed back
  into the strategist, and post-time arms that actually gate posting slots.
  **Empirical proof exists**: `mark evolve-proof` / `scripts/evolution_proof.py`
  runs the full production loop against a planted hidden audience taste —
  convergence (0.32→0.55 best-arm share), +23% lift over a permanent random
  holdout, and re-convergence after a mid-run taste inversion, all PASS; a fast
  version runs in CI (`tests/test_evolution.py`). A live holdout policy
  (`learning.holdout_pct`) keeps proving lift forever on real accounts.
* **#7 Earned autonomy** — `approval.mode: graduated`: auto-approval requires
  the draft's persisted QA scores AND a per-(strategy, platform) track record;
  decay revokes autonomy when performance fades. Self-monitoring: engagement-
  collapse detection pauses a platform with a cool-down + alert, daily spend cap
  freezes generation. Trend reactions that earn approval post immediately
  (detection→live in one pass).
* **#8 Any product** — `mark onboard "<description>"` researches and generates a
  full campaign: audience model, voice, knowledge pools, per-strategy
  domain-adapted briefs, trend subreddits/keywords, character concept, rating.
  fact_base stays empty until human-verified (hard rule).
* **NEW: content-as-the-business** — campaigns with `kind: entertainment`: no
  product, no CTA; product-bound strategies excluded; prompts reframe success
  as watch/share/follow. The summer test lab is supported end-to-end: per-
  campaign upload-post profiles (accounts), per-campaign caps/trend sources, and
  an `experiments` layer (campaigns as A/B variants with comparison reports).
* **NEW: edge calibration** — per-campaign `content_rating` (clean/standard/
  edgy-PG-13) with platform ceilings (LinkedIn always clean); the humor
  benignness gate and all comedy prompts move with it. Hard lines (slurs, hate,
  punching down, tragedy) survive every rating.
* **Corrections everywhere** — double-posting atomic claim, expiry enforcement
  on all posting paths, UTM-tagged links (vision #6 attribution opened), karaoke
  caption fix, multi-shot AI video, chat-drama audio + pacing, franchise
  carousels, campaign-scoped trends with real velocity math, live-refusal no
  longer silently posts mock copy, series objects with the 3-strikes kill rule,
  knowledge self-refresh mining comments into the specificity bank.

Remaining (deliberately): the go-live hardening pass (nothing has hit a real
API yet — unchanged top priority before the summer lab), trending *sounds* +
X trends + KnowYourMeme sources, judge fine-tuning once preference pairs
accumulate, Instagram Trial Reels, and the reply-guy program (blocked on data
the posting API doesn't provide).

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
