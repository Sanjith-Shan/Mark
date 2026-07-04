# Real-Time Trend Detection & Fast Trend-Riding for an Automated Content System (2025–2026)

*Research report for Mark — July 2026. Focus: programmatically accessible trend sources, trend lifecycle timing, brand-fit decisions, native-audio constraints, and a concrete detection→generation architecture.*

---

## 1. Where trends are actually visible first — and what's programmatically reachable

### 1.1 TikTok Creative Center (the single best free structured source)

TikTok Creative Center (`ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en` — with sibling paths `.../popular/music/...`, `.../popular/creator/...`, and top-ads pages) remains the canonical trend surface: **trending hashtags, trending songs, trending creators, and top ads**, filterable by country (100+) and period (7 / 30 / 120 days). It's login-free in the browser, which is why an ecosystem of scrapers wraps it.

Ground truth for 2026:

- **Data exposed:** hashtag name, rank + rank change (trend direction up/down), view counts, related videos, audience demographics (25+ fields via some scrapers); for songs: title, artist, rank trend over time, usage counts, play URL, cover art; for creators: follower counts and engagement.
- **How scrapers work:** the page is backed by an internal JSON API (`creative_radar_api/v1/popular_trend/...` family — `hashtag/list`, `sound/rank_list`, etc.). Scrapers hit those endpoints with rotating browser fingerprints. The Creative Center **does not** expose a trending-videos API; the video page internally reuses the hashtag endpoint ([Data365 analysis](https://data365.co/blog/tiktok-trends-api)).
- **Scraping viability is degrading:** TikTok's ToS explicitly prohibits automated Creative Center harvesting, and per [ScrapeBadger's 2026 guide](https://scrapebadger.com/blog/tiktok-scraping-apis-in-2026-the-complete-deep-guide), scrapers that worked in 2025 are failing in 2026 against ML bot detection (canvas fingerprinting, WebGL signatures, timing analysis). Naive `httpx`+cookie scraping is now fragile; plan for a headless browser (Playwright) or a paid scraper.
- **Official API:** TikTok's Research API is academic-only, ~4-week approval, 1,000 req/day, no commercial use. Effectively closed ([Data365](https://data365.co/blog/tiktok-trends-api)).
- **Turnkey options:** Apify actors — [Creative Center Scraper](https://apify.com/doliz/tiktok-creative-center-scraper), [TikTok Trends Scraper (hashtags+sounds+creators)](https://apify.com/automation-lab/tiktok-trends-scraper), [Trending Sounds Tracker](https://apify.com/alien_force/tiktok-trending-sounds-tracker) — pay-per-result, schedulable, JSON out. A [RapidAPI Creative Center API](https://rapidapi.com/Lundehund/api/tiktok-creative-center-api) and a free open-source proxy ([tiktok-discover-api](https://tiktok-discover-api.vercel.app/) — `getTrendingHashtag/Songs/Creators/Videos(country, page, limit, period)`) also exist, though free proxies die without warning.
- **Known lag:** Creative Center data is aggregated for advertisers and **lags the live app by hours to ~a day**, and is platform-wide rather than niche-specific. It tells you a trend is real; it doesn't catch hour-zero.

**Recommendation for Mark:** primary = a scheduled Apify actor (or self-hosted Playwright scraper as fallback) hitting hashtags + songs for US, 7-day period, twice daily minimum. Store rank, view count, and rank-delta so velocity is computable from your own history.

### 1.2 Trending sounds specifically

- **Creative Center music page** (above) is the structured source: rank, trend-over-time, usage counts.
- **[Tokchart](https://tokchart.com/)** publishes daily trending TikTok songs (videos-using-sound counts and growth) — scrapeable HTML, updated daily.
- **Apify sound scrapers** ([clockworks/tiktok-sound-scraper](https://apify.com/clockworks/tiktok-sound-scraper)) can pull per-sound usage counts for arbitrary sound IDs — useful for *tracking a specific sound's growth curve* once detected (poll a sound's video count daily; the second derivative tells you rising vs. saturated).
- **Human-curated weekly lists** as a cross-check: [HeyOrca's weekly trending audio](https://www.heyorca.com/blog/trending-audio-for-reels-tiktok), [Buffer's monthly IG sounds](https://buffer.com/resources/trending-audio-instagram/), [Later's Reels trends](https://later.com/blog/instagram-reels-trends/) — all updated weekly, scrapeable, and each entry usually includes "how to use it" context an LLM can consume directly. These are ~3–7 days behind the bleeding edge but pre-filtered for meme-format usability.

### 1.3 Google Trends — pytrends is dead

- **pytrends broke permanently in April 2025** when Google changed session auth; the library is unmaintained ([Glimpse](https://meetglimpse.com/software-guides/pytrends-alternatives/), [GitHub](https://github.com/GeneralMills/pytrends)). Do not build on it.
- **Google shipped an official Trends API (alpha) in 2025** — interest over time, trending now, related queries — but it's invite-only with tight quotas.
- Working alternatives in 2026: **[SerpApi Google Trends API](https://serpapi.com/blog/scraping-google-trends-with-python-pytrends-alternative/)** (structured JSON: trending searches, related queries, interest-over-time; ~$75/mo entry), **[ScrapingBee](https://www.scrapingbee.com/blog/best-google-trends-api/)**, **[Glimpse API](https://meetglimpse.com/google-trends-api/)** (adds absolute search volume + growth rates), **[Apify Google Trends actors](https://apify.com/steadyfetch/google-trends-scraper)** (cheapest for low volume).
- Also directly pollable with zero auth: **Google Trends "Trending Now" RSS** (`https://trends.google.com/trending/rss?geo=US`) still works in 2026 for realtime trending searches — free, but keyword-level only, no niche filtering.
- Role for Mark: Google Trends is a **verification and niche-seasonality source** (e.g., "internship season" spikes), not a first-alert source. Memes usually hit TikTok days before search.

### 1.4 X (Twitter)

- Official API: `GET /2/trends/by/woeid/{woeid}` requires **Basic tier, $200/mo**; a `personalized_trends` endpoint exists for the authenticated user ([X docs](https://docs.x.com/x-api/trends/get-personalized-trends)). A consumption-based pricing beta started Nov 2025 but trends remain paywalled.
- Third-party pay-per-call is dramatically cheaper: [twitterapi.io](https://twitterapi.io/blog/twitter-api-trending) and [API Direct](https://apidirect.io/endpoints/twitter-trends) at ~$0.006/request for trends by WOEID — polling US trends hourly costs ~$4/mo.
- X trends are **hours-fresh but noisy** (news/sports dominated). Best used to detect *text-meme formats* and discourse moments for X/Threads/Bluesky posts, not TikTok formats.

### 1.5 Reddit — the best free early-warning system

- Official API + PRAW still works free within rate limits (100 QPM with OAuth). `subreddit.rising()` and `/r/all/rising` are the highest-signal endpoints: posts with unusual upvote velocity *before* they peak ([Hootsuite on Reddit trends](https://blog.hootsuite.com/reddit-trends/)).
- For SudoApply's niche, poll `rising` on: r/csMajors, r/internships, r/jobs, r/recruitinghell, r/cscareerquestions, r/college — plus r/all for platform-wide memes. Niche-subreddit rising posts are simultaneously **trend signal and content material** (pain-point posts → relatable content angles).
- Reddit memes often precede TikTok text-memes by 1–3 days; r/recruitinghell screenshots are exactly SudoApply's content vertical.

### 1.6 YouTube

- **The Trending page was killed July 2025** ([TechCrunch](https://techcrunch.com/2025/07/10/youtube-is-getting-rid-of-its-trending-page-and-trending-now-list/)); the Data API's `chart=mostPopular` now draws from category charts (Music/Movies/Gaming), not a general trending feed.
- Verdict: YouTube is now a **low-value trend source** for a Shorts-posting tool. Trending music charts are a weak cross-check on sounds. Skip; treat YouTube as distribution-only.

### 1.7 Bluesky — free realtime firehose

- Unique among platforms: the **full firehose is free** via Jetstream WebSocket (JSON), and an unauthenticated trending endpoint exists: `https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics` ([atproto discussion](https://github.com/bluesky-social/atproto/discussions/3822), [firehose docs](https://docs.bsky.app/docs/advanced-guides/firehose)). One `curl` per hour gets platform trends for free.
- Volume is smaller and skews news/politics/tech — decent for X-style text trend detection, and Mark already posts there.

### 1.8 KnowYourMeme, newsletters, Exploding Topics

- **KnowYourMeme** has a trending surface (`trending.knowyourmeme.com/trending`) plus per-meme pages with origin/spread/status. No official API; simple scrapers exist ([culturgen on PyPI](https://pypi.org/project/culturgen/)). KYM **confirms and explains** memes (an LLM can be fed the KYM entry to understand a meme's meaning and whether it's offensive) but is a *lagging* indicator — if it has a full KYM page, it's mid-life. Use for context/safety-check, not detection. Crucially: **a "confirmed" KYM entry with declining activity = do-not-post signal**.
- **Newsletters as curated trend feeds:** [Link in Bio](https://thecmo.com/career/best-social-media-newsletters/) (Rachel Karten), **ICYMI** (Lia Haberman), Geekout, We Are Social. These arrive weekly and pre-digest which trends are brand-usable. Automatable via an inbox parser (subscribe with a dedicated address, LLM-summarize each issue into trend candidates). 3–7 days behind, but very high precision.
- **[Exploding Topics](https://makerstack.co/explodingtopics-review/)**: search-growth trend database; API on the $99/mo Investor plan. It detects *product/industry* trends over weeks-months, not memes over days. Low value for meme-riding; possible value for content-topic ideation ("AI resume screening" rising). Skip initially.

### 1.9 Source ranking for Mark (signal freshness × accessibility × cost)

| Source | Freshness | Access | Cost | Role |
|---|---|---|---|---|
| Reddit rising (niche subs) | Hours | Official API, free | $0 | Early alert + content material |
| TikTok Creative Center (hashtags+sounds) | ~1 day | Scraper/Apify | ~$5–30/mo | Primary structured trend feed |
| Tokchart / HeyOrca / Buffer weekly audio | 1–7 days | Scrape HTML | $0 | Sound shortlist + usage context |
| Bluesky trending endpoint | Hours | Free public API | $0 | Text-trend feed |
| X trends via twitterapi.io | Hours | Pay-per-call | ~$5/mo | Text memes/discourse |
| Google Trends RSS / SerpApi | Hours–1 day | Free RSS / paid API | $0–75/mo | Verification, niche seasonality |
| KnowYourMeme | Days | Scrape | $0 | Meme explanation + lifecycle stage + safety |
| Newsletters (ICYMI, Link in Bio) | ~Weekly | Email parse | $0 | High-precision curation |
| YouTube charts | Weak since 7/2025 | Data API | $0 | Skip |
| Exploding Topics | Weeks | API $99/mo | High | Skip for now |

---

## 2. The trend lifecycle — when to jump, when to skip

Numbers converge across 2025–2026 sources ([Together Agency](https://togetheragency.co.uk/news/the-shelf-life-of-a-tiktok-trend), [The List](https://www.thelist.com/800454/how-long-does-an-average-tiktok-trend-last/), [Best Colorful Socks stats roundup](https://bestcolorfulsocks.com/blogs/news/tiktok-product-trend-lifespan-statistics)):

- **Micro-trends/memes: 3–5 days** of peak relevance. **Sounds/formats: 1–3 weeks.** Broader content themes: up to 90 days.
- Canonical sound lifecycle stages:
  - **New (day 0–3):** just breaking. Post immediately *if* you have a clear angle. Highest reach multiplier, highest risk of misreading the joke.
  - **Rising (day 4–10):** the sweet spot for brands — audience is primed, format is understood, good creative still breaks out.
  - **Mature (day 11–21):** crowded; only enter with a genuinely differentiated twist.
  - **Declining (3+ weeks / mainstream brands piling in):** skip. "Once a brand joins in on a trend, that trend is often dead in the public's eyes" ([The Drum](https://www.thedrum.com/opinion/2022/08/22/brands-read-jumping-the-latest-meme-trend)); the [6-7 meme post-mortem](https://news.designrush.com/6-7-meme-dying-gen-alpha-marketing) shows brand adoption itself marking the death phase.
- **Cross-platform lag is exploitable:** Reels trends typically start on TikTok **3–7 days earlier**. Heuristic from [SocialPilot/Later data](https://www.socialpilot.co/blog/instagram-reels-trends): *sound viral on TikTok but <5,000 Reels on IG = head start; >100K Reels = window closing.* This gives an automated system a second chance at every TikTok trend: detect on TikTok day 2, ride on Reels day 4.
- **Dying-trend cringe risk** is asymmetric: a late meme actively damages a youth brand ("Hot Girl Summer" brand pile-on; Zoa's "Big Dwayne Energy" — [Zoomsphere](https://www.zoomsphere.com/blog/cringe-marketing-why-brands-are-embracing-weird-unhinged-strategies-in-2025)). For an 18–24 audience the rule is hard: **if in doubt about freshness, skip** — there is always another trend within 72 hours. Exception: *self-aware* lateness ("we're a job app, we found out about this trend from a LinkedIn post, obviously") can convert lateness into the joke itself — but that's a deliberate meta-format, not a fallback excuse, and should be rate-limited.

---

## 3. How fast brand teams actually operationalize this (Duolingo et al.)

The Duolingo playbook, per [Sprout Social](https://sproutsocial.com/insights/duolingo-tiktok-success/), [Technical.ly](https://technical.ly/company-culture/duolingo-viral-marketing-strategy-lessons/), and [Startup Spells](https://startupspells.com/p/duolingo-tiktok-playbook-850m-views-143-viral-videos) (850M organic views, 143 videos over 1M):

1. **Weekly trend-scan ritual + daily reactive posting.** A small team brainstorms weekly, sourcing primarily from **trending TikTok audio**, but executes individual trend responses in **hours-to-days**, not weeks.
2. **Minimal approval chain is the actual competitive advantage.** Social team posts without exec sign-off; legal/CMO consulted only for edge cases. "Memes live and die in days — if your approval chain involves legal, comms, and a VP, it's already over" ([Pulse Advertising](https://www.pulse-advertising.com/resources/social-media-news/meme-culture-social-media-marketing-2026/)). *Mark's equivalent: auto-approve (or one-tap phone approval) for trend-reactive posts; the human gate is the latency bottleneck, exactly like a VP sign-off.*
3. **A repeatable character/format multiplies trend speed.** Duo-the-owl + trend + menacing tone = a fill-in-the-blank template; the team doesn't reinvent a voice per trend. An automated system should likewise maintain 3–5 **house formats** (e.g., "deranged job-search POV", "screenshot + one-line caption", "self-aware AI-slop absurdism") so a trend only needs *mapping onto a format*, not de-novo creative.
4. **They skip most trends.** The formula is applied only where the mascot/brand angle is additive. High volume of *attempts* on fitting trends, zero attempts on non-fitting ones.
5. Speed benchmark: reactive posts within **24–48 hours** of a moment (e.g., the TikTok-ban "Oh so NOW you're learning Mandarin" post — [Brand24](https://brand24.com/blog/duolingo-social-media-strategy/)). An automated pipeline can beat this to ~2–6 hours, which is a genuine structural advantage over human teams.

---

## 4. Matching trends to the brand: the fit decision

Synthesis of [ChatterBlast](https://chatterblast.com/blog/brands-to-meme-or-not-to-meme/), [The Drum](https://www.thedrum.com/opinion/2022/08/22/brands-read-jumping-the-latest-meme-trend), [Zoomsphere](https://www.zoomsphere.com/blog/why-some-brands-shouldnt-touch-memes), plus Duolingo case studies — reduced to a scoreable rubric:

1. **Origin & meaning check (safety gate, binary):** does the trend originate from tragedy, a specific marginalized community's in-joke, a feud, or NSFW context? If origin is unclear → automatic skip. (KYM page + LLM read of top examples answers this.)
2. **Relevance score (0–1):** can the trend carry a job-search/college-life/AI angle **while preserving the joke's structure**? The operational test: *write the adaptation, then ask "would this be funny if the product name were removed?"* If the humor only exists as product promotion, it fails. LLM-judgeable: "Here is the meme format and 3 canonical examples. Here is our draft. Does the draft follow the format's actual comedic mechanic, or does it bend the format to sell?"
3. **Voice compatibility:** the brand already talks like a chronically-online student, so most Gen-Z meme formats are in-voice — but corporate-success or wealth-flex formats are off-voice. Maintain an allowlist/blocklist of format *genres*.
4. **Freshness stage** (from §2): only New/Rising, unless doing deliberate self-aware-late meta.
5. **Effort-to-window match:** if producing the adaptation takes longer than the remaining window (video render + approval + optimal post slot), downgrade to a faster content type (text/image riff on the same trend) or skip.
6. **The "can we add a product angle without ruining the joke" tiebreak:** best practice from Duolingo is that the product appears as *set dressing, not punchline* — the joke is about the audience's life (job hunting misery), the product is incidentally present. Encode as: product mention ≤1, never in the hook, never as the resolution of the joke.

Scoring: `fit = relevance × voice_match × freshness_multiplier`, with the safety gate as a hard filter. Empirically, a system should **skip ~80–90% of detected trends** — Duolingo-grade accounts are defined by what they don't post.

---

## 5. Sounds/audio: the hard constraint for API posting

### Why it matters
Trending audio remains a ranking signal in 2026: Instagram explicitly ranks Reels partly on **audio popularity** and gives the strongest boost to *early* users of a trending sound; sound pages are a discovery surface on both platforms ([Buffer](https://buffer.com/resources/trending-audio-instagram/), [Metricool](https://metricool.com/trending-audio-on-instagram/)). A sound is simultaneously a distribution channel (sound page) and a format template (the joke structure is the audio).

### The constraint: **APIs cannot attach native/licensed sounds. Period.**
- **TikTok Content Posting API** (which upload-post.com wraps): uploads video + caption only. No sound library, no stickers, no polls. Audio must be **fully embedded in the video file**; the post then shows as "original audio" and is **not linked to the trending sound's page** ([TokPortal](https://www.tokportal.com/learn/tiktok-sounds-api), [upload-post TikTok docs](https://www.upload-post.com/platforms/tiktok/)).
- **Instagram Graph API**: identical situation — no music-library or trending-audio attachment; the API lacks the app's music license and may strip or block posts with unlicensed embedded music. `audio_name` only labels your original audio ([Postproxy](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/), [Statusbrew](https://statusbrew.com/insights/adding-trending-audio-to-scheduled-content)).
- Baking a copyrighted trending song into the video file and uploading via API risks **mute/block/copyright strike**, since API uploads don't inherit the platform's music license.

### Workarounds, ranked for Mark
1. **Draft/inbox mode for sound-dependent posts (recommended):** upload-post supports TikTok `post_mode=MEDIA_UPLOAD`, which drops the finished video into the TikTok app inbox; the human opens the app, attaches the trending sound in 30 seconds, and publishes ([upload-post docs](https://www.upload-post.com/platforms/tiktok/)). This keeps 95% automation and captures the native-sound boost. Pipeline flags content as `requires_native_sound`, sends a push/CLI notification with the sound name + link.
2. **Design around the constraint:** favor trend formats where audio is *not* the mechanic — text-overlay memes, POV skits with **TTS voiceover** (Mark already generates TTS; original-audio voiceover content is fully API-postable and unaffected), screenshot humor, carousels. In 2026 a large share of TikTok meme formats are text/format-driven rather than sound-driven; the strategist should classify each trend as `sound-dependent` vs `format-dependent` and auto-post only the latter.
3. **Recreate the audio concept, not the audio:** for spoken/skit sounds, have TTS deliver the same comedic beat structure as original audio. Loses the sound-page discovery, keeps the format recognition.
4. **Device-farm posting (TokPortal-style, posts natively in-app on real devices) exists** but is a different trust/cost class ([TokPortal](https://www.tokportal.com/learn/post-tiktoks-programmatically-native-sounds)) — not worth it for a personal tool.
5. Never embed commercial music in API uploads. Only embed audio you generated (TTS, licensed/royalty-free).

---

## 6. Architecture recommendations for Mark

### 6.1 Polling cadence (source-appropriate, cheap)

| Job | Cadence | Notes |
|---|---|---|
| Reddit rising (6–8 niche subs + r/all) | **Every 30–60 min** | Free; highest freshness-per-dollar |
| Bluesky trending endpoint | Hourly | Free, one HTTP call |
| Google Trends RSS (US) | Every 2–3 h | Free |
| X trends (twitterapi.io, US WOEID) | Every 2–4 h | ~$0.006/call |
| TikTok Creative Center hashtags + sounds | **2–4×/day** | Data itself lags ~hours–1 day; more polling ≠ more freshness |
| Tokchart / weekly audio lists | Daily / on publish | Scrape |
| KnowYourMeme trending + entry lookup | Daily + on-demand | On-demand when validating a candidate |
| Newsletter inbox parse | On arrival | LLM extract → trend candidates |

Current `trend_monitoring_cron: "0 8,16 * * *"` (2×/day) is **too slow for the fast sources** — keep it for Creative Center, add a 30-min lightweight job for Reddit/Bluesky/RSS.

### 6.2 Freshness & velocity scoring (store history, score deltas)

The trends table already stores snapshots; the scoring must be **longitudinal**:

```
velocity   = (metric_now - metric_prev) / hours_elapsed        # per trend, per source
accel      = velocity_now - velocity_prev                       # 2nd derivative
z_spike    = (velocity_now - mean(velocity, 7d)) / std(velocity, 7d)
stage      = new (first seen <72h, accel>0) | rising (accel>0) | mature (accel≈0) | declining (accel<0)
freshness  = exp(-hours_since_first_seen / half_life)           # half_life ≈ 48h memes, 120h sounds
cross_src  = 1 + 0.5 * (n_sources_confirming - 1)               # Reddit+TikTok both seeing it = strong
final      = z_spike_norm * freshness * cross_src * llm_relevance(0-1)
```

Key rules: (a) a trend first seen **already at high rank** with flat velocity is *mature* — do not treat first-observation as fresh; (b) **declining stage is a hard veto** regardless of score; (c) cross-source confirmation (e.g., a joke format on r/recruitinghell + a related TikTok hashtag rising) is the strongest buy signal. This matches standard z-score/velocity spike practice in social trend detection ([Meltwater](https://www.meltwater.com/en/blog/trend-detection), [Kaylin AI](https://www.kaylinai.com/blog/ai-trend-prediction-analytics/social-media-trend-detection-algorithms-explained)).

### 6.3 Auto-trigger pipeline (event-driven generation, not just daily cron)

```
poller → trends table (snapshot + computed velocity/stage)
  └─ if z_spike > threshold AND stage ∈ {new, rising}:
       1. ENRICH: fetch KYM entry / top examples / sound usage count → meme_context
       2. SAFETY GATE (LLM): origin check → hard pass/fail
       3. FIT SCORE (LLM): relevance to SudoApply audience, voice match,
          "joke survives product angle" test → 0-1; skip if < 0.6
       4. FORMAT CLASSIFY: sound-dependent vs format-dependent;
          map to house format; pick fastest sufficient content_type
          (text riff ships in minutes; video in ~1h)
       5. TRIGGER strategist→writer→media with meme_context injected
          (strategy_context records trend id, stage, fit score, deadline)
       6. EXPIRING APPROVAL: trend content carries expires_at
          (new: +24h, rising: +72h); unapproved-by-deadline → auto-reject,
          never post stale trend content
       7. POST: trend posts may pre-empt the optimal-time schedule —
          for a new-stage trend, posting NOW beats posting at 17:00
       8. LADDER: TikTok first; if traction, auto-queue the Reels
          adaptation on day 2-4 (platform-lag arbitrage), X/Threads text
          version same-day
```

Budget: cap trend-triggered generations (e.g., ≤3/day) so a noisy spike day doesn't burn API credits; rank candidates and take the top.

---

## Pipeline implications

Concrete rules an automated system can encode:

1. **Replace pytrends** with Google Trends RSS (free, realtime trending) + SerpApi/Apify for interest-over-time; treat Google as verifier, not detector.
2. **Trend source stack:** Reddit rising on niche subs every 30–60 min (free, earliest, doubles as content material); TikTok Creative Center hashtags+sounds 2–4×/day via Apify actor with Playwright self-hosted fallback; Bluesky `getTrendingTopics` hourly (free); X trends via twitterapi.io (~$0.006/call); Tokchart daily for sounds; KYM on-demand for meme context/safety; newsletter inbox parser for weekly curation. Skip YouTube trending (page killed July 2025) and Exploding Topics (too slow, $99/mo).
3. **Score longitudinally, not point-in-time:** store every snapshot; compute velocity, acceleration, z-spike vs 7-day baseline; classify stage new/rising/mature/declining. First-seen-already-big + flat velocity = mature, not fresh.
4. **Hard timing rules:** act within 0–10 days of a trend's birth (new/rising only); declining = unconditional veto; expiring approvals (24–72h TTL) with auto-reject so stale trend content can never post; trend posts may override the optimal-time scheduler — immediacy beats time-slot optimization for new-stage trends.
5. **Platform-lag arbitrage:** every TikTok trend gets a second life on Reels 3–7 days later — auto-queue the Reels adaptation; heuristic: sound viral on TikTok + <5K IG Reels = go, >100K Reels = too late. Same-day text adaptation for X/Threads/Bluesky.
6. **Fit gate (LLM, two stages):** (a) safety — skip if origin is tragedy/community-in-joke/NSFW/unclear; (b) fit = "does the joke survive the product angle?" — draft the adaptation, judge whether it follows the meme's comedic mechanic vs bending it to sell; product appears once, never in hook, never as punchline. Expect to skip 80–90% of detected trends; encode a fit threshold (~0.6) and a daily cap (~3 trend-triggered generations).
7. **Sound constraint is absolute:** no API (upload-post, TikTok Content Posting API, IG Graph API) can attach native trending audio, and embedding commercial music invites copyright mutes. Classify every trend `sound-dependent` vs `format-dependent`; auto-post format-dependent (TTS/original audio is fully safe); route sound-dependent TikToks through upload-post draft mode (`MEDIA_UPLOAD`) + a notification telling the user which sound to attach in-app (30-second manual step); or recreate the audio's comedic beat with TTS, accepting loss of sound-page discovery.
8. **House formats as trend adapters (Duolingo lesson):** maintain 3–5 reusable format templates (deranged job-search POV, screenshot+one-liner, self-aware AI-slop absurdism); trend response = map trend onto nearest template, not de-novo creative. Minimal approval latency is the whole game — a one-tap approve (or auto-approve for text) is Mark's version of Duolingo's no-VP-sign-off policy; target detection→live in 2–6 hours, which beats the best human teams' 24–48h.
9. **Self-aware lateness is a format, not an excuse:** an occasional deliberately-late "we just found this trend on LinkedIn" meta-post fits the brand's AI-slop humor, but rate-limit it (≤1–2/month) and never use it to justify posting a genuinely dead meme straight.

### Key sources
[ScrapeBadger TikTok scraping 2026](https://scrapebadger.com/blog/tiktok-scraping-apis-in-2026-the-complete-deep-guide) · [Data365 TikTok Trends API](https://data365.co/blog/tiktok-trends-api) · [Apify Creative Center scraper](https://apify.com/doliz/tiktok-creative-center-scraper) · [Glimpse pytrends alternatives](https://meetglimpse.com/software-guides/pytrends-alternatives/) · [SerpApi Trends API](https://serpapi.com/blog/scraping-google-trends-with-python-pytrends-alternative/) · [X trends docs](https://docs.x.com/x-api/trends/get-personalized-trends) · [twitterapi.io trends guide](https://twitterapi.io/blog/twitter-trends-api-2026-guide) · [Hootsuite Reddit trends](https://blog.hootsuite.com/reddit-trends/) · [TechCrunch YouTube trending removal](https://techcrunch.com/2025/07/10/youtube-is-getting-rid-of-its-trending-page-and-trending-now-list/) · [Bluesky firehose docs](https://docs.bsky.app/docs/advanced-guides/firehose) · [atproto trending discussion](https://github.com/bluesky-social/atproto/discussions/3822) · [Together Agency trend shelf life](https://togetheragency.co.uk/news/the-shelf-life-of-a-tiktok-trend) · [SocialPilot Reels trends](https://www.socialpilot.co/blog/instagram-reels-trends) · [DesignRush 6-7 meme death](https://news.designrush.com/6-7-meme-dying-gen-alpha-marketing) · [Sprout Social Duolingo](https://sproutsocial.com/insights/duolingo-tiktok-success/) · [Technical.ly Duolingo process](https://technical.ly/company-culture/duolingo-viral-marketing-strategy-lessons/) · [Startup Spells Duolingo playbook](https://startupspells.com/p/duolingo-tiktok-playbook-850m-views-143-viral-videos) · [Pulse Advertising meme culture 2026](https://www.pulse-advertising.com/resources/social-media-news/meme-culture-social-media-marketing-2026/) · [The Drum on brand memes](https://www.thedrum.com/opinion/2022/08/22/brands-read-jumping-the-latest-meme-trend) · [TokPortal sounds API](https://www.tokportal.com/learn/tiktok-sounds-api) · [upload-post TikTok platform docs](https://www.upload-post.com/platforms/tiktok/) · [Postproxy Reels API guide](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/) · [Statusbrew trending audio scheduling](https://statusbrew.com/insights/adding-trending-audio-to-scheduled-content) · [Buffer trending IG audio](https://buffer.com/resources/trending-audio-instagram/) · [HeyOrca weekly audio](https://www.heyorca.com/blog/trending-audio-for-reels-tiktok) · [Tokchart](https://tokchart.com/) · [Meltwater trend detection](https://www.meltwater.com/en/blog/trend-detection) · [culturgen KYM scraper](https://pypi.org/project/culturgen/)
