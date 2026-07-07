# Content Templates Build — Architecture Contract (July 2026)

> Source of truth for the "clip economy" build: 6 new content templates + shared
> caption engine + EDL renderer + web clip/caption editor. Written from deep
> research (8 reports, synthesized in the session scratchpad) + full codebase
> recon. Every build agent MUST read this file first and conform to the
> contracts below. Research reports live at
> `/private/tmp/claude-501/-Users-sanjithshanmugavel-Documents-Mark/6d20a087-7bd8-492c-ad4b-e4858f012cb3/scratchpad/`
> (`synthesis.md` + `report-*.json`) — read the one for your system.

## Environment facts

- Python: `/opt/anaconda3/bin/python3` (3.12) — `mark` is editable-installed here.
  Run tests with `/opt/anaconda3/bin/python3 -m pytest tests/ -x -q`.
- Installed: ffmpeg 8.1 + ffprobe (`/opt/homebrew/bin`), yt-dlp (`/opt/anaconda3/bin/yt-dlp`),
  `faster-whisper` (python), Pillow, numpy, httpx, fastapi. NOT installed: moviepy,
  fal_client, whisper_timestamped, torch/whisperx, cv2, scenedetect, pydub.
- No `.env` → **no live API keys right now**. `App.is_mock(provider)` gates real
  calls; everything must work offline in mock mode. macOS `say -o out.aiff` is
  available for REAL speech audio in tests (convert with ffmpeg) — use it to test
  alignment/captions without API keys.
- Test video sources: `ffmpeg -f lavfi -i testsrc=...`/`color=...` and
  `ffmpeg -f lavfi -i sine=...` for audio.

## Codebase integration points (from recon)

- `App` (`src/mark/app.py`): carries `settings`, `paths`, `keys`, `conn`,
  `force_mock`; `App.is_mock("openai"|"fal"|...)` decides real-vs-mock.
- Strategy model + registry: `src/mark/strategies.py` (`Strategy`, `STRATEGIES`,
  `register()` at :598). Media dispatch on `strategy.id`:
  `src/mark/agents/media.py:produce_media` (:29). Media output dir:
  `agents/media.media_dir_for(app, product_id, content_id)` → `data/media/{pid}/{date}/{cid}/`.
- Video today: `src/mark/media/video.py` — fal via `fal_client.subscribe`, ffmpeg
  assembly `_assemble` (:262), concat pattern `_concat_clips` (:216). Captions
  today: `src/mark/media/captions.py` — `word_timestamps()` (:24) and
  `build_ass()` (:117) burned via ffmpeg `subtitles=` filter. `chatdrama.py` is
  the model for deterministic timed-segment assembly.
- Characters: `src/mark/characters.py` + `config/characters/*.yaml` + DB table;
  identity today = one reference image → `images.edit(input_fidelity="high")` →
  i2v first-frame lock. `ensure_reference_image()` (:166), `scene_prompt()` (:188).
- DB: raw SQLite, `src/mark/db.py`. New columns → append to BOTH the `SCHEMA`
  string and `MIGRATIONS` list. New tables → `CREATE TABLE IF NOT EXISTS` in `SCHEMA`.
- Discovery pattern to clone: `src/mark/humor_radar.py` (fetchers → LLM judge →
  velocity/stage → `refresh()`/`radar()`/`draft_*()` → scheduler hook in
  `scheduler/engine.py:job_trends_fast` :194).
- Web: FastAPI (`src/mark/web/api.py`, all routes in `build_router(rt)`) + React/
  Vite/TS SPA in `web/` (build → `src/mark/web/static/`). Media served at `/media`.
  Studio page (`web/src/pages/Studio.tsx`) has the approval drawer + `<video>` player.
  `PATCH /api/content/{id}` merges draft fields; `POST /api/content/{id}/regenerate-media`
  re-runs media. Long jobs: return `{job_id}`, progress over SSE `/api/events`
  (see `web/runtime.py` job queue).
- Costs: log every external call via the existing cost logger
  (see `log_external_cost` usage in `media/video.py`).

## Resolved architecture decisions (do not relitigate)

