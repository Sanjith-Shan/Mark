# Mark

**A personal autonomous AI marketing engine.** Mark generates platform-specific
marketing content (images, video, carousels, text/threads) for whatever product
you're building, posts it across TikTok, Instagram, X, LinkedIn, YouTube Shorts,
Bluesky, and Threads, monitors engagement, and uses that data to improve future
content over time.

Anyone can build anything now — what matters is who can sell it best. Mark is the
selling, on autopilot, so you can keep building.

This is a power tool for one person (you), not a SaaS.

---

## Offline-first

Mark runs **end-to-end with no API keys**. Every external provider (OpenAI, fal.ai,
upload-post.com, trend sources) has a real path and a deterministic offline path
that still produces real artifacts — actual PNG images, real 1080×1920 MP4 videos
with burned-in captions, simulated posts and metrics. A provider drops to offline
mode automatically when its key is missing, or globally with `--dry-run`.

This means you can watch the entire pipeline work, review the output, and tune
everything before spending a cent. Add keys to `.env` to go live, one provider at a
time — `mark status` always shows which are `live` vs `mock`.

---

## Setup

```bash
pip install -e .            # core (runs fully offline)
pip install -e '.[all]'     # + video stack, posting SDK, trend libs

cp .env.example .env        # fill in keys when you're ready to go live
mark init                   # create the database + import the example product
```

Requirements: Python ≥ 3.11 and `ffmpeg` (for video). On macOS: `brew install ffmpeg`.

## Quickstart (offline)

```bash
mark product add --from config/products/example.yaml   # or: mark product add
mark generate                 # create drafts for every platform
mark queue                    # see what's pending
mark preview 1                # inspect one piece + its media files
mark approve --all            # (or: mark approve 1)
mark post                     # post approved content (simulated while offline)
mark analytics --collect      # pull/refresh engagement metrics
mark trends                   # show trending topics, ranked by product relevance
mark learn                    # run the feedback loop (bandit + winners + analyzer)
mark insights                 # read what's working
mark run                      # start the autonomous scheduler
```

## Commands

| Command | What it does |
| --- | --- |
| `mark init` | Create the database + config dirs |
| `mark product add/list/activate` | Manage products (active product is the current campaign) |
| `mark generate [--platform p] [-n N]` | Strategist → writer → media → save drafts |
| `mark queue` / `mark preview <id>` | Review pending content |
| `mark approve <id>` / `--all` · `mark reject <id> -f "..."` | Approval gate (rejection feedback is learned from) |
| `mark post [<id>] [--now]` | Post approved content |
| `mark analytics [--days N] [--collect]` | Engagement performance |
| `mark trends [--refresh]` | Trending topics scored for product relevance |
| `mark learn [--days N]` | Run the weekly feedback loop now |
| `mark insights` | Latest analyzer output |
| `mark status` | Active product, content counts, provider modes, spend, schedule |
| `mark run [--once]` | Autonomous scheduler (generation, posting, analytics, trends, feedback) |

Global flags: `--dry-run` (force offline) and `--home <dir>` (project root).

---

## How it works

```
STRATEGIST  decides what to post (topic, format, angle, hook, tone)
    │         ← trends + RAG-of-winners + bandit recommendation
WRITER      generates copy + media prompts
    │         ← N variants → LLM judge → self-critique (anti-slop) → finalize
NOVELTY     rejects near-duplicates of recent posts (audience fatigue guard)
MEDIA       images (OpenAI+Pillow) / video (fal+ffmpeg+captions) / carousels
SAVE        every piece is stored as a draft before anything goes out
APPROVAL    manual gate, or auto-approve once you trust it
POST        upload-post.com, at optimal times with jitter, per-day caps
ANALYTICS   pull engagement metrics on a schedule
FEEDBACK    normalize engagement → reward the bandit, re-index winners,
            analyze sentiment + patterns → insights → better next content
```

The system **converges on what works for your specific audience**: the bandit learns
the best hook styles / formats / tones / posting times per platform, and the
RAG-of-winners feeds your best past posts back in as examples.

## Configuration

- `config/default.yaml` — global settings: platforms, posting cadence/times, media
  models, the LLM quality knobs (`variants`, `self_critique`, `novelty_threshold`),
  scheduling crons, and the approval policy.
- `config/products/*.yaml` — one file per product (voice, audience, platforms,
  cadence). The **active** product is the campaign Mark is currently running.
- `.env` — API keys (never committed).

## Beyond the original spec (genuine additions)

These were added because they materially improve output quality or operability,
and are all controlled from `config/default.yaml`:

1. **Offline/mock mode** for every provider — the pipeline is runnable and testable
   without keys, producing real media files.
2. **Cost tracking** (`costs` table) — tokens + estimated USD per call, surfaced in
   `mark status`, so you see cost-per-post.
3. **Multi-variant + LLM-judge writing** (`llm.variants`) — generate several drafts,
   ship the strongest.
4. **Self-critique pass** (`llm.self_critique`) — enforces the anti-slop rules and
   revises before saving.
5. **Novelty guard** (`llm.novelty_threshold`) — embeds new content and rejects
   near-duplicates of recent posts.

## Tests

```bash
pytest
```

The suite runs fully offline and covers config/db, vectors, the bandit (including
that it *learns*), winners retrieval, the novelty guard, anti-slop stripping, and
the generation pipeline.
