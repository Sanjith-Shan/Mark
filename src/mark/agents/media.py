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

from .. import media as _media_pkg  # noqa: F401 (namespace anchor)
from ..app import App
from ..llm import LLM
from ..media import images


def media_dir_for(app: App, product_id: str, content_id: int) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    d = app.paths.media_dir / product_id / day / str(content_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def produce_media(app: App, llm: LLM, product: dict, content_id: int, plan, draft) -> dict:
    """Generate all media for a piece of content. Raises on hard failure so the
    caller can apply the video→image fallback."""
    ct = plan.content_type
    if ct in ("text", "thread"):
        return {"media_paths": [], "media_urls": []}

    out_dir = media_dir_for(app, product["id"], content_id)
    size = images.platform_size(plan.platform, ct)

    if ct == "image":
        path = out_dir / f"{content_id}_{plan.platform}_image.png"
        images.generate_image(app, llm, draft.image_prompt or plan.topic, path,
                              size=size, content_id=content_id, product_id=product["id"])
        return {"media_paths": [str(path)], "media_urls": []}

    if ct == "carousel":
        return _produce_carousel(app, llm, product, content_id, plan, draft, out_dir)

    if ct == "video":
        from ..media import video  # lazy: keeps the video stack optional

        result = video.produce_video(app, llm, product, content_id, plan, draft, out_dir)
        return {"media_paths": result["media_paths"], "media_urls": []}

    # Unknown type → treat as image.
    path = out_dir / f"{content_id}_{plan.platform}_image.png"
    images.generate_image(app, llm, draft.image_prompt or plan.topic, path,
                          size=size, content_id=content_id, product_id=product["id"])
    return {"media_paths": [str(path)], "media_urls": []}


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
    prompts_list = draft.image_prompts or [draft.image_prompt or plan.topic] * len(slides_text)
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
