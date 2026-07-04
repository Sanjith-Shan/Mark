# The 2025–2026 Toolchain for Funny / Viral AI Content

*Research report for Mark (autonomous marketing pipeline). Compiled July 2026. Prices are fal.ai or first-party API rates as of mid-2026 and drift monthly — treat as ±20%.*

---

## 1. Video models via API (fal.ai catalog + Sora 2)

### Quick reference table

| Model | fal endpoint (model ID) | Price | Max duration | Native audio | Resolution | Best for |
|---|---|---|---|---|---|---|
| **Kling 3.0 Pro** | `fal-ai/kling-video/o3/pro/text-to-video` | $0.112/s (no audio), $0.168/s (audio) | 3–15s, 1s increments | Yes (toggle) | 1080p (4K native claimed) | Multi-shot sequences, character consistency, best price/quality |
| **Kling V3 Standard** | `fal-ai/kling-video/o3/standard/text-to-video` | $0.084/s ($0.126 w/ audio) | 3–15s | Yes (toggle) | 1080p | Cheapest "good" tier; volume production |
| **Veo 3.1** | `fal-ai/veo3.1` (+ `/fast`, `/reference-to-video`) | fal: $0.20/s no audio, $0.40/s w/ audio (720/1080p); Google direct: $0.40/s standard, $0.15/s Fast, $0.10/s Fast-no-audio | 8s per clip (extendable by chaining) | **Yes — dialogue, SFX, ambience synced in one call** | up to 4K | Realistic talking characters, vlog-style comedy (Bigfoot format), best prompt adherence |
| **Sora 2** | `fal-ai/sora-2/text-to-video`, `/image-to-video` | ~$0.10/s (720p); OpenAI direct $0.10/s std / $0.05/s batch | 4/8/12s | Yes (dialogue + ambience, lip-synced) | 720p | Absurdist humor, meme-culture physics gags |
| **Sora 2 Pro** | `fal-ai/sora-2/text-to-video/pro` | $0.30/s (720p), $0.50/s (1080p) | up to 25s | Yes | 1080p | Longer absurd skits; **OpenAI API sunsets Sept 24, 2026 — don't build hard dependency** |
| **Seedance 2.0** | `bytedance/seedance-2.0/text-to-video` (+ `/fast`) | $0.30/s std, $0.24/s fast (audio included) | 4–15s | Yes (always on, no extra cost) | 720p on fal | Multi-modal reference input (9 images + 3 videos + 3 audio); viral on Reddit for comedy |
| **Wan 2.6** | `fal-ai/wan/v2.6/text-to-video` (+ `reference-to-video`, `image-to-video`) | ~$0.10/s 720p, $0.15/s 1080p (Wan 2.5 legacy: $0.05/s) | 5/10/15s | Yes (synced) | 720p/1080p | Budget tier with audio; R2V endpoint for character reference |
| **Hailuo 2.3 (MiniMax)** | `fal-ai/minimax/hailuo-2.3/pro/image-to-video` (+ standard, fast) | $0.49/clip Pro 1080p; $0.28/6s clip standard 768p; Fast ≈ −50% | 6–10s | No | 768p–1080p | **Exaggerated motion & physical comedy** — best-in-class motion directives, slapstick energy |

