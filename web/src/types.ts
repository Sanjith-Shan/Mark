export interface Campaign {
  id: string;
  name: string;
  description: string;
  target_audience: string;
  brand_voice: string;
  website_url: string | null;
  platforms: string[];
  posting_cadence: Record<string, number>;
  platform_options: Record<string, Record<string, string>>;
  /** "product" | "entertainment" — entertainment campaigns market the content itself */
  kind?: string | null;
  /** "clean" | "standard" | "edgy" (platform caps still apply) */
  content_rating?: string | null;
  /** per-campaign upload-post profile (multi-account posting) */
  upload_profile?: string | null;
  /** per-campaign trend radar sources */
  trend_sources?: { subreddits?: string[]; keywords?: string[] } | null;
  active: number;
  archived?: number;
  created_at: string;
  // overview extras
  counts?: Record<string, number>;
  posts_7d?: number;
  avg_engagement_7d?: number;
  views_7d?: number;
  spend_usd?: number;
}

export interface MediaItem {
  url: string;
  kind: "image" | "video";
  name: string;
}

export interface Draft {
  caption?: string;
  hashtags?: string[];
  hook?: string;
  script?: string | null;
  slide_texts?: string[] | null;
  cta?: string | null;
  alt_text?: string | null;
  image_prompt?: string | null;
  image_prompts?: string[] | null;
  video_prompt?: string | null;
  video_style?: string | null;
}

export interface Content {
  id: number;
  product_id: string;
  platform: string;
  content_type: string;
  caption: string | null;
  hashtags: string[];
  hook: string | null;
  media_paths: string[];
  media: MediaItem[];
  strategy_context: {
    topic?: string;
    angle?: string;
    hook_style?: string;
    tone?: string;
    trend_tie_in?: string | null;
    reasoning?: string;
    novelty_max_sim?: number;
    strategy?: string;
    strategy_name?: string;
    episode?: number | null;
    emotional_target?: string;
    humor_mechanism?: string | null;
    humor_persona?: string | null;
    character_id?: number | null;
    character?: string | null;
    forced_trend?: string | null;
    /** "holdout" = random-policy control group post (proves learning lift) */
    policy?: string | null;
  };
  draft: Draft;
  status: string;
  rejection_feedback: string | null;
  error: string | null;
  scheduled_at: string | null;
  /** Trend content TTL (UTC) — auto-rejects past this time. */
  expires_at?: string | null;
  created_at: string;
  approved_at: string | null;
  posted_at: string | null;
  posts?: PostRecord[];
}

export interface PostRecord {
  id: number;
  platform: string;
  platform_post_id: string | null;
  request_id: string | null;
  posted_at: string;
  latest_metric?: Metric | null;
  comments?: CommentRow[];
}

export interface Metric {
  views: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  clicks: number;
  engagement_rate: number;
  collected_at: string;
}

export interface CommentRow {
  id: number;
  post_id: number;
  comment_text: string;
  author: string | null;
  platform: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  post_platform?: string;
  content_id?: number;
  content_hook?: string;
  product_id?: string;
}

export interface ReplyRow {
  id: number;
  comment_id: number;
  post_id: number;
  content_id: number | null;
  product_id: string;
  platform: string;
  reply_text: string;
  /** 1 = handle personally; backend leaves reply_text empty for these */
  sensitive: number;
  status: string; // "draft" | "approved" | "posted" | "skipped"
  created_at: string;
  // joined from comments/content
  comment_text: string;
  author: string | null;
  post_hook: string | null;
}

