"""Media orchestration — routes a ContentDraft to the right generator.

Returns a dict with ``media_paths`` (local files) and ``media_urls`` (filled later
if/when assets are uploaded). Video assembly lives in :mod:`mark.media.video` and
is imported lazily so the text/image pipeline has no hard dependency on the video
stack (moviepy/ffmpeg/fal).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .. import db as db_module
from .. import media as _media_pkg  # noqa: F401 (namespace anchor)
from ..app import App
from ..llm import LLM
from ..media import images


def media_dir_for(app: App, product_id: str, content_id: int) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    d = app.paths.media_dir / product_id / day / str(content_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def produce_media(app: App, llm: LLM, product: dict, content_id: int, plan, draft,
                  character: dict = None, strategy=None) -> dict:
    """Generate all media for a piece of content. Raises on hard failure so the
    caller can apply the video→image fallback. When ``character`` is set, image
    and video generation are conditioned on its reference sheet so the same
    face/outfit appears in every asset. Some strategies use dedicated
    deterministic renderers (UI mockups, chat-drama videos) where text fidelity
    or zero-AI-labeling matters more than generative visuals."""
    ct = plan.content_type
    if ct in ("text", "thread"):
        return {"media_paths": [], "media_urls": []}

    out_dir = media_dir_for(app, product["id"], content_id)
    size = images.platform_size(plan.platform, ct)
    strategy_id = getattr(strategy, "id", None)

    # Satirical UI mockups: the joke IS the interface text — render it
    # deterministically so it's pixel-perfect (models garble UI copy).
    if strategy_id == "satirical-ui-franchise" and ct in ("image", "carousel"):
        from ..media import uikit

        spec = draft.slide_texts or [draft.hook, draft.caption]
        if ct == "carousel":
            # One mockup PER slide. Multi-line entries are already per-slide
            # specs; a single flat spec becomes a progressive reveal (title +
            # rows so far) so the swipe builds the joke.
            if any("\n" in (s or "") for s in spec):
                slide_specs = [s.splitlines() for s in spec if s and s.strip()]
            else:
                title, rest = spec[0], spec[1:] or [spec[0]]
                slide_specs = [[title, *rest[: i + 1]] for i in range(len(rest))]
            paths = []
            for i, slide in enumerate(slide_specs[:10]):
                p = out_dir / f"{content_id}_{plan.platform}_mockup{i + 1}.png"
                uikit.render_ui_mockup(app, slide, p, size=size)
                paths.append(str(p))
            return {"media_paths": paths, "media_urls": []}
        path = out_dir / f"{content_id}_{plan.platform}_mockup.png"
        uikit.render_ui_mockup(app, spec, path, size=size)
        return {"media_paths": [str(path)], "media_urls": []}

    # Fake-text drama: chat-bubble compositor (no AI media, no labeling) —
    # video for the paced reveal, sequential screenshots for carousels.
    if strategy_id == "fake-text-drama" and ct in ("video", "carousel"):
        from ..media import chatdrama

        if ct == "carousel":
            script = draft.script or "\n".join(draft.slide_texts or []) or draft.caption or ""
            n = len(draft.slide_texts or []) or 5
            paths = chatdrama.render_chat_slides(
                app, script, out_dir, f"{content_id}_{plan.platform}_chat",
                title=(plan.topic or "the group chat")[:38], slides=n)
            return {"media_paths": [str(p) for p in paths], "media_urls": []}
        script = draft.script or draft.caption or ""
        path = out_dir / f"{content_id}_{plan.platform}_chatdrama.mp4"
        chatdrama.render_chat_video(app, script, path,
                                    title=(plan.topic or "the group chat")[:38])
        return {"media_paths": [str(path)], "media_urls": []}

    refs = None
    prompt = draft.image_prompt or plan.topic
    if character and character.get("reference_image"):
        from .. import characters as characters_mod

        refs = [character["reference_image"]]
        prompt = characters_mod.scene_prompt(character, prompt)

    if ct == "image":
        path = out_dir / f"{content_id}_{plan.platform}_image.png"
        images.generate_image(app, llm, prompt, path, size=size, reference_images=refs,
                              content_id=content_id, product_id=product["id"])
        return {"media_paths": [str(path)], "media_urls": []}

    if ct == "carousel":
        return _produce_carousel(app, llm, product, content_id, plan, draft, out_dir)

    if ct == "video":
        from ..media import video  # lazy: keeps the video stack optional

        result = video.produce_video(app, llm, product, content_id, plan, draft, out_dir,
                                     character=character)
        return {"media_paths": result["media_paths"], "media_urls": []}

    # Unknown type → treat as image (recorded — the learning loop needs to know).
    record_degradation(app, f"unknown content_type '{ct}' → image",
                       content_id=content_id, product_id=product["id"])
    path = out_dir / f"{content_id}_{plan.platform}_image.png"
    images.generate_image(app, llm, draft.image_prompt or plan.topic, path,
                          size=size, content_id=content_id, product_id=product["id"])
    return {"media_paths": [str(path)], "media_urls": []}


def record_degradation(app: App, reason: str, content_id: int | None = None,
                       product_id: str | None = None) -> None:
    """Record that media production fell back to a simpler path. A silent
    fallback poisons reward attribution — the learning loop must know what was
    actually produced — so the reason goes in the activity feed AND the content
    row's error column. Status is left alone; the content is still postable."""
    db_module.log_activity(app.conn, "media_degraded", reason,
                           product_id=product_id, content_id=content_id, level="info")
    if content_id is None:
        return
    try:
        row = app.conn.execute("SELECT error FROM content WHERE id = ?",
                               (content_id,)).fetchone()
        prior = (row["error"] or "").strip() if row else ""
        note = f"degraded: {reason}"
        if note in prior:
            return
        app.conn.execute("UPDATE content SET error = ? WHERE id = ?",
                         (f"{prior}; {note}" if prior else note, content_id))
        app.conn.commit()
    except Exception:
        pass  # best-effort, like the activity feed


def prune_old_media(app: App, days: int = 30) -> int:
    """Delete generated media files older than ``days`` to prevent disk bloat.
    Returns the number of files removed. Empty directories are cleaned up too."""
    root = app.paths.media_dir
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    # Remove now-empty directories (deepest first).
    for d in sorted([p for p in root.rglob("*") if p.is_dir()], reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    return removed


def _produce_carousel(app, llm, product, content_id, plan, draft, out_dir) -> dict:
    slides_text = draft.slide_texts or [draft.hook, draft.caption]
    prompts_list = list(draft.image_prompts or [])
    if not prompts_list:
        prompts_list = [draft.image_prompt or plan.topic] * len(slides_text)
    # Pad rather than zip-drop: every slide_text must get a slide even when the
    # writer produced fewer image_prompts than slides.
    while len(prompts_list) < len(slides_text):
        prompts_list.append(prompts_list[-1])
    size = images.platform_size(plan.platform, "carousel")
    paths = []
    for i, (text, prompt) in enumerate(zip(slides_text, prompts_list)):
        p = out_dir / f"{content_id}_{plan.platform}_slide{i + 1}.png"
        images.generate_image(app, llm, prompt, p, size=size,
                              content_id=content_id, product_id=product["id"])
        # Burn the slide's text onto the image so the carousel is self-contained.
        images.add_text_overlay(p, text, position="center")
        paths.append(str(p))
    return {"media_paths": paths, "media_urls": []}