Sources: [fal pricing](https://fal.ai/pricing), [fal Seedance vs Kling](https://fal.ai/learn/tools/seedance-2-0-vs-kling-3-0), [DevTk AI video pricing 2026](https://devtk.ai/en/blog/ai-video-generation-pricing-2026/), [costgoat Sora sunset guide](https://costgoat.com/pricing/sora), [fal Hailuo 2.3 blog](https://blog.fal.ai/minimax-hailuo-2-3-is-now-available-on-fal/), [fal Sora 2 Pro](https://fal.ai/models/fal-ai/sora-2/text-to-video/pro), [Veo 3.1 on fal](https://fal.ai/models/fal-ai/veo3.1).

### Comedy/absurdism vs realism — which model when

- **Sora 2 is the comedy model.** Its training distribution is meme-culture-heavy; the viral formats built on it (bodycam comedies, absurd movie-scene substitutions, impossible-physics gags) rely on "realism + one absurd variable" prompts. Reviewers consistently note Sora produces the funniest output, sometimes unintentionally ([God of Prompt viral prompts](https://godofprompt.ai/blog/sora-2-viral-video-prompts/), [JZ Creates examples](https://jzcreates.com/blog/10-viral-sora-2-examples-breaking-the-internet/)). Caveat: **API sunset Sept 24, 2026** — build it as one interchangeable backend, not the foundation.
- **Veo 3.1 is the talking-character model.** It's the only one where dialogue, comic timing, and SFX arrive locked to on-screen action in a single generation — this is what powered the Bigfoot-vlog wave. Use it when the joke is *spoken*.
- **Hailuo 2.3 is the slapstick model.** Best obedience to motion directives ("the mascot faceplants into the desk, papers explode upward"), cheap per-clip pricing, but no audio — pair with TTS/ElevenLabs.
- **Kling 3.0 is the workhorse.** Best $/quality at 1080p, per-shot prompts with custom durations via API (multi-shot skits in one call), negative prompts, and character Elements. Default for anything needing a recurring character.
- **Seedance 2.0** when you need to feed existing brand assets (screenshots of SudoApply UI, past clips, a voice recording) directly as references — it accepts up to 9 images + 3 videos + 3 audio clips.
- **Wan 2.6** as the cheap fallback with audio included.

Cost anchor: a 10s vertical clip ≈ **$0.50–$1.70** (Hailuo/Wan/Kling) vs **$3–$5** (Sora 2 Pro / Veo 3.1 w/ audio). At 5 videos/day, model choice is a 5–10x monthly cost lever ($75 vs $750/mo).

---

## 2. Character consistency — a recurring AI "brand ambassador" without LoRA

The 2026 consensus: **nobody trains LoRAs for social video anymore.** Reference-image conditioning is good enough and zero-setup.

### The three mechanisms

1. **Kling "Elements" / Bind Subject** — upload 1–4 images of the character; Kling binds face + clothing across the generation. In Kling 3.0 I2V mode, enabling "Bind Subject" (element reference) is the documented fix for identity drift ([Kling Elements docs](https://app.klingai.com/global/quickstart/ai-video-character-consistency), [Atlas Cloud guide](https://www.atlascloud.ai/blog/guides/solving-character-inconsistency-a-guide-to-kling-3.0-image-to-video-mode)).
2. **Veo 3.1 "Ingredients to Video"** (`fal-ai/veo3.1/reference-to-video`) — up to 3 reference images with distinct roles: **subject** (locks identity), **environment** (stable world), **style** (consistent look). This is the strongest cross-scene identity system currently available via API ([Google blog](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-ingredients-to-video/)).
3. **Image-to-video from a canonical character sheet** — generate the character once as a set of stills (front/side/expressions) with gpt-image-2 or FLUX, store them, and always start video generations from one of those stills (I2V) rather than pure T2V. Works on every model including Hailuo and Wan (Wan 2.6 has a dedicated `reference-to-video` endpoint).

### Best practice for a recurring brand ambassador (e.g., a SudoApply mascot)

- **Create the character sheet once, version it, and treat it as brand infrastructure**: 4–8 canonical images (neutral, laughing, despairing-at-job-applications, holding phone), identical outfit and lighting.
- **Freeze a text "identity string"** (exact physical description, outfit, vibe) and prepend it verbatim to every prompt — practitioners report reusing identical descriptive attributes and avoiding lighting/camera-distance changes between shots is as important as the reference image ([Magic Hour Kling 3.0 reference guide](https://magichour.ai/blog/kling-30-reference-guide)).
- Route: **Kling Elements** for multi-shot skits, **Veo Ingredients** when the character must talk, **I2V from the sheet** everywhere else.
- Deliberately non-human/absurd mascots (creature, object with a face — Italian-brainrot style) are *more* consistent than humans (no uncanny-valley face drift) and read as self-aware AI humor rather than fake humans. This is the pragmatic choice for an AI-slop-aware brand.

---

## 3. Image models: memes and text-in-image

| Model | Access | Price | Text rendering | Notes |
|---|---|---|---|---|
| **gpt-image-2** | OpenAI API (token-billed) | 1024² ≈ $0.006 low / $0.053 med / $0.211 high | **~99% accuracy, best-in-class, incl. dense multi-word copy** | The meme model. Also does template *editing* (upload template image + instruction). LM Arena leader alongside FLUX 2 Pro. |
| **FLUX 2 Pro v1.1** | fal / BFL API | ~$0.055/img | ~85–90% English | Elo ties gpt-image; cheaper per image but weaker on dense text |
| **FLUX 2 Dev / Schnell** | fal | $0.025 / $0.015 | lower | Volume backgrounds, b-roll stills, carousel art |
| **Flux Kontext Pro** | `fal-ai/flux-kontext/pro` | $0.04/img | — | *Editing* model: modify an existing image via instruction — useful for meme-template remixing |
| **Nano Banana (Gemini)** | fal | ~$0.04/img | good | Fast, cheap, strong at photoreal edits |
| **Seedream V4** | fal | $0.03/img | good | Cheap photoreal alternative |

Sources: [BuildMVPFast image API costs](https://www.buildmvpfast.com/api-costs/ai-image), [gptimager comparison](https://gptimager.com/compare/gpt-image-2-vs-flux), [LaoZhang comparison](https://blog.laozhang.ai/en/posts/ai-image-generation-api-comparison-2026).

**Rule of thumb:** any image whose joke depends on rendered text (meme captions, fake UI screenshots, fake text-message convos, chart gags) → **gpt-image-2 medium** ($0.05). Pure visuals at volume → FLUX Dev/Schnell or Seedream. For maximum caption reliability, still composite text with Pillow over a generated background — deterministic > 99%.

---

## 4. TTS / voice for comedic delivery

### ElevenLabs Eleven v3 — the comedy engine
- **Audio tags in square brackets steer performance**: `[laughs]`, `[giggle]`, `[big laugh]`, `[sighs]`, `[whispers]`, `[excited]`, `[sarcastic]`, plus SFX-ish tags. Tags shape **tempo and timing** — the thing that makes a joke land ([ElevenLabs v3 audio tags](https://elevenlabs.io/blog/v3-audiotags)).
- 120+ emotional states, phoneme-level control; ranked #4 on Artificial Analysis (Elo 1,178) vs OpenAI TTS-1 at #17 (1,102) ([CallMissed TTS showdown](https://www.callmissed.com/en/blog/tts-showdown-2026-elevenlabs-vs-cartesia-vs-openai-vs-sesame-the-ultimate-compar)).
- Price: **$0.10/1k chars** (v3/multilingual v2); Flash/Turbo $0.05/1k. A 60-second script (~900 chars) ≈ $0.09. Also available on fal: `fal-ai/elevenlabs/tts/eleven-v3`.
- High latency, not for real-time — irrelevant for a posting pipeline.

### OpenAI gpt-4o-mini-tts — the cheap steerable option
- `instructions` parameter takes natural-language direction ("deadpan, slightly too fast, like someone who has applied to 400 jobs") — no SSML. ~**$0.015/min** (~6x cheaper than ElevenLabs v3) ([PromptLayer](https://blog.promptlayer.com/gpt-4o-mini-tts-steerable-low-cost-speech-via-simple-apis/), [OpenAI](https://openai.com/index/introducing-our-next-generation-audio-models/)).
- No inline laughter/emotion tags mid-line — coarser control than v3.

### Viral AI voice styles (2025–26)
- **Deadpan fast narrator** (Fireship/brainrot-explainer cadence) — the default for text-to-brainrot content.
- **Over-enthusiastic "AI announcer" played straight** — self-aware slop humor: the voice *sounds* AI on purpose.
- **Whisper/ASMR read** for satisfying-loop content.
- Recipe: **ElevenLabs v3 with tags for punchline lines; gpt-4o-mini-tts for bulk narration.** The marginal $0.08/video for v3 on the joke lines is the highest-ROI spend in the whole stack.

---

## 5. Lip-sync / talking-head tools

| Tool | Endpoint | Price | Notes |
|---|---|---|---|
| **Sync Lipsync 2.0** | `fal-ai/sync-lipsync/v2` (`/pro`) | $3/min ($5/min Pro) | Retrofit new audio onto existing video — re-dub a generated clip with a better take |
| **OmniHuman 1.5 (ByteDance)** | `fal-ai/bytedance/omnihuman` | $0.14–0.16/s | Single image + audio → full talking avatar; 60s audio at 720p; SOTA expressiveness |
| **Infinitalk** | `fal-ai/infinitalk` | $0.20/s | Image + audio → talking head, long-form capable |
| **Kling AI Avatar v2 Pro** | `fal-ai/kling-video/ai-avatar/v2/pro` | $0.115/s | Cheapest quality avatar path on fal |
| **MuseTalk** | `fal-ai/musetalk` | cheap | Fast/basic audio-driven lipsync |
| **VEED Fabric** | via fal | $0.15/s | Image-to-talking-video |
| **Hedra** (Character-3) | own API | ~50% cheaper than OmniHuman | 4,000+ voices, expressive; known artifacts: over-smiling, head-tilt, weak complex phonemes ([comparison](https://aifreeforever.com/blog/lip-sync-ai)) |

**Decision rule:** character must *speak* → generate directly in **Veo 3.1** (audio native, one call) when budget allows; otherwise **mascot still image + ElevenLabs v3 audio + OmniHuman/Kling Avatar** ≈ $0.10–0.16/s — half the cost of Veo-with-audio and reuses the canonical character sheet, guaranteeing identity.

---

## 6. What actual viral AI-slop creators use

Findings from creator tutorials and the [Kapwing TikTok AI Slop Report](https://www.kapwing.com/resources/the-tiktok-ai-slop-report/):

- **Scale:** 59% of videos served to a fresh TikTok account are AI-generated; TikTok carries ~3x YouTube's slop share. AI content is now the *water*, not the novelty — differentiation comes from writing, not from "wow, AI."
- **Backlash is real:** anti-AI comments routinely out-like the posts. The content that escapes backlash is either (a) so absurd it's clearly intentional comedy, or (b) self-aware about being AI. Earnest fake-human content gets ratioed. **This validates the "deliberately absurd, self-aware slop" strategy.**
- **The Bigfoot/Yeti vlog stack** (the canonical viral-AI-character workflow): ChatGPT/Gemini writes a character bible + per-clip selfie-vlog prompts → **Veo 3** generates 8s clips with native dialogue → CapCut strings 7–8 clips into a 60s arc. BigfootBoyz went 0 → 330k followers in 3 days, 15M+ views ([Superprompt guide](https://superprompt.com/blog/how-to-make-viral-ai-character-vlogs)). Key prompt trick: never say "POV camera" — say "holding a selfie stick (that's where the camera is)."
- **Italian brainrot** (Ballerina Cappuccina, Tung Tung Tung Sahur): absurd hybrid character images from ChatGPT/Gemini image gen → animated via Veo/Kling I2V → CapCut assembly, pseudo-Italian TTS narration. The formula: *object + animal + fake-language name + confident narration* ([nss G-Club explainer](https://www.nssgclub.com/en/lifestyle/40805/italian-brainrot-tiktok-meme-ballerina-cappuccina-explained)).
- **Text-to-brainrot SaaS** (StoryShort, Revid, Viggle templates): text in → TTS narration + Subway-Surfers-style background + word-timed captions out. This is exactly Mark's existing Path-B pipeline (TTS + Whisper timestamps + MoviePy) — commodity capability; the differentiator is script quality.
- **AI ASMR / satisfying loops** (glass-fruit cutting, kinetic sand, "survival ASMR"): Veo 3 with SFX-heavy prompts; seamless loops get watched 3–5x, and 2026 TikTok/IG algorithm changes reward high completion-rate loops aggressively ([LensGo](https://lensgo.ai/blog/ai-asmr-videos-trending-2026), [Pollo guide](https://pollo.ai/hub/how-to-make-viral-ai-glass-fruit-cutting-ai-asmr-videos)). Under $30 for 10 Reels.
- **Sora 2 app culture:** bodycam comedy, absurd movie-scene substitutions, Cameo (drop a real person into scenes — face-featuring videos get 3–5x shares). Formula documented across prompt roundups: **hyper-real production grammar (bodycam, CCTV, news chyron, ring-cam) + one impossible subject, played completely straight.**

---

## 7. Meme-specific generation

- **Imgflip API** ([imgflip.com/api](https://imgflip.com/api)): free `caption_image` over 1M+ templates, `get_memes` for top-100 trending templates, template search. Text placement on known templates is deterministic and reliable. Its `automeme` AI captioner is hit-or-miss/generic per 2026 reviews ([alici.ai](https://alici.ai/blog/best-ai-meme-generators-2026)) — **use Imgflip for rendering, your own LLM for the joke.**
- **gpt-image-2 for "organic" memes**: generates novel meme-format images with near-perfect caption text, and can *edit* an uploaded template. Costs $0.05 vs Imgflip's free, but produces memes that don't look like a bot filled in a template — better for platforms where template memes read as low-effort (LinkedIn, Bluesky).
- **Pillow compositing** (already in Mark's stack) remains the most reliable text overlay: LLM writes top/bottom text + picks template → Pillow renders. 100% text fidelity, $0 render cost.
- **Template freshness is the actual hard problem.** A meme in a stale template is worse than no meme. Poll Imgflip `get_memes` (ordered by recent usage) as a trend signal for which formats are currently alive.

---

## Pipeline implications

Concrete rules an automated system (Mark) can encode:

### Model routing table
1. **Spoken-joke video (character talks):** Veo 3.1 Fast w/ audio (`fal-ai/veo3.1/fast`), 8s clips chained; budget ≈ $1.20–$3.20/60s. Premium: Veo 3.1 standard.
2. **Physical-comedy / absurd-motion video (no dialogue):** Hailuo 2.3 I2V ($0.28–0.49/clip) or Kling V3 Standard ($0.084/s) + ElevenLabs/gpt-4o-mini-tts voiceover via existing Path-B assembly.
3. **Absurdist "played straight" skits:** Sora 2 ($0.10/s) while it lasts — **hard-code a sunset check: OpenAI Sora 2 API dies 2026-09-24; auto-fail-over to Veo 3.1/Kling.**
4. **Cheap volume with audio:** Wan 2.6 ($0.10/s).
5. **Text-bearing images (memes, fake screenshots, carousels with copy):** gpt-image-2 medium. Pure visuals: FLUX 2 Dev/Schnell or Seedream V4 ($0.015–0.03).
6. **Talking mascot on a budget:** canonical still + ElevenLabs v3 audio + OmniHuman/Kling Avatar ($0.115–0.16/s).

### Brand-ambassador subsystem
7. Generate a **versioned character sheet** (4–8 canonical stills + frozen identity paragraph) per product; store paths in DB. Every video generation must pass either the sheet (Kling Elements / Veo Ingredients / I2V) or start from a sheet still. Never generate the character from text alone.
8. Prefer a **non-human absurd mascot** — better identity stability, and self-aware-AI humor deflects slop backlash.

### Prompt strategies
9. Encode the viral video grammar as prompt templates: `{hyper-real format: bodycam|selfie-vlog|CCTV|news-report|ring-cam} + {impossible/absurd subject} + played completely straight`. For selfie-vlogs, write "holding a selfie stick (that's where the camera is)", never "POV."
10. For comedic TTS: route punchline-bearing scripts to ElevenLabs v3 with audio tags (`[sighs]`, `[laughs]`, pauses via `...`); have the Writer agent emit tags inline in the script field. Bulk/neutral narration → gpt-4o-mini-tts with an `instructions` string generated from the content plan's tone.
11. Memes: LLM writes the joke + selects template from a live pull of Imgflip `get_memes` (trend signal); render via Pillow/Imgflip for guaranteed text, or gpt-image-2 when a "non-template" organic meme fits the platform.
12. Add a **loopability heuristic** for TikTok/Reels: last frame ≈ first frame (satisfying/ASMR-adjacent content); completion-rate looping is the single strongest 2026 algorithm lever.

### Cost + safety rails
13. Budget guardrail: default stack keeps a 10s vertical video ≤ $1.20 all-in (video + TTS + assembly); flag any plan projected > $5.
14. Self-aware framing rule in the Writer prompt: content must either be obviously-intentional absurdity or explicitly wink at being AI; never pass AI content off as earnest human footage (backlash comments out-like earnest slop posts).
