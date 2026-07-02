# CLAUDE.md — Autonomark: Personal Autonomous AI Marketing Platform

## What This Is

A personal Python CLI tool that autonomously generates platform-specific marketing content (images, video, text, carousels) for whatever product I'm currently working on, posts it across TikTok, Instagram, X, LinkedIn, YouTube Shorts, Bluesky, Threads, and Reddit, monitors engagement, and uses that data to improve future content over time. This is NOT a SaaS product — it's a power tool for one person (me).

## Golden Rules

1. **Every architectural decision is already made in this file.** Do not second-guess the stack. Build with what's specified.
2. **Build in phases.** Each phase must be fully working before moving to the next. Never stub out "TODO" placeholders — implement completely or don't start.
3. **Bias toward simplicity.** One file per concern. No over-abstraction. No class hierarchies deeper than 2 levels. Functions over classes when possible.
4. **All config is YAML.** All secrets are env vars loaded via `.env`. Never hardcode API keys.
5. **Every generated piece of content must be saved to the database before posting.** Content is always reviewable.
6. **Expand where you see fit.** If something in this spec is underspecified, make the best engineering decision and document it in a comment.

---

## Tech Stack (exact libraries)

```
# Core
python = "^3.11"
openai >= 1.80             # LLM + image generation (user has thousands in credits)
fal-client >= 0.5          # Video generation (Kling 3.0, Veo 3, Seedance, Wan)
upload-post >= 2.2         # Unified social media posting API (13 platforms)
httpx >= 0.27              # Async HTTP client

# Media
Pillow >= 10.0             # Image processing, carousel assembly
moviepy >= 2.0             # Video composition and editing
ffmpeg-python >= 0.2       # FFmpeg wrapper for transcoding
whisper-timestamped >= 1.0 # Word-level timestamps for captions (or openai whisper)

# Data
sqlite3 (stdlib)           # Database — no ORM, use raw SQL with helper functions
numpy >= 1.26              # Embeddings math, bandit calculations

# Scheduling & CLI
apscheduler >= 3.10        # Job scheduling
typer >= 0.12              # CLI framework
rich >= 13.0               # Terminal UI, tables, progress bars

# Config & Utils
pyyaml >= 6.0              # Config files
python-dotenv >= 1.0       # .env loading
pydantic >= 2.0            # Config/data validation models
```

### External API Keys Required (`.env`)
```
OPENAI_API_KEY=            # Text generation, image generation, TTS, embeddings
FAL_KEY=                   # Video generation via fal.ai
UPLOAD_POST_API_KEY=       # Social media posting via upload-post.com
ELEVENLABS_API_KEY=        # (optional) Higher quality TTS voices
```

### External Account Setup
- **upload-post.com**: Sign up, subscribe to Basic plan ($16/mo), connect social accounts (TikTok, Instagram, YouTube, X, LinkedIn, Threads, Pinterest, Reddit, Bluesky) via their dashboard. Note the profile username — it's used in every API call.
- **fal.ai**: Sign up, generate API key. Pay-per-use, no subscription needed. $10 free credits on signup.

---

## Project Structure

```
autonomark/
├── CLAUDE.md
├── pyproject.toml
├── .env                          # API keys (gitignored)
├── config/
│   ├── default.yaml              # Global settings (posting times, platforms, defaults)
│   └── products/
│       └── example.yaml          # Per-product config (brand voice, target audience, etc.)
├── src/
│   └── autonomark/
│       ├── __init__.py
│       ├── cli.py                # Typer CLI — all user-facing commands
│       ├── config.py             # Pydantic models for config loading/validation
│       ├── db.py                 # SQLite database: schema, migrations, query helpers
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── strategist.py     # Decides WHAT to post (topic, format, platform, angle)
│       │   ├── writer.py         # Generates platform-specific copy
│       │   ├── media.py          # Orchestrates image/video/carousel generation
│       │   └── analyzer.py       # Analyzes engagement data, extracts insights
│       ├── media/
│       │   ├── __init__.py
│       │   ├── images.py         # OpenAI image generation + Pillow processing
│       │   ├── video.py          # fal.ai video gen + FFmpeg/MoviePy assembly
│       │   ├── captions.py       # Word-level caption overlay for videos
│       │   └── tts.py            # Text-to-speech (OpenAI TTS or ElevenLabs)
│       ├── posting/
│       │   ├── __init__.py
│       │   ├── manager.py        # Routes content to the right poster
│       │   └── upload_post.py    # upload-post.com SDK wrapper
│       ├── trends/
│       │   ├── __init__.py
│       │   ├── tiktok.py         # TikTok Creative Center trend scraper
│       │   ├── google_trends.py  # Google Trends via pytrends or scraping
│       │   └── aggregator.py     # Merges all trend sources into ranked topics
│       ├── analytics/
│       │   ├── __init__.py
│       │   ├── collector.py      # Pulls engagement metrics (upload-post analytics API)
│       │   └── sentiment.py      # Comment sentiment analysis via OpenAI
│       ├── learning/
│       │   ├── __init__.py
│       │   ├── winners.py        # RAG-of-winners: embed + index top posts
│       │   ├── bandit.py         # Contextual bandit (LinUCB) for content optimization
│       │   └── feedback.py       # Orchestrates the full feedback loop
│       └── scheduler/
│           ├── __init__.py
│           └── engine.py         # APScheduler job definitions and lifecycle
├── data/                         # Runtime data (gitignored)
│   ├── autonomark.db             # SQLite database
│   ├── media/                    # Generated media files
│   └── winners/                  # Serialized winner embeddings
└── tests/
```

