"""SQLite database: schema, migrations, and query helpers.

Raw SQL, no ORM. Connections use WAL mode and ``sqlite3.Row`` for dict-like
access. JSON-encoded columns (hashtags, media_paths, ...) are round-tripped
through the helpers in this module so callers work with native Python types.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target_audience TEXT NOT NULL,
    brand_voice TEXT NOT NULL,
    website_url TEXT,
    platforms TEXT NOT NULL,
    posting_cadence TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    platform TEXT NOT NULL,
    content_type TEXT NOT NULL,
    caption TEXT,
    hashtags TEXT,
    hook TEXT,
    media_paths TEXT,
    media_urls TEXT,
    strategy_context TEXT,
    status TEXT DEFAULT 'draft',
    rejection_feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    posted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content(id),
    platform TEXT NOT NULL,
    platform_post_id TEXT,
    request_id TEXT,
    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    engagement_rate REAL DEFAULT 0.0,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    comment_text TEXT NOT NULL,
    author TEXT,
    platform TEXT,
    sentiment TEXT,
    sentiment_score REAL,
    analyzed_at TIMESTAMP,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content(id),
    platform TEXT NOT NULL,
    content_type TEXT NOT NULL,
    caption TEXT,
    hook TEXT,
    engagement_rate REAL NOT NULL,
    embedding BLOB,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bandit_arms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arm_type TEXT NOT NULL,
    arm_value TEXT NOT NULL,
    platform TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES products(id),
    pulls INTEGER DEFAULT 0,
    total_reward REAL DEFAULT 0.0,
    avg_reward REAL DEFAULT 0.0,
    alpha REAL DEFAULT 1.0,
    beta_param REAL DEFAULT 1.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(arm_type, arm_value, platform, product_id)
);

CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    topic TEXT NOT NULL,
    trend_score REAL,
    metadata TEXT,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Added by Mark (beyond the original spec):

-- Per-call cost/usage tracking so you can see cost-per-post & cost-per-engagement.
CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,            -- "openai", "fal", "elevenlabs", "upload_post"
    operation TEXT NOT NULL,           -- "chat", "image", "tts", "embedding", "video", ...
    model TEXT,
    content_id INTEGER,                -- optional link to the content this was spent on
    product_id TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    units REAL DEFAULT 0.0,            -- generic unit count (images, seconds, chars)
    usd REAL DEFAULT 0.0,
    mocked INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly analyzer output, kept so `mark insights` can show the latest.
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    payload TEXT NOT NULL,             -- JSON EngagementInsights
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Activity feed: everything the system does, for the web dashboard + audit trail.
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                -- "generate", "post", "approve", "learn", ...
    message TEXT NOT NULL,
    product_id TEXT,
    content_id INTEGER,
    level TEXT DEFAULT 'info',         -- "info", "success", "error"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Drafted replies to comments on our posts (first-hour replies are one of the
-- strongest distribution levers; drafts are one-tap approved, never auto-sent).
CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL REFERENCES comments(id),
    post_id INTEGER NOT NULL REFERENCES posts(id),
    content_id INTEGER,
    product_id TEXT,
    platform TEXT,
    reply_text TEXT NOT NULL,
    sensitive INTEGER DEFAULT 0,       -- visa/mental-health/desperation → human only
    status TEXT DEFAULT 'draft',       -- "draft", "approved", "posted", "skipped"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Persistent AI characters (brand ambassadors / mascots) fronting content.
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    name TEXT NOT NULL,
    role TEXT DEFAULT 'ambassador',    -- "ambassador", "mascot", "parody"
    persona TEXT NOT NULL,             -- lore + personality + how they talk
    visual_desc TEXT NOT NULL,         -- canonical appearance, prepended to media prompts
    voice TEXT,                        -- TTS voice id (falls back to global config)
    catchphrases TEXT,                 -- JSON array
    reference_image TEXT,              -- canonical character-sheet PNG path
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Humor radar: copyworthy humor sighted in the wild (memes, formats, GIFs).
-- One row per sighting (like trends) so velocity is computable; external_id
-- identifies the same item across sightings.
CREATE TABLE IF NOT EXISTS humor_finds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- "reddit", "tenor", "imgflip", "kym"
    external_id TEXT NOT NULL,         -- stable per item (post id / gif id / slug)
    title TEXT NOT NULL,               -- the joke text / meme name
    media_url TEXT,                    -- direct image/gif/video URL (nullable: formats)
    media_type TEXT,                   -- "image", "gif", "video", "template"
    permalink TEXT,                    -- canonical page (credit + provenance)
    author TEXT,                       -- creator handle for credit
    community TEXT,                    -- subreddit / tag / collection
    raw_score REAL DEFAULT 0.0,        -- source-native popularity (0-100 normalized)
    funny REAL,                        -- judge: how funny 0..1
    copyability REAL,                  -- judge: works standalone, easy to ride 0..1
    safe INTEGER DEFAULT 1,            -- 0 = nsfw/tragedy/unclear origin — never use
    velocity REAL,                     -- raw_score delta vs sightings 2-48h ago
    stage TEXT,                        -- "new", "rising", "mature", "declining"
    metadata TEXT,                     -- JSON extras (ups, template_id, …)
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_humor_ext ON humor_finds(external_id, collected_at);

-- Livestream clip radar: one row per clip sighting (humor_finds pattern).
CREATE TABLE IF NOT EXISTS stream_finds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- "twitch", "kick", "youtube"
    external_id TEXT NOT NULL,         -- clip id (stable per item)
    streamer TEXT,                     -- broadcaster login/handle
    title TEXT,
    clip_url TEXT,                     -- canonical clip page
    game TEXT,                         -- category/game name
    view_count INTEGER DEFAULT 0,
    vod_offset INTEGER,                -- seconds into the VOD (cluster signal)
    duration REAL,
    keep REAL,                         -- judge: clip-worthiness 0..1
    hook_text TEXT,                    -- judge: suggested first-frame hook
    safe INTEGER DEFAULT 1,            -- 0 = licensed music / unsafe — never use
    velocity REAL,                     -- view-count delta vs earlier sightings
    stage TEXT,                        -- "new", "rising", "mature", "declining"
    campaign_id INTEGER,               -- clip_campaigns.id when campaign-covered
    downloaded_path TEXT,              -- local mp4 once fetched
    metadata TEXT,                     -- JSON extras (crop rects, transcript, …)
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stream_ext ON stream_finds(external_id, collected_at);

-- Paid clipping campaigns discovered on ContentRewards/Whop etc. Joining,
-- posting and submitting are ALWAYS human actions (platform ToS) — this table
-- only powers discovery, ranking and tracking.
CREATE TABLE IF NOT EXISTS clip_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,            -- "contentrewards", "whop", ...
    external_id TEXT NOT NULL,         -- campaign id on the platform
    title TEXT,
    brand TEXT,
    url TEXT,
    category TEXT,                     -- niche: streamer/music/app/gambling/...
    cpm REAL,                          -- $ per 1000 views
    budget REAL,
    budget_used REAL,
    creators INTEGER,                  -- competition: joined creator count
    platforms TEXT,                    -- JSON: allowed posting platforms
    requirements TEXT,                 -- JSON: extracted hard rules from brief
    ev_score REAL,                     -- expected-value ranking score
    blocked INTEGER DEFAULT 0,         -- brand-safety block (gambling etc.)
    joined INTEGER DEFAULT 0,          -- user marked as joined (human action)
    status TEXT DEFAULT 'open',        -- "open", "ended", "paused"
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT                      -- JSON extras (raw listing payload)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_ext ON clip_campaigns(platform, external_id);

-- Small key/value store for learning bookkeeping (last decay pass, etc.).
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- A/B experiments: campaigns as variants (the summer test-lab mechanism).
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hypothesis TEXT,                   -- what difference between variants is being tested
    campaign_ids TEXT NOT NULL,        -- JSON array of product ids acting as variants
    metric TEXT DEFAULT 'engagement_rate',
    status TEXT DEFAULT 'running',     -- "running", "concluded"
    conclusion TEXT,                   -- filled when concluded
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- First-class series bookkeeping (franchise compounding is the growth asset).
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    strategy_id TEXT NOT NULL,         -- which strategy this series runs under
    premise TEXT NOT NULL,             -- the series concept, one line
    platform TEXT,                     -- home platform (NULL = cross-platform)
    episodes INTEGER DEFAULT 0,
    avg_engagement REAL DEFAULT 0.0,
    last_engagement TEXT,              -- JSON: trailing per-episode engagement rates
    status TEXT DEFAULT 'active',      -- "active", "retired"
    retired_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_content_product ON content(product_id);
CREATE INDEX IF NOT EXISTS idx_metrics_post ON metrics(post_id);
CREATE INDEX IF NOT EXISTS idx_posts_content ON posts(content_id);
CREATE INDEX IF NOT EXISTS idx_winners_platform ON winners(platform, content_type);
CREATE INDEX IF NOT EXISTS idx_trends_topic_time ON trends(topic, collected_at);
"""


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #
def connect(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Timestamps are handled as plain strings throughout, so we deliberately skip
    # PARSE_DECLTYPES (its default TIMESTAMP converter is deprecated in 3.12+).
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


# Columns added after the original schema shipped. init_db() checks PRAGMA
# table_info and ALTERs existing databases; fresh databases already have the
# columns from SCHEMA, so each entry is a no-op there.
MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, declaration)
    ("content", "draft", "TEXT"),              # full ContentDraft JSON — editable in the web app
    ("content", "error", "TEXT"),              # last media/posting error, surfaced in the UI
    ("content", "scheduled_at", "TIMESTAMP"),  # explicit user-chosen posting time
    ("products", "archived", "INTEGER DEFAULT 0"),
    ("products", "platform_options", "TEXT"),  # JSON: {"reddit": {"subreddit": ...}, "pinterest": {"board_id": ...}}
    ("comments", "author", "TEXT"),
    ("comments", "platform", "TEXT"),
    ("comments", "collected_at", "TIMESTAMP"),
    ("trends", "style_notes", "TEXT"),         # LLM analysis of the trend's format/style/audio
    ("products", "strategies", "TEXT"),        # JSON allowlist of strategy ids (null = all)
    ("trends", "velocity", "REAL"),            # score delta vs previous sighting (None = first sighting)
    ("trends", "stage", "TEXT"),               # lifecycle: "new", "rising", "mature", "declining"
    ("products", "specificity_bank", "TEXT"),  # JSON: concrete audience-life artifacts fueling humor
    ("products", "knowledge", "TEXT"),         # JSON: {pain_veins: [], fact_base: [], take_pool: []}
    ("characters", "lore_state", "TEXT"),      # JSON: running counters, NPCs, active arcs
    ("content", "expires_at", "TIMESTAMP"),    # trend content TTL — never post a dead meme
    # Evolution hardening: rewards are graded and applied exactly once per post.
    ("posts", "rewarded_at", "TIMESTAMP"),     # when the learning loop consumed this post
    ("posts", "reward", "REAL"),               # the graded reward it earned (0..1, 0.5 = baseline)
    ("content", "qa", "TEXT"),                 # JSON: judge/critique quality scores (autonomy gating)
    # Campaign generalization: content-as-the-business + per-campaign accounts.
    ("products", "kind", "TEXT DEFAULT 'product'"),  # "product" | "entertainment"
    ("products", "upload_profile", "TEXT"),    # per-campaign upload-post profile (multi-account)
    ("products", "content_rating", "TEXT"),    # "clean" | "standard" | "edgy" (platform caps still apply)
    ("products", "trend_sources", "TEXT"),     # JSON: {subreddits: [], keywords: []} per-campaign radar
    ("products", "strategy_catalog", "TEXT"),  # JSON: campaign-adapted strategy briefs (onboarding output)
    ("trends", "product_id", "TEXT"),          # campaign scoping — relevance is per-campaign
    # Clip-economy build: EDL sidecar per video content + character identity packs.
    ("content", "edl_path", "TEXT"),           # edit.json path — source of truth for the clip/caption editor
    ("characters", "identity", "TEXT"),        # JSON identity pack: lora_url, arcface path, voice_id, refs
]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, decl in MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    _data_migrations(conn)
    conn.commit()


