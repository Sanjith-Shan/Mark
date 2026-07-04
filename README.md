# Mark

**A personal autonomous AI marketing engine with a web app.** Mark generates
platform-specific marketing content (images, video, carousels, text/threads) for
whatever you're building, posts it across TikTok, Instagram, X, LinkedIn, YouTube
Shorts, Bluesky, Threads, Reddit, and Pinterest, monitors engagement and comments,
and uses that data to improve future content over time.

Anyone can build anything now — what matters is who can sell it best. Mark is the
selling, on autopilot, so you can keep building.

This is a power tool for one person (you), not a SaaS.

---

## The web app

```bash
pip install -e .
mark web                # opens http://127.0.0.1:8321
mark web --autopilot    # start with the autonomous scheduler running
```

| Page | What it does |
| --- | --- |
| **Dashboard** | Cross-campaign stats, engagement chart, live activity feed, quick actions |
| **Campaigns** | Run many products at once — create/edit/pause/archive, per-platform cadence, subreddit & Pinterest board options |
| **Studio** | Review queue with media previews. Edit any caption, hook, hashtag, script, or image prompt. AI rewrite with your instruction, regenerate media, approve/reject (rejection feedback is learned from), post now |
| **Analytics** | Engagement and views per platform per day, top content, comments with sentiment |
| **Trends** | Live trending topics with lifecycle stages (new/rising/mature/declining), velocity, a "Hot right now" rail, and one-click **Ride this trend** |
| **Playbook** | The 12-strategy catalog — enable/disable per campaign, see platform fit, humor level, usage — plus AI ambassador characters: edit personas, generate reference sheets, watch the lore counters |
| **Learn** | What's working: best hooks/types/times per platform, analyzer recommendations, bandit leaderboard |
| **Autopilot** | One switch for the full loop: trends → generate → post at optimal times → analytics → weekly learning. Upcoming runs + live job progress |
| **Settings** | Provider status, connected accounts, models, approval policy, schedule, spend |

Long jobs stream progress live (SSE). Every piece of content is saved as a draft
before anything is posted; nothing goes out without approval unless you enable
auto-approve.

## Offline-first

Mark runs **end-to-end with no API keys**. Every provider (OpenAI, fal.ai,
upload-post.com, trend sources) has a real path and a deterministic offline path
that still produces real artifacts — actual PNGs, real 1080×1920 MP4s with
burned-in captions, simulated posts and metrics. A provider drops to offline mode
automatically when its key is missing, or globally with `--dry-run`.

Watch the entire pipeline work, tune everything, then add keys to `.env` to go
live one provider at a time. The topbar always shows live vs offline.

## Setup

```bash
pip install -e .            # core (runs fully offline)
pip install -e '.[all]'     # + video stack, posting SDK, trend libs

cp .env.example .env        # add keys when you're ready to go live
mark web                    # everything happens in the app from here
```

Requirements: Python ≥ 3.11 and `ffmpeg` (for video). On macOS: `brew install ffmpeg`.

Keys (`.env`): `OPENAI_API_KEY` (copy, images, TTS, embeddings),
`FAL_KEY` (AI video), `UPLOAD_POST_API_KEY` (posting + analytics via
upload-post.com — connect your socials on their dashboard),
`ELEVENLABS_API_KEY` (optional premium voices).

## The loop

```
STRATEGY    picks a named playbook (12-strategy catalog, learned per platform)
    │         pain-point POVs · satirical UI franchise · educational hooks ·
    │         demo magic · unhinged mascot · absurdist AI slop · meme carousels ·
    │         trend-jack · contrarian takes · social proof · fake-text drama ·
    │         founder build log (draft-only)
STRATEGIST  decides what to post (topic, angle, hook, ONE target emotion)
    │         ← live trends + RAG-of-winners + bandit recommendation
    │         ← per-product knowledge pools (pain veins / fact base / take pool)
WRITER      generates copy + media prompts (platform playbooks, 2026 rules)
    │         ← N variants → LLM judge → self-critique (anti-slop)
    │         ← your rejection feedback ("too generic") as hard requirements
HUMOR       when the strategy calls for funny: violation search → joke scaffold
    │         → 6-persona fan-out → pairwise judging (calibrated on YOUR
    │         audience's real preferences) → predictability filter → punch last
CHARACTER   mascot strategies front a persistent AI character (bible + lore +
    │         reference-sheet visual consistency + pinned voice)
NOVELTY     rejects near-duplicates — across ALL campaigns, so two products
    │         never post the same idea
MEDIA       images (OpenAI+Pillow) / video (fal + TTS + word-level captions
    │         + ffmpeg; image-to-video for character consistency) / carousels
APPROVAL    review in the Studio (or auto-approve once you trust it);
    │         trend content EXPIRES (a dead meme can never post late)
POST        upload-post.com at optimal times with jitter, per-day caps,
    │         user-scheduled times honored
ANALYTICS   metrics every 6h + comment collection + sentiment + reply drafts
FEEDBACK    engagement → bandit rewards (strategy, humor mechanism, persona,
            emotion, hook, type, time), winners re-indexed, judge calibration,
            winner cascade to lagged platforms (TikTok → Reels day 2-4)
```

**Real-time trend adaptation:** Reddit rising (niche subs) + Bluesky trending +
Google RSS every 30 minutes, TikTok Creative Center on the slower cron. Trends
get lifecycle stages (new/rising/mature/declining), safety + sound-dependency
gates, and a hard veto on dying memes. With `trends.auto_react` on, a qualifying
spike goes from detection to drafted content in minutes — target detection→live
is 2-6 hours, faster than any human social team.

The system **converges on what works for your audience, per campaign, per
platform**: the Thompson-sampling bandit learns strategies / humor mechanisms /
personas / emotions / hooks / formats / times, the RAG-of-winners feeds your
best past posts back as few-shot examples, and the comedy judge is calibrated
monthly from your own engagement preference pairs.

The research behind all of this lives in `docs/research/` —
`MASTER-STRATEGY.md` is the source of truth the code encodes.

## CLI

Everything is also scriptable: `mark init`, `mark product add/list/activate`,
`mark generate`, `mark queue/preview/approve/reject`, `mark post`,
`mark analytics`, `mark trends`, `mark react` (ride a hot trend now),
`mark strategies`, `mark character list/sync/sheet`, `mark learn`,
`mark insights`, `mark status`, `mark run` (headless scheduler), `mark web`.
Global flags: `--dry-run`, `--home`.

## Development

```bash
pytest                       # full suite, fully offline
cd web && npm install && npm run dev    # frontend dev server (proxies to :8321)
npm run build                # builds into src/mark/web/static (what `mark web` serves)

python3 scripts/demo_seed.py /tmp/mark-demo     # seed a demo home
python3 scripts/screenshot.py /tmp/mark-demo shots/   # screenshot every page
```

- `config/default.yaml` — platforms, models, quality knobs, crons, approval policy
  (all editable in Settings)
- `config/products/*.yaml` — campaign definitions (also managed in the app)
- `data/` — SQLite DB + generated media (gitignored)