---

## Database Schema (SQLite)

Use raw SQL with helper functions. No ORM. Use `sqlite3.Row` for dict-like access. Enable WAL mode on connection.

```sql
-- Products/campaigns being marketed
CREATE TABLE products (
    id TEXT PRIMARY KEY,                -- slug, e.g. "sudoapply"
    name TEXT NOT NULL,
    description TEXT NOT NULL,          -- what the product does
    target_audience TEXT NOT NULL,       -- who we're targeting
    brand_voice TEXT NOT NULL,           -- tone/style guidelines
    website_url TEXT,
    platforms TEXT NOT NULL,             -- JSON array of platform names
    posting_cadence TEXT NOT NULL,       -- JSON: {"tiktok": 2, "instagram": 3, ...} posts/day
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual pieces of content
CREATE TABLE content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    platform TEXT NOT NULL,             -- "tiktok", "instagram", "x", "linkedin", etc.
    content_type TEXT NOT NULL,         -- "video", "image", "carousel", "text", "thread"
    caption TEXT,                       -- The post text/caption
    hashtags TEXT,                      -- JSON array
    hook TEXT,                          -- The opening hook line
    media_paths TEXT,                   -- JSON array of local file paths
    media_urls TEXT,                    -- JSON array of public URLs (if uploaded)
    strategy_context TEXT,              -- JSON: why this content was chosen (topic, angle, trend)
    status TEXT DEFAULT 'draft',        -- "draft", "approved", "posted", "failed", "rejected"
    rejection_feedback TEXT,            -- User feedback when rejecting (used for learning)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    posted_at TIMESTAMP
);

-- Post records (after posting)
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content(id),
    platform TEXT NOT NULL,
    platform_post_id TEXT,              -- The ID returned by the platform/upload-post
    request_id TEXT,                    -- upload-post request_id for analytics
    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Engagement metrics (time-series)
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,   -- computed: (likes+comments+shares+saves) / views
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Comments collected for sentiment analysis
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    comment_text TEXT NOT NULL,
    sentiment TEXT,                     -- "positive", "negative", "neutral"
    sentiment_score REAL,
    analyzed_at TIMESTAMP
);

-- Top-performing posts for RAG-of-winners
CREATE TABLE winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content(id),
    platform TEXT NOT NULL,
    content_type TEXT NOT NULL,
    caption TEXT,
    hook TEXT,
    engagement_rate REAL NOT NULL,
    embedding BLOB,                    -- numpy array serialized as bytes
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bandit arms and state
CREATE TABLE bandit_arms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arm_type TEXT NOT NULL,             -- "hook_style", "format", "post_time", "tone", "topic_angle"
    arm_value TEXT NOT NULL,            -- The specific value, e.g. "question_hook", "listicle", "9am"
    platform TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES products(id),
    pulls INTEGER DEFAULT 0,
    total_reward REAL DEFAULT 0.0,
    avg_reward REAL DEFAULT 0.0,
    alpha REAL DEFAULT 1.0,            -- Beta distribution param (for Thompson sampling)
    beta_param REAL DEFAULT 1.0,       -- Beta distribution param
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(arm_type, arm_value, platform, product_id)
);

-- Trend data cache
CREATE TABLE trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,               -- "tiktok", "google", "x", "reddit"
    topic TEXT NOT NULL,
    trend_score REAL,                   -- Normalized relevance score
    metadata TEXT,                      -- JSON: hashtags, related sounds, etc.
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Config Format

### `config/default.yaml`
```yaml
upload_post:
  profile_username: "my-profile"    # Your upload-post.com profile name

