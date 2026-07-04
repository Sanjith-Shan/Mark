"""Image generation + processing.

Real path: OpenAI image model (gpt-image-*). Offline path: a generated gradient
with the prompt text rendered on it via Pillow — a real PNG so the rest of the
pipeline (carousel assembly, posting previews) works unchanged.
"""

from __future__ import annotations

import base64
import textwrap
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..app import App
from ..llm import LLM, log_external_cost

# Platform-specific output sizes (from the spec).
PLATFORM_IMAGE_SPECS = {
    "tiktok": {"size": "1024x1536"},
    "instagram": {"size": "1024x1024"},
    "instagram_reel": {"size": "1024x1536"},
    "instagram_carousel": {"size": "1024x1024"},
    "x": {"size": "1536x1024"},
    "linkedin": {"size": "1536x1024"},
    "youtube": {"size": "1024x1536"},
    "bluesky": {"size": "1024x1024"},
    "threads": {"size": "1024x1024"},
    "reddit": {"size": "1024x1024"},
    "pinterest": {"size": "1024x1536"},
}


def platform_size(platform: str, content_type: str = "image") -> str:
    if platform == "instagram" and content_type == "carousel":
        return PLATFORM_IMAGE_SPECS["instagram_carousel"]["size"]
    if platform == "instagram" and content_type == "video":
        return PLATFORM_IMAGE_SPECS["instagram_reel"]["size"]
    return PLATFORM_IMAGE_SPECS.get(platform, {"size": "1024x1024"})["size"]


def _parse_size(size: str) -> tuple[int, int]:
    w, h = size.lower().split("x")
    return int(w), int(h)


def generate_image(
    app: App,
    llm: LLM,
    prompt: str,
    out_path: Path,
    *,
    size: str = "1024x1024",
    quality: Optional[str] = None,
    reference_images: Optional[list[Path]] = None,
    content_id: Optional[int] = None,
    product_id: Optional[str] = None,
) -> Path:
    """Generate one image to ``out_path`` and return the path.

    ``reference_images`` switches to reference-conditioned generation
    (images.edit) so a persistent character keeps the same face/outfit across
    every asset. Falls back to plain generation if the edit call fails.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    quality = quality or app.settings.media.image_quality
    refs = [Path(r) for r in (reference_images or []) if Path(r).exists()]

    if app.is_mock("openai"):
        mock_key = prompt + "".join(r.name for r in refs)
        img = _mock_image(mock_key, _parse_size(size))
        img.save(out_path)
        log_external_cost(app, "openai", "image", quality, units=1,
                          content_id=content_id, product_id=product_id, mocked=True)
        return out_path

    client = llm.client()
    resp = None
    if refs:
        try:
            handles = [open(r, "rb") for r in refs]
            try:
                resp = client.images.edit(
                    model=app.settings.media.image_model,
                    image=handles if len(handles) > 1 else handles[0],
                    prompt=prompt, size=size, quality=quality,
                    input_fidelity="high",  # preserve faces/identity from the reference
                    n=1,
                )
            finally:
                for h in handles:
                    h.close()
        except Exception:
            import logging

            logging.getLogger("mark.images").warning(
                "reference-conditioned edit failed; falling back to plain generation")
            resp = None
    if resp is None:
        resp = client.images.generate(
            model=app.settings.media.image_model, prompt=prompt,
            size=size, quality=quality, n=1,
        )
    datum = resp.data[0]
    if getattr(datum, "b64_json", None):
        out_path.write_bytes(base64.b64decode(datum.b64_json))
    elif getattr(datum, "url", None):
        import httpx

        out_path.write_bytes(httpx.get(datum.url, timeout=60).content)
    else:  # pragma: no cover - defensive
        raise RuntimeError("Image API returned neither b64_json nor url")
    log_external_cost(app, "openai", "image", quality, units=1,
                      content_id=content_id, product_id=product_id)
    return out_path


# --------------------------------------------------------------------------- #
# Text overlay (used for carousels, video frames, captions-on-image)
# --------------------------------------------------------------------------- #
def add_text_overlay(image_path: Path, text: str, out_path: Optional[Path] = None,
                     position: str = "center") -> Path:
    """Draw bold, outlined text on an existing image (for carousel slides)."""
    image_path = Path(image_path)
    out_path = Path(out_path) if out_path else image_path
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    font = _load_font(int(h * 0.06))

    wrapped = _wrap(text, draw, font, int(w * 0.86))
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=10)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) / 2
    y = {"center": (h - th) / 2, "top": h * 0.08, "bottom": h * 0.80}.get(position, (h - th) / 2)

    # Darkened band behind text for legibility.
    pad = int(h * 0.02)
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 180))
    _draw_outlined(draw, (x, y), wrapped, font)
    img.save(out_path)
    return out_path


def _draw_outlined(draw, xy, text, font, fill=(255, 255, 255), outline=(0, 0, 0)):
    x, y = xy
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if dx or dy:
                draw.multiline_text((x + dx, y + dy), text, font=font, fill=outline, spacing=10, align="center")
    draw.multiline_text((x, y), text, font=font, fill=fill, spacing=10, align="center")


# --------------------------------------------------------------------------- #
# Offline rendering
# --------------------------------------------------------------------------- #
def _mock_image(prompt: str, size: tuple[int, int]) -> Image.Image:
    w, h = size
    # Deterministic gradient seeded by the prompt so the same prompt looks stable.
    seed = abs(hash(prompt)) % (2**32)
    rng = np.random.default_rng(seed)
    top = rng.integers(20, 120, size=3)
    bottom = rng.integers(80, 220, size=3)
    grad = np.linspace(0, 1, h)[:, None, None]
    arr = (top[None, None, :] * (1 - grad) + bottom[None, None, :] * grad)
    arr = np.broadcast_to(arr, (h, w, 3)).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")

    draw = ImageDraw.Draw(img)
    font = _load_font(int(h * 0.045))
    wrapped = _wrap(prompt, draw, font, int(w * 0.84))
    _draw_outlined(draw, (w * 0.08, h * 0.40), wrapped, font)
    tag_font = _load_font(int(h * 0.028))
    draw.text((w * 0.08, h * 0.04), "MARK · offline preview", font=tag_font, fill=(255, 255, 255))
    return img


def _wrap(text: str, draw, font, max_width: int) -> str:
    # Estimate average char width to choose a wrap column.
    avg = max(draw.textlength("abcdefghij", font=font) / 10, 1)
    cols = max(int(max_width / avg), 8)
    return "\n".join(textwrap.fill(line, width=cols) for line in text.splitlines() or [text])


_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "DejaVuSans-Bold.ttf",
]


def _load_font(size: int):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()