def _data_migrations(conn: sqlite3.Connection) -> None:
    """One-time data migrations, tracked via PRAGMA user_version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        # v1: engagement_rate formula changed (shares/saves weighted 2x).
        # Recompute historical rows from their stored raw components so every
        # consumer (cascade baselines, winners, bandit rewards) compares rates
        # on ONE scale — mixing scales silently mislabels winners.
        conn.execute(
            "UPDATE metrics SET engagement_rate = ROUND("
            "  (likes + comments + 2.0 * shares + 2.0 * saves)"
            "  / MAX(views, 1), 5)")
        conn.execute("PRAGMA user_version = 1")


def get_meta(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)))
    conn.commit()


def log_activity(conn: sqlite3.Connection, kind: str, message: str,
                 product_id: Optional[str] = None, content_id: Optional[int] = None,
                 level: str = "info") -> None:
    """Append to the activity feed. Never raises — the feed is best-effort."""
    try:
        insert(conn, "activity", kind=kind, message=message,
               product_id=product_id, content_id=content_id, level=level)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def execute(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, tuple(params)).fetchall())


def query_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchone()


def insert(conn: sqlite3.Connection, table: str, **values: Any) -> int:
    """Insert a row; JSON-encode list/dict values automatically. Returns rowid."""
    cols = list(values.keys())
    encoded = [_encode(v) for v in values.values()]
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, encoded)
    conn.commit()
    return int(cur.lastrowid)


def update(conn: sqlite3.Connection, table: str, row_id: int, **values: Any) -> None:
    cols = list(values.keys())
    encoded = [_encode(v) for v in values.values()]
    assignments = ", ".join(f"{c} = ?" for c in cols)
    sql = f"UPDATE {table} SET {assignments} WHERE id = ?"
    conn.execute(sql, encoded + [row_id])
    conn.commit()


# --------------------------------------------------------------------------- #
# JSON column helpers
# --------------------------------------------------------------------------- #
def _encode(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def loads(value: Any, default: Any = None) -> Any:
    """Decode a JSON column, tolerating None / already-parsed values."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None