1. **Rendering = ffmpeg filtergraphs + libass ASS burn-in.** No MoviePy anywhere new.
2. **Caption timing = forced alignment of the KNOWN script** when we scripted the
   audio; ASR only for unscripted (downloaded) audio. Implementation: primary =
   `faster-whisper` (already installed) `word_timestamps=True`, then snap
   transcribed words onto the known script tokens (fuzzy monotonic alignment);
   optional `whisperx.align()` upgrade if importable; OpenAI `whisper-1`
   verbose_json fallback when local model unavailable; even-spacing last resort
   (mock mode).
3. **One EDL JSON is THE assembly representation** for every video template.
   Templates emit an EDL; `media/render.py` executes it; the web editor edits it.
   The EDL (`edit.json`) + a **captionless master video** are persisted per
   content row in its media dir; final export burns captions.
4. **Compliance invariant in the renderer:** any EDL with `ai_generated: true`
   gets a small burned "AI-generated" text disclosure during t=0–5s. Not
   configurable off. Posting already sets platform AIGC flags (`posting/manager.py:128`).
5. **Human-in-the-loop lanes:** livestream clips and paid-campaign submissions
   are NEVER auto-approved/auto-posted (`Strategy.never_auto_approve=True` +
   campaign submission is always a human click in the web UI). Everything else
   uses the normal approval gate.
6. **Banned:** FaceFusion/inswapper (license), MoviePy TextClip, OpenTimelineIO,
   auto-downloading copyrighted movies/shows. Recap template = AI-generated
   "fake movie" by default + a clip-intelligence engine that operates on
   user-supplied local video files only.

## Contract 1 — EDL schema (`src/mark/media/edl.py`)

Pydantic models + `load(path) / save(edl, path)` + `edl_path_for(out_dir) -> out_dir/"edit.json"`.

```jsonc
{
  "version": 1,
  "ai_generated": true,              // triggers disclosure invariant
  "canvas": {"width": 1080, "height": 1920, "fps": 30, "background": "#000000"},
  "clips": [                          // visual timeline, ordered by `order`
    {"id": "c1", "src": "clips/beat1.mp4",   // path relative to the EDL's dir, or absolute under data/
     "in": 0.0, "out": 5.2,           // source trim, seconds
     "order": 0,
     "fit": "cover",                  // cover | contain | window
     "window": {"x": 0, "y": 420, "w": 1080, "h": 1080},  // when fit=window (letterbox composer)
     "speed": 1.0,                    // 0.85–1.25 typical
     "mute": true,
     "transition": {"type": "crossfade", "duration": 0.4}  // into the NEXT clip; optional
    }
  ],
  "overlays": [                       // PNG/text overlays on master timeline
    {"kind": "png", "src": "quote.png", "t0": 0, "t1": 9.5, "x": 0, "y": 96},
    {"kind": "text", "text": "hook line", "t0": 0, "t1": 2.5, "y_frac": 0.12, "style": "hook"}
  ],
  "captions": {
    "mode": "karaoke",                // karaoke | static_scene | seam_band | none
    "style": "hormozi",               // preset id from config/caption_styles/
    "words": [{"w": "never", "t0": 0.00, "t1": 0.32, "emphasize": false, "emoji": null}],
    "events": [{"text": "he waited all day", "t0": 0.0, "t1": 4.1}]   // static_scene mode
  },
  "audio": [
    {"src": "vo.mp3", "kind": "voiceover", "gain_db": 0, "t0": 0.0},
    {"src": "music.mp3", "kind": "music", "gain_db": -6, "duck_db": -12},  // ducked under voiceover via sidechaincompress
    {"src": null, "kind": "original", "gain_db": 0}    // keep clip's own audio (mute=false clips)
  ]
}
```

Timing rule: `captions`, `overlays`, and `audio` are anchored to the MASTER
(voiceover) timeline and are invariant under visual clip reorder/trim. Helper:
`total_duration(edl)`, `visual_duration(edl)`.

## Contract 2 — Caption engine (`src/mark/media/align.py`, `src/mark/media/ass_captions.py`)

- `align.word_timestamps(app, audio_path, script=None, *, llm=None) -> list[Word]`
  where `Word = (text, start, end)` (keep the existing tuple shape from
  `captions.py`). `script` given → forced alignment per decision 2. Must degrade
  gracefully offline (even spacing weighted by word length).
- `align.verify_sync(app, video_path, words) -> dict` — extract audio, re-align,
  return `{"median_offset_ms": .., "max_offset_ms": .., "passed": median<80 and max<200}`.
