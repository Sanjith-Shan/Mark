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
| **Trends** | Live trending topics ranked by relevance to your campaign, with notes on how creators are executing each trend |
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
STRATEGIST  decides what to post (topic, format, angle, hook, tone)
    │         ← live trends + RAG-of-winners + bandit recommendation
WRITER      generates copy + media prompts
    │         ← N variants → LLM judge → self-critique (anti-slop)
    │         ← your rejection feedback ("too generic") as hard requirements
NOVELTY     rejects near-duplicates — across ALL campaigns, so two products
    │         never post the same idea
MEDIA       images (OpenAI+Pillow) / video (fal + TTS + word-level captions
    │         + ffmpeg) / carousels with text overlays
APPROVAL    review in the Studio (or auto-approve once you trust it)
POST        upload-post.com at optimal times with jitter, per-day caps
ANALYTICS   metrics every 6h + comment collection + sentiment
FEEDBACK    engagement → bandit rewards, winners re-indexed, analyzer
            insights → better next content
```

The system **converges on what works for your audience, per campaign, per
platform**: the Thompson-sampling bandit learns hook styles / formats / tones /
posting times, and the RAG-of-winners feeds your best past posts back in as
few-shot examples.

## CLI

Everything is also scriptable: `mark init`, `mark product add/list/activate`,
`mark generate`, `mark queue/preview/approve/reject`, `mark post`,
`mark analytics`, `mark trends`, `mark learn`, `mark insights`, `mark status`,
`mark run` (headless scheduler), `mark web`. Global flags: `--dry-run`, `--home`.

## Development

```bash
pytest                       # 24 tests, fully offline
cd web && npm install && npm run dev    # frontend dev server (proxies to :8321)
npm run build                # builds into src/mark/web/static (what `mark web` serves)

python3 scripts/demo_seed.py /tmp/mark-demo     # seed a demo home
python3 scripts/screenshot.py /tmp/mark-demo shots/   # screenshot every page
```

- `config/default.yaml` — platforms, models, quality knobs, crons, approval policy
  (all editable in Settings)
- `config/products/*.yaml` — campaign definitions (also managed in the app)
- `data/` — SQLite DB + generated media (gitignored)