platforms:
  tiktok:
    enabled: true
    max_posts_per_day: 2
    content_types: ["video"]
    optimal_times: ["11:00", "17:00", "20:00"]  # Will be refined by bandit
    hashtag_count: 5
    privacy_level: "PUBLIC_TO_EVERYONE"
  instagram:
    enabled: true
    max_posts_per_day: 2
    content_types: ["video", "carousel", "image"]  # Reels, carousels, feed
    optimal_times: ["08:00", "12:00", "17:00"]
    hashtag_count: 15
  x:
    enabled: true
    max_posts_per_day: 3
    content_types: ["image", "text", "thread", "video"]
    optimal_times: ["09:00", "12:00", "18:00"]
    hashtag_count: 3
  linkedin:
    enabled: true
    max_posts_per_day: 1
    content_types: ["text", "image", "carousel"]
    optimal_times: ["08:00", "16:00"]
    hashtag_count: 5
  youtube:
    enabled: true
    max_posts_per_day: 1
    content_types: ["video"]             # Shorts only
    optimal_times: ["12:00", "17:00"]
  bluesky:
    enabled: true
    max_posts_per_day: 3
    content_types: ["text", "image"]
    optimal_times: ["09:00", "14:00", "19:00"]
    hashtag_count: 0
  threads:
    enabled: true
    max_posts_per_day: 2
    content_types: ["text", "image"]
    optimal_times: ["10:00", "19:00"]

media:
  image_model: "gpt-image-1.5"         # or "gpt-image-2" for highest quality
  image_quality: "medium"               # "low", "medium", "high"
  video_model: "fal-ai/kling-video/v3/text-to-video"  # Default video model
  video_fallback: "fal-ai/wan/v2.6/text-to-video"     # Cheaper fallback
  video_duration: 8                     # seconds, default
  video_resolution: "720p"
  tts_provider: "openai"               # "openai" or "elevenlabs"
  tts_voice: "onyx"                     # OpenAI voice name

scheduling:
  timezone: "America/Los_Angeles"
  content_generation_cron: "0 6 * * *"  # Generate content daily at 6am
  analytics_collection_cron: "0 */6 * * *"  # Collect analytics every 6 hours
  trend_monitoring_cron: "0 8,16 * * *"     # Monitor trends twice daily
  feedback_loop_cron: "0 0 * * 0"           # Weekly feedback loop analysis

approval:
  auto_approve: false                   # Set true once you trust the output
  auto_approve_types: []                # Content types to auto-approve, e.g. ["text"]
```

### `config/products/example.yaml`
```yaml
id: "sudoapply"
name: "SudoApply"
description: |
  An AI-powered job application platform that automates applying to jobs.
  Features multi-resume support, ATS autofill via Chrome extension, and a
  Kanban application tracker. Built for students hunting for internships.
target_audience: |
  College students (18-24) actively looking for internships and entry-level jobs.
  Frustrated by the repetitive nature of job applications. Tech-savvy, use
  LinkedIn and job boards daily. Active on TikTok, Instagram, X, and LinkedIn.
brand_voice: |
  Casual, relatable, slightly irreverent. Speaks like a fellow student who gets
  the pain of job hunting. Uses humor and memes. Never corporate-speak.
  First person plural ("we") or second person ("you").
  Short sentences. Punchy hooks.
website_url: "https://sudoapply.com"
platforms: ["tiktok", "instagram", "x", "linkedin", "youtube", "bluesky"]
posting_cadence:
  tiktok: 2
  instagram: 2
  x: 3
  linkedin: 1
  youtube: 1
  bluesky: 2
```

---

## Content Pipeline (the core loop)

This is the exact sequence that runs when content is generated:

```
1. STRATEGIST AGENT
   Input:  product config + recent trends + winners index + bandit recommendation
   Output: ContentPlan (platform, content_type, topic, angle, hook_style, tone)

2. WRITER AGENT
   Input:  ContentPlan + product config + winner examples (RAG)
   Output: ContentDraft (caption, hashtags, hook, script if video, alt_text)