- `ass_captions.build_ass(edl_captions: dict, canvas: dict, out_path: Path) -> Path`
  — renders any of the three modes from the EDL captions block.
  - karaoke: 2–3-word chunks, one Dialogue event per word-state, active word
    scaled `\t(0,120,\fscx128\fscy128)\t(120,220,\fscx100\fscy100)` + colored
    (`\1c` — **BGR order!**), `\pos(540,1230)` default (platform-safe).
  - static_scene: one centered event per `events[]` entry (animal-story mode).
  - seam_band: karaoke placed in the seam between stacked videos (y from style).
- Style presets: `config/caption_styles/{hormozi,clean,meme}.yaml` — font, size,
  colors (primary/highlight/outline), outline width, position, chunk size,
  uppercase flag. Loaded with safe defaults if file missing.
- Fonts vendored at `src/mark/assets/fonts/` (OFL only: Montserrat-ExtraBold,
  Anton, Bebas Neue). Burn with `ass=...:fontsdir=<assets/fonts>`.
- Back-compat: `media/captions.py` keeps its public functions but delegates to
  the new modules (video.py imports keep working until migrated).

## Contract 3 — Renderer (`src/mark/media/render.py`)

- `render_edl(app, edl, edl_dir, out_path, *, proxy=False) -> Path`
  - Builds ONE ffmpeg command: per-clip `trim/setpts/scale/crop` (or pad/window
    placement), `xfade` transitions, overlay PNGs/text (drawtext), audio graph
    (`amix` + `sidechaincompress` ducking), ASS burn (skip when `proxy`),
    disclosure invariant (decision 4), `-pix_fmt yuv420p -movflags +faststart`,
    1080x1920 H.264 CRF 18 (proxy: 480p ultrafast CRF 30).
  - Subprocess list-args only; validate all `src` paths resolve under
    `app.paths.data_dir` or the EDL dir (path-traversal guard — the web editor
    POSTs EDLs).
- `render.letterbox_quote(...)`-style helpers may exist, but the letterbox
  composer is just `fit: window` + a PNG overlay — no separate pipeline.
- Every template's produce step: write assets + `edit.json` into the content
  media dir via edl.save, render master (captionless, `proxy=False, captions
  skipped`) → `master.mp4`, then final with captions → `{cid}_{platform}_video.mp4`,
  and returns media_paths like today's `produce_video`.

## Contract 4 — Sourcing layer (`src/mark/sourcing/`)

- `stock.py`: Pexels + Pixabay video search/download.
  `search_videos(app, query, *, orientation="portrait", per_page=15, provider="pexels")`,
  `download_video(app, item) -> Path` cached at `data/assets/stock/{provider}/{id}.mp4`.
  Keys: `PEXELS_API_KEY`, `PIXABAY_API_KEY` (mock mode: return deterministic
  testsrc-generated local clips so pipelines run offline).
- `ytdlp.py`: `download(url, out_dir, *, fmt="mp4", max_height=1080) -> Path` —
  subprocess wrapper around the installed `yt-dlp` binary, 2 retries, clear
  error including version-update hint. Policy note in docstring: Twitch clips
  under campaign permission / CC or own content only.
- `twitch.py`: Helix client — app access token via client-credentials
  (`TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET`), `get_streams(logins|game, first)`,
  `get_clips(broadcaster_id, started_at, first)` with pagination; offline mocks.
- All external hits logged via `db.log_activity` and costs (Apify later) via cost logger.

## Contract 5 — Template modules (`src/mark/templates/`)

Each template = ONE self-contained module exposing:
- `STRATEGY: Strategy` (or `STRATEGIES: list[Strategy]`) — new ids:
  `ai-ambassador`, `animal-story`, `fake-movie-recap`, `motivational-letterbox`,
  `stream-clips`, `campaign-clips`.
- `produce(app, llm, product, content_id, plan, draft, out_dir, character=None) -> dict`
  returning `{"media_paths": [...]}` — same shape as `video.produce_video`.
- Optional `refresh(app, llm)` / `radar(app, llm)` for discovery templates
  (humor_radar pattern).