export interface Job {
  id: string;
  kind: string;
  label: string;
  product_id: string | null;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  result: unknown;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Activity {
  id: number;
  kind: string;
  message: string;
  product_id: string | null;
  content_id: number | null;
  level: string;
  created_at: string;
}

export interface Status {
  providers: Record<string, "live" | "mock">;
  force_mock: boolean;
  autopilot: { running: boolean; started_at: string | null };
  counts: Record<string, number>;
  spend_total_usd: number;
  spend_30d_usd: number;
  timezone: string;
}

export type TrendStage = "new" | "rising" | "mature" | "declining";

export interface Trend {
  source: string;
  topic: string;
  trend_score: number;
  /** may contain: safe (bool), sound_dependent (bool), relevance (number) */
  metadata: Record<string, unknown>;
  style_notes?: string | null;
  velocity?: number | null;
  stage?: TrendStage | null;
  collected_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  emotional_target: string;
  /** platform -> adaptation note ("" = native fit) */
  platforms: Record<string, string>;
  content_types: string[];
  humor_level: "none" | "light" | "full";
  uses_character: boolean;
  series_format: string | null;
  example_sketches: string[];
  mix_weight: number;
  never_auto_approve: boolean;
  /** per-campaign: on the selected campaign's allowlist (null allowlist = all) */
  enabled: boolean;
  /** count of content generated under this strategy for the campaign */
  usage?: number;
  /** next episode number, for series strategies */
  episode?: number | null;
}

export interface Character {
  id: number;
  product_id: string;
  name: string;
  role: string;
  persona: string;
  visual_desc: string;
  voice: string | null;
  catchphrases: string[];
  reference_image: string | null;
  reference_url: string | null;
  active: number;
  lore_state: Record<string, unknown>;
  created_at: string;
}

export interface SeriesPoint {
  day: string;
  platform: string;
  engagement: number;
  views: number;
  likes?: number;
  comments?: number;
  shares?: number;
}

export interface Insights {
  insights: {
    payload?: {
      top_performing_topics?: string[];
      worst_performing_topics?: string[];
      best_hook_styles?: string[];
      best_content_types?: Record<string, string>;
      best_posting_times?: Record<string, string>;
      audience_sentiment_summary?: string;
      recommended_adjustments?: string[];
      raw_analysis?: string;
    };
    created_at?: string;
  } | null;
  bandit: BanditArm[];
  winners: number;
  /** bandit-policy vs random-holdout comparison; null until both groups have data */
  holdout_lift?: HoldoutLift | null;
  campaign?: string;
}

export interface HoldoutLift {
  bandit_posts: number;
  bandit_avg_reward: number;
  holdout_posts: number;
  holdout_avg_reward: number;
  lift_pct: number;
}

export interface Experiment {
  id: number;
  name: string;
  hypothesis: string | null;
  campaign_ids: string[];
  metric: string;
  status: string; // "running" | "concluded"
  conclusion: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface ExperimentVariant {
  campaign_id: string;
  campaign_name: string;
  posts: number;
  avg_engagement: number;
  views: number;
  likes: number;
  avg_reward: number | null;
  rewarded_posts: number;
}

export interface ExperimentReport extends Experiment {
  variants: ExperimentVariant[];
  leader: string | null;
}

export interface BanditArm {
  arm_type: string;
  arm_value: string;
  platform: string;
  pulls: number;
  avg_reward: number;
  alpha: number;
  beta_param: number;
}

export const PLATFORM_COLORS: Record<string, string> = {
  tiktok: "#22d3ee",
  instagram: "#f472b6",
  x: "#94a3b8",
  linkedin: "#60a5fa",
  youtube: "#f87171",
  bluesky: "#38bdf8",
  threads: "#c084fc",
  reddit: "#fb923c",
  pinterest: "#fb7185",
};

export const ALL_PLATFORMS = Object.keys(PLATFORM_COLORS);

export const PLATFORM_LABELS: Record<string, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
  x: "X",
  linkedin: "LinkedIn",
  youtube: "YouTube",
  bluesky: "Bluesky",
  threads: "Threads",
  reddit: "Reddit",
  pinterest: "Pinterest",
};

/* ------------------------------------------------------------------ *
 * EDL — the edit decision list the clip/caption editor reads and writes.
 * Mirrors src/mark/media/edl.py (Pydantic). Clips use the "in" alias.
 * ------------------------------------------------------------------ */
export interface EdlCanvas {
  width: number;
  height: number;
  fps: number;
  background: string;
}
export interface EdlWindow { x: number; y: number; w: number; h: number; }
export interface EdlTransition { type: "crossfade"; duration: number; }
export interface EdlClip {
  id: string;
  src: string;
  in: number;
  out: number;
  order: number;
  fit: "cover" | "contain" | "window";
  window?: EdlWindow | null;
  speed: number;
  mute: boolean;
  transition?: EdlTransition | null;
}
export interface EdlOverlay {
  kind: "png" | "text";
  src?: string | null;
  text?: string | null;
  t0: number;
  t1: number;
  x?: number | null;
  y?: number | null;
  y_frac?: number | null;
  style?: string | null;
}
export interface EdlCaptionWord {
  w: string;
  t0: number;
  t1: number;
  emphasize?: boolean;
  emoji?: string | null;
}
export interface EdlCaptionEvent { text: string; t0: number; t1: number; }
export interface EdlCaptions {
  mode: "karaoke" | "static_scene" | "seam_band" | "none";
  style: string;
  words: EdlCaptionWord[];
  events: EdlCaptionEvent[];
}
export interface EdlAudioTrack {
  src?: string | null;
  kind: "voiceover" | "music" | "original" | "sfx";
  gain_db: number;
  duck_db?: number | null;
  t0: number;
  label?: string | null;
}
export interface Edl {
  version: number;
  ai_generated: boolean;
  canvas: EdlCanvas;
  clips: EdlClip[];
  overlays: EdlOverlay[];
  captions: EdlCaptions;
  audio: EdlAudioTrack[];
}

/** A caption style preset (config/caption_styles/*.yaml) as the editor sees it. */
export interface CaptionStyle {
  id: string;
  font?: string;
  font_size?: number;
  primary_color?: string;    // ASS &HAABBGGRR (BGR!)
  highlight_color?: string;
  outline_color?: string;
  outline?: number;
  uppercase?: boolean;
  chunk_size?: number;
  y_frac?: number;
  seam_y_frac?: number;
  [k: string]: unknown;
}

export interface FontRef { family: string; url: string; file: string; }

export interface EditData {
  content_id: number;
  platform: string;
  content_type: string;
  status: string;
  edl: Edl;
  media_urls: { proxy: string | null; master: string | null; video: string | null };
  audio_url: string | null;
  styles: CaptionStyle[];
  fonts: FontRef[];
  sfx_available: boolean;
}

/** One entry in the SFX library (Contract 7). Empty list = engine not shipped. */
export interface SfxItem {
  slug: string;
  name: string;
  category?: string | null;
  purpose?: string | null;
  duration?: number | null;
  gain_db?: number;
  src?: string | null;
  url?: string | null;
}

/** A copyworthy humor sighting from the humor radar (memes, GIFs, formats). */
export interface HumorFind {
  id: number;
  source: string;                 // "reddit" | "tenor" | "imgflip" | "kym"
  external_id: string;
  title: string;
  media_url: string | null;       // null = format/template signal, not postable
  media_type: string | null;      // "image" | "gif" | "video" | "template"
  permalink: string | null;
  author: string | null;
  community: string | null;
  raw_score: number;
  funny: number | null;           // judge: 0..1
  copyability: number | null;     // judge: 0..1
  safe: number;
  velocity: number | null;
  stage: string | null;
  metadata: Record<string, unknown>;
  collected_at: string;
  radar_score: number;            // blended ranking score
  post_now: boolean;              // fresh + rising + funny + postable
}