3. MEDIA GENERATOR
   Input:  ContentDraft + content_type
   Output: MediaAsset (file paths to generated images/video)
   
   For VIDEO:
     a. Generate voiceover from script via TTS
     b. Generate visuals via fal.ai (Kling/Veo/Seedance) OR
        assemble from generated images + transitions via MoviePy
     c. Add word-level captions overlay via Whisper timestamps + MoviePy
     d. Export as 1080x1920 H.264 MP4 (9:16 vertical)
   
   For IMAGE:
     a. Generate via OpenAI gpt-image model
     b. Resize/crop to platform specs via Pillow
   
   For CAROUSEL:
     a. Generate each slide as a separate image
     b. Include text overlays on each slide

4. SAVE TO DB
   Insert into `content` table with status='draft'

5. APPROVAL GATE
   If auto_approve: set status='approved'
   Else: wait for user to approve via CLI (`autonomark approve <id>`)

6. POSTER
   Once approved, queue for posting at optimal time
   Call upload-post.com API to post
   Save platform_post_id and request_id to `posts` table

7. ANALYTICS COLLECTOR (runs on schedule)
   Pull metrics via upload-post analytics API
   Save to `metrics` table

8. FEEDBACK ANALYZER (runs weekly)
   Identify top performers by engagement_rate
   Update RAG-of-winners index
   Update bandit arm rewards
   Analyze comment sentiment
   Generate insights summary
```

---

## Agent Implementation Patterns

All agents use the OpenAI Python SDK with structured outputs. Each agent is a function, not a class. Use `response_format` for typed JSON output.

### Strategist Agent (`agents/strategist.py`)

```python
# Pattern — not exact code, but the structure to follow

STRATEGIST_SYSTEM_PROMPT = """
You are a social media strategist for {product_name}.

PRODUCT: {product_description}
TARGET AUDIENCE: {target_audience}
BRAND VOICE: {brand_voice}

CURRENT TRENDS:
{formatted_trends}

TOP PERFORMING PAST CONTENT (learn from these):
{formatted_winners}

BANDIT RECOMMENDATIONS (these have worked well recently):
{formatted_bandit_picks}

Your job: decide what content to create next. Consider:
- What's trending that we can tie into our product
- What content types are performing best on this platform
- What hooks/angles haven't been tried recently
- The target audience's pain points and interests
- Platform-specific norms (TikTok = entertainment-first, LinkedIn = value-first, etc.)

Return your decision as structured JSON.
"""

# Output schema (Pydantic model, passed as response_format)
class ContentPlan(BaseModel):
    platform: str           # "tiktok", "instagram", etc.
    content_type: str       # "video", "image", "carousel", "text", "thread"
    topic: str              # What the post is about
    angle: str              # The specific take/angle
    hook_style: str         # "question", "bold_claim", "story", "statistic", "pain_point"
    tone: str               # "funny", "educational", "inspirational", "relatable"
    trend_tie_in: str | None  # Which trend this connects to, if any
    reasoning: str          # Why this combination was chosen (for logging)
```

### Writer Agent (`agents/writer.py`)

```python
WRITER_SYSTEM_PROMPT = """
You are a copywriter creating a {content_type} for {platform}.

PRODUCT: {product_name} — {product_description}
BRAND VOICE: {brand_voice}
TARGET AUDIENCE: {target_audience}

CONTENT PLAN:
- Topic: {topic}
- Angle: {angle}
- Hook style: {hook_style}
- Tone: {tone}
- Trend tie-in: {trend_tie_in}

TOP PERFORMING EXAMPLES ON THIS PLATFORM (emulate what works):
{winner_examples}

PLATFORM RULES:
{platform_rules}

Write the content now. The hook (first line) is THE most important part — it must
stop the scroll. Make every word earn its place. Be specific, not generic.
"""