`src/mark/templates/__init__.py` calls `strategies.register([...])` for all and
exposes `PRODUCERS: dict[strategy_id, produce_fn]` + `DISCOVERY: dict[strategy_id, refresh_fn]`.
Central wiring (dispatch in `agents/media.py`, scheduler hooks, config, db
migrations) is done by the orchestrator, NOT by template agents — template
agents must not edit `strategies.py`, `agents/media.py`, `db.py`, `config.py`,
`pyproject.toml`, or `scheduler/engine.py`; put integration needs in a module
docstring section titled `INTEGRATION`.

## Contract 6 — Web editor

- New page `web/src/pages/Editor.tsx` reachable from Studio drawer ("Open in
  editor") + route `/editor/:contentId`.
- Backend: `GET /api/edit/{content_id}` (EDL + media urls + fonts + styles),
  `POST /api/edit/{content_id}` (save EDL, Pydantic-validated),
  `POST /api/edit/{content_id}/proxy` (fast 480p re-cut, job),
  `POST /api/edit/{content_id}/render` (final render, job → replaces content
  media, back to normal approve/post flow).
- Browser preview: `<video>` element + caption overlay DIV synced via rAF on
  `currentTime` binary-searching the words array — captions are NEVER burned in
  preview; fonts served from the same vendored files (`/api/fonts/...` or
  static). Waveform + caption timing drag: wavesurfer.js v7 + Regions (self-host
  the ESM, no CDN).
- Clip lane: simple draggable/trim UI (plain divs). All edits mutate the
  in-memory EDL; explicit save.

## Contract 7 — Sound-effects engine (`src/mark/media/sfx.py` + `src/mark/sfx_library.py`)

A shared SFX engine used BOTH by autonomous clip creation and the web editor.
Decoupled from templates: it operates on an EDL, appending `kind="sfx"` audio
tracks (already supported by `edl.AudioTrack`: `src`, `t0`, `gain_db`, `label`).
Templates do NOT place SFX themselves — they emit clean EDLs (optionally with
beat/scene markers in `strategy_context`), and the central produce path calls
the engine to augment the EDL.

- `sfx_library.py`: a curated, on-disk SFX library at `data/assets/sfx/{slug}.mp3`
  with a manifest `config/sfx_library.yaml` — each entry: `slug`, `name`,
  `category` (whoosh/impact/riser/ding/pop/boom/swoosh/glitch/suspense/…),
  `purpose` (when/why used in short-form: "scene transition", "punchline
  emphasis", "reveal/hook sting", "text pop", "tension build"), `tags`,
  `duration`, `gain_db` default, `source`/`license`. Downloader
  `ensure_library(app)` fetches from a permissively-licensed bulk source
  (research picks it — Pixabay SFX / Mixkit / freesound CC0) into the cache;
  mock/offline → synthesize placeholder tones with ffmpeg so the pipeline runs.
- `sfx.py`: `plan_sfx(app, llm, edl, context) -> list[SfxCue]` — an LLM (or, in
  mock, a deterministic rule engine) reads the EDL's cut points, caption/word
  timings, hook window, and beat markers, and decides which effects go where
  (transition whooshes on cuts, a sting on the hook, pops on caption keyword
  emphasis, a riser before a reveal). `apply_sfx(app, llm, edl, context) -> EDL`
  appends the chosen `kind="sfx"` tracks. Idempotent; respects a per-EDL SFX
  density cap so it never gets noisy.
- Editor exposes the library (`GET /api/sfx`) and lets the human add/remove/
  move SFX cues on the timeline (they become `kind="sfx"` tracks in the EDL).
- Integration (orchestrator does this, not template agents): call
  `sfx.apply_sfx` in the shared produce path after a template returns its EDL,
  gated by a config flag `media.sfx_enabled` (default true).

## Testing bar (every agent)

- Unit tests in `tests/` (pytest, mock mode). Follow existing test style
  (`tests/conftest.py` fixtures).
- REAL end-to-end artifact test where possible without API keys: use `say` for
  speech, lavfi for video, then actually render an MP4 and assert with ffprobe
  (duration, streams, resolution); extract a frame with ffmpeg and eyeball it
  (agents: use the Read tool on the extracted PNG to VISUALLY verify — captions
  visible, layout correct). Do not claim success without having looked at output.
- `/opt/anaconda3/bin/python3 -m pytest tests/ -x -q` must stay green.