# Platform-specific rules injected into the prompt
PLATFORM_RULES = {
    "tiktok": """
    - Caption max 2200 chars, but shorter is better (under 150 ideal)
    - If video: script should be 15-60 seconds spoken
    - Use 3-5 hashtags, mix popular + niche
    - Hook must work in first 1-2 seconds
    - Conversational, not polished — raw and authentic wins
    - Script format: write exactly what should be said, line by line
    """,
    "instagram": """
    - Caption can be longer (up to 2200 chars), front-load the hook
    - For Reels: same video rules as TikTok but slightly more polished
    - For Carousels: write 5-10 slide texts, each slide one clear point
    - Use 10-15 hashtags in a comment or end of caption
    - Include a clear CTA (save, share, follow, link in bio)
    """,
    "x": """
    - Max 280 characters for single posts
    - For threads: 3-7 tweets, first tweet is the hook
    - Use 1-3 hashtags max
    - Hot takes and contrarian opinions perform well
    - Retweet-worthy = useful, surprising, or emotionally resonant
    - No links in main post (costs $0.20 via API) — put links in reply
    """,
    "linkedin": """
    - Professional but not boring — personality wins
    - Optimal length: 1200-1500 characters
    - Line breaks between every 1-2 sentences (LinkedIn formatting)
    - Open with a personal story or bold statement
    - End with a question to drive comments
    - Use 3-5 hashtags
    - For carousels: create PDF-style slides with clear takeaways
    """,
    "youtube": """
    - Title: under 60 chars, curiosity-driven, include primary keyword
    - Description: first 2 lines visible, front-load CTA
    - Include #Shorts in description for Shorts
    - Video must be vertical (9:16) and under 3 minutes
    """,
    "bluesky": """
    - Max 300 graphemes (roughly 300 chars)
    - No hashtag culture yet — focus on substance
    - Community values authenticity and substance over engagement bait
    - Can include up to 4 images
    """,
    "threads": """
    - Max 500 characters
    - Conversational, casual tone
    - Can include images
    - Cross-posting from X works but adapt tone slightly
    """
}

class ContentDraft(BaseModel):
    caption: str
    hashtags: list[str]
    hook: str                      # The first line / opening
    script: str | None = None      # For video: the spoken script
    slide_texts: list[str] | None = None  # For carousels: text per slide
    cta: str | None = None         # Call to action
    alt_text: str | None = None    # Image alt text
    image_prompt: str | None = None      # Prompt for image generation
    image_prompts: list[str] | None = None  # For carousels: prompt per slide
    video_prompt: str | None = None      # Prompt for AI video generation
    video_style: str | None = None       # "talking_head", "b_roll", "text_overlay", "ai_generated"
```

### Analyzer Agent (`agents/analyzer.py`)

Runs weekly. Looks at all metrics since last analysis, identifies patterns, and produces actionable insights.

```python
class EngagementInsights(BaseModel):
    top_performing_topics: list[str]
    worst_performing_topics: list[str]
    best_hook_styles: list[str]
    best_content_types: dict[str, str]   # platform -> best type
    best_posting_times: dict[str, str]   # platform -> best time
    audience_sentiment_summary: str
    recommended_adjustments: list[str]
    raw_analysis: str
```

---

## Media Generation Details

### Image Generation (`media/images.py`)

```python
# Use OpenAI images API
# Models: "gpt-image-1.5" (default) or "gpt-image-2" (highest quality)
# Sizes: "1024x1024" (square), "1024x1536" (portrait/vertical), "1536x1024" (landscape)

# Platform-specific sizes:
PLATFORM_IMAGE_SPECS = {
    "tiktok":    {"size": "1024x1536", "aspect": "9:16"},  # Cover image
    "instagram": {"size": "1024x1024", "aspect": "1:1"},   # Feed post (square)
    "instagram_reel": {"size": "1024x1536", "aspect": "9:16"},
    "instagram_carousel": {"size": "1024x1024", "aspect": "1:1"},  # Each slide
    "x":         {"size": "1536x1024", "aspect": "16:9"},
    "linkedin":  {"size": "1536x1024", "aspect": "16:9"},
    "youtube":   {"size": "1024x1536", "aspect": "9:16"},  # Shorts thumbnail
    "bluesky":   {"size": "1024x1024", "aspect": "1:1"},
    "threads":   {"size": "1024x1024", "aspect": "1:1"},
}

# For carousels: generate each slide separately with slide_texts overlay
# Use Pillow to add text overlays if the image prompt alone isn't sufficient
```

### Video Generation (`media/video.py`)

Two paths for video creation:

**Path A: AI-Generated Video (for cinematic/b-roll content)**
```python
# Use fal.ai unified API
# Primary: Kling 3.0 ("fal-ai/kling-video/v3/text-to-video") — best value, ~$0.10/sec
# Fallback: Wan 2.6 ("fal-ai/wan/v2.6/text-to-video") — cheapest, ~$0.05/sec
# Premium: Veo 3.1 ("fal-ai/veo-3") — best quality, ~$0.15-0.50/sec

import fal_client

result = fal_client.subscribe(
    "fal-ai/kling-video/v3/text-to-video",
    arguments={
        "prompt": video_prompt,
        "duration": 5,              # seconds
        "aspect_ratio": "9:16",     # vertical for social
    }
)
video_url = result["video"]["url"]
# Download video, then overlay captions + add voiceover via MoviePy
```

**Path B: Assembled Video (for talking-head/text-overlay/slideshow content)**
```python
# 1. Generate voiceover via OpenAI TTS
#    client.audio.speech.create(model="tts-1-hd", voice="onyx", input=script)
#    Save as MP3, convert to WAV for processing
#
# 2. Get word-level timestamps via Whisper
#    whisper.transcribe(audio_path, word_timestamps=True)
#
# 3. Generate background images or use AI-generated visuals
#
# 4. Assemble with MoviePy:
#    - Background image/video as base
#    - Voiceover as audio track
#    - Word-by-word caption overlays timed to speech
#    - Export as 1080x1920 H.264 MP4
#
# Target specs for all platforms:
#   Resolution: 1080x1920 (9:16 vertical)
#   Codec: H.264
#   Bitrate: 8-12 Mbps
#   Audio: AAC 128kbps
#   FPS: 30
#   Max duration: 60s (TikTok/Reels), 180s (YouTube Shorts)
```

### Caption Overlay (`media/captions.py`)

TikTok-style animated word-by-word captions are essential for engagement. Use Whisper timestamps and MoviePy `TextClip` to render them.

```
- Font: Bold sans-serif (e.g., Impact, Montserrat-Bold)
- Size: ~60-80px
- Color: White with black outline/stroke
- Position: Center of screen, slightly below middle
- Animation: Each word appears on its timestamp, 2-3 words visible at once
- Highlight the current word with a different color (yellow or brand color)
```

---

## Posting Layer

### upload-post.com Integration (`posting/upload_post.py`)

Primary posting method. Handles TikTok, Instagram, YouTube, X, LinkedIn, Threads, Pinterest, Reddit, Bluesky through one API.

```python
from upload_post import UploadPostClient

client = UploadPostClient(api_key)

# Video post (TikTok + Instagram Reels + YouTube Shorts)
response = client.upload_video(
    video_path,
    title=caption,
    user=profile_username,
    platforms=["tiktok", "instagram", "youtube"],
    tiktokPrivacyLevel="PUBLIC_TO_EVERYONE",
    # first_comment="Link in bio 👆"  # Optional first comment
)

# Photo post (Instagram + X + LinkedIn)
response = client.upload_photo(
    [image_path],
    title=caption,
    user=profile_username,
    platforms=["instagram", "x", "linkedin"],
)

# Text post (X + LinkedIn + Bluesky + Threads)
response = client.upload_text(
    text=caption,
    user=profile_username,
    platforms=["x", "bluesky", "threads"],
)

# Carousel (Instagram)
response = client.upload_photo(
    [slide1_path, slide2_path, slide3_path],
    title=caption,
    user=profile_username,
    platforms=["instagram"],
)

# IMPORTANT: Store the `request_id` from every response — needed for analytics
```

### Analytics via upload-post.com (`analytics/collector.py`)

```python
# Get post analytics
# GET /api/uploadposts/post-analytics/{request_id}
# Returns: views, likes, comments, shares per platform

# Get total impressions
# GET /api/uploadposts/total-impressions/{profile_username}

# These endpoints return engagement data across all connected platforms.
# Poll periodically (every 6 hours) and store in `metrics` table.
# Compute engagement_rate = (likes + comments + shares + saves) / max(views, 1)
```

---

## Trend Monitoring

### TikTok Creative Center (`trends/tiktok.py`)

The TikTok Creative Center (ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag) shows trending hashtags, songs, creators, and videos. It requires no login and no API key.

```python
# Scrape the Creative Center trending page
# Filter by country (US), period (7 days)
# Extract: trending hashtags, their view counts, growth rates
# Store in `trends` table with source="tiktok"
#
# Use httpx + BeautifulSoup or playwright if JS-rendered
# Run twice daily via scheduler
#
# The data format to extract:
# - Hashtag name
# - View count
# - Growth rate (trending up/down)
# - Related hashtags
```

### Google Trends (`trends/google_trends.py`)

```python
# Use pytrends library or scrape Google Trends
# Search for topics related to the product's niche
# E.g., for a job app: "internship", "job search", "resume tips"
# Extract: trending searches, related queries, interest over time
```

### Aggregator (`trends/aggregator.py`)

Merges all trend sources, deduplicates, scores by relevance to the active product, and returns a ranked list that the Strategist agent uses.

```python
# Score each trend by:
# 1. Recency (how fresh)
# 2. Growth rate (rising trends > steady ones)
# 3. Relevance to product (use OpenAI to score relevance 0-1)
# 4. Platform match (TikTok trends for TikTok content, etc.)
```

---

## Self-Improving Feedback Loop

### RAG-of-Winners (`learning/winners.py`)

The core learning mechanism. Maintains an index of your best-performing posts and retrieves them as few-shot examples when generating new content.

```python
# After metrics collection:
# 1. Rank all posts by engagement_rate (per platform, per content_type)
# 2. Top 20% become "winners"
# 3. Generate embeddings for each winner's caption + hook using OpenAI embeddings API
#    client.embeddings.create(model="text-embedding-3-small", input=text)
# 4. Store embedding in `winners` table
#
# When generating new content:
# 1. Embed the ContentPlan topic + angle
# 2. Find top 3-5 most similar winners via cosine similarity
# 3. Include their captions/hooks as examples in the Writer agent prompt
#
# This means: content that performed well gets used as a template for future content.
# Over time, the system converges toward what actually works with your audience.
```

### Contextual Bandit (`learning/bandit.py`)

Uses Thompson Sampling to optimize discrete choices. Each "arm" is a choice the system can make.

```python
# Bandit arm types:
# - hook_style: "question", "bold_claim", "story", "statistic", "pain_point", "before_after"
# - content_type: "video", "image", "carousel", "text"
# - post_time: "morning", "midday", "afternoon", "evening"
# - tone: "funny", "educational", "inspirational", "relatable", "controversial"
#
# Thompson Sampling implementation:
# For each arm, maintain alpha and beta parameters (Beta distribution)
# On selection: sample from Beta(alpha, beta) for each arm, pick highest
# On reward: alpha += reward, beta += (1 - reward)
# Where reward = normalized engagement rate (0 to 1, relative to account baseline)
#
# The bandit learns which hook styles, content types, posting times, and tones
# produce the best engagement FOR YOUR SPECIFIC AUDIENCE on EACH PLATFORM.
```

### Feedback Loop Orchestrator (`learning/feedback.py`)

Runs weekly. Ties everything together.

```python
# 1. Collect all metrics for posts from the past week
# 2. Compute per-account baseline engagement rate
# 3. Normalize each post's engagement: reward = post_rate / baseline_rate (capped at 1.0)
# 4. Update bandit arms with rewards
# 5. Identify new winners, embed them, add to winners index
# 6. Run the Analyzer agent to generate insights
# 7. Remove stale winners (older than 90 days or below current top-20% threshold)
# 8. Log everything to a weekly report
```

---

## CLI Commands (`cli.py`)

Build with Typer. Use Rich for formatting.

```
autonomark init                         # Initialize database, create config dirs
autonomark product add                  # Interactive: create a new product config
autonomark product list                 # List all products
autonomark product activate <id>        # Set active product

autonomark generate [--product <id>]    # Generate content for all platforms
autonomark generate --platform tiktok   # Generate for one platform only

autonomark queue                        # Show all pending content (draft status)
autonomark preview <content_id>         # Show content details + media paths
autonomark approve <content_id>         # Approve for posting
autonomark approve --all                # Approve all drafts
autonomark reject <content_id> --feedback "too generic, needs more specificity"

autonomark post [--now]                 # Post all approved content (or queue for optimal time)
autonomark post <content_id>            # Post specific content immediately

autonomark analytics [--days 7]         # Show recent post performance
autonomark trends                       # Show current trending topics
autonomark insights                     # Show latest analyzer insights

autonomark run                          # Start the autonomous scheduler (long-running)
autonomark run --daemon                 # Run in background

autonomark status                       # Show system status, upcoming posts, health checks
```

---

## Build Order (execute these phases sequentially)

### Phase 1: Foundation
1. Project scaffolding (`pyproject.toml`, directory structure, `__init__.py` files)
2. Config system (`config.py` — Pydantic models, YAML loading, env var loading)
3. Database (`db.py` — schema creation, migration, helper functions)
4. Basic CLI skeleton (`cli.py` — `init`, `product add/list`, `status`)
5. Create the example product config

**Checkpoint: `autonomark init` creates the database. `autonomark product add` creates a product config.**

### Phase 2: Content Generation (Text + Images)
1. Writer agent (`agents/writer.py` — generates captions, hashtags, hooks)
2. Image generation (`media/images.py` — OpenAI image API, Pillow resizing)
3. Strategist agent (`agents/strategist.py` — decides what to post, initially without trends/bandit)
4. Media orchestration (`agents/media.py` — routes to correct generator)
5. Wire into CLI: `autonomark generate` creates content, saves to DB
6. Add `queue`, `preview`, `approve`, `reject` commands

**Checkpoint: `autonomark generate` produces image posts with captions for all platforms. `autonomark queue` shows them. `autonomark approve <id>` marks them ready.**

### Phase 3: Posting
1. upload-post.com integration (`posting/upload_post.py`)
2. Posting manager (`posting/manager.py` — routes content to poster)
3. Wire into CLI: `autonomark post` sends approved content to platforms
4. Save platform_post_id and request_id to DB

**Checkpoint: Content flows from generation → approval → live on social media.**

### Phase 4: Video Generation
1. TTS module (`media/tts.py` — OpenAI TTS or ElevenLabs)
2. fal.ai video generation (`media/video.py` — Kling/Wan/Veo via fal_client)
3. Caption overlay system (`media/captions.py` — Whisper timestamps + MoviePy)
4. Video assembly pipeline (MoviePy composition: background + voiceover + captions)
5. Update strategist and writer to produce video ContentPlans and scripts
6. Carousel generation (multi-image with Pillow text overlay)

**Checkpoint: `autonomark generate` can produce videos, carousels, and images. Videos have voiceover and animated captions.**

### Phase 5: Trends & Analytics
1. TikTok Creative Center scraper (`trends/tiktok.py`)
2. Google Trends integration (`trends/google_trends.py`)
3. Trend aggregator (`trends/aggregator.py`)
4. Analytics collector (`analytics/collector.py` — upload-post analytics API)
5. Wire trends into Strategist prompt
6. Wire analytics into CLI: `autonomark analytics`, `autonomark trends`

**Checkpoint: Strategist uses real trend data. `autonomark analytics` shows engagement numbers.**

### Phase 6: Self-Improvement
1. Winners indexing (`learning/winners.py` — embeddings + similarity search)
2. Contextual bandit (`learning/bandit.py` — Thompson Sampling)
3. Feedback loop orchestrator (`learning/feedback.py`)
4. Analyzer agent (`agents/analyzer.py` — generates insights from metrics)
5. Comment sentiment analysis (`analytics/sentiment.py`)
6. Wire RAG-of-winners into Writer prompt
7. Wire bandit recommendations into Strategist
8. Add `autonomark insights` command

**Checkpoint: System improves over time. Winners inform new content. Bandit optimizes choices.**

### Phase 7: Automation
1. APScheduler engine (`scheduler/engine.py`)
2. Define all scheduled jobs (generation, posting, analytics, trends, feedback)
3. Implement `autonomark run` as a long-running process
4. Add jitter to posting times (±15 min randomization to avoid bot patterns)
5. Error handling, retries, and health monitoring
6. Implement `autonomark status` showing upcoming schedule

**Checkpoint: `autonomark run` is fully autonomous. Content generated, approved (or auto-approved), posted, metrics collected, system learns.**

---

## Important Implementation Notes

### Error Handling
- All API calls wrapped in try/except with exponential backoff (3 retries)
- Failed posts set content status to "failed" with error message
- Never crash the scheduler — log errors and continue
- Media generation failures should fall back to simpler content types (video fails → try image)

### Rate Limit Awareness
- upload-post.com: respect their rate limits (check response headers)
- OpenAI: use exponential backoff on 429s
- fal.ai: queue-based, will return result when ready
- Space out API calls — never burst. Add `asyncio.sleep(1)` between sequential calls

### Media File Management
- All generated media saved to `data/media/{product_id}/{date}/{content_id}/`
- Clean up media older than 30 days to prevent disk bloat
- Use descriptive filenames: `{content_id}_{platform}_{type}.{ext}`

### Posting Safety
- Add ±5-15 minutes random jitter to all scheduled posting times
- Never post identical content to multiple platforms — always adapt captions and hashtags
- Maximum posts per platform per day enforced in scheduler (from config)
- Log every post with full content for auditability

### Content Quality Guardrails
- The Writer agent prompt should include explicit anti-slop instructions:
  "Never use these phrases: 'In today's digital age', 'Game-changer', 'Revolutionary',
  'Unlock your potential', 'Take your X to the next level'. Be specific and concrete,
  never vague and generic."
- Always include the product name naturally — never forced
- Hooks must be under 10 words and create curiosity or emotion

### X/Twitter Link Strategy
- NEVER put URLs in the main post body (costs $0.20 per post via API)
- Instead: post the text/image first, then reply with the link
- The upload-post.com `first_comment` feature may handle this
