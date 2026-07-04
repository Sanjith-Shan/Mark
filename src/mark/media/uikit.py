"""Deterministic fake-UI mockup renderer (satirical-ui-franchise).

The joke in a satirical UI mockup lives in the interface text, so it must be
pixel-perfect — generative image models garble text. This renders a clean,
corporate-neutral app window with Pillow from a simple line spec the writer
produces in ``slide_texts``:

    line 1            → window title
    "text: …"         → plain row
    "field: …"        → input field (the value is the joke)
    "button: …"       → primary button
    "button_disabled: …" → greyed-out button
    "tooltip: …"      → tooltip bubble (attaches under the previous element)
    "counter: …"      → big stat row
    "toggle: …"       → setting row with an ON toggle
    (bare line)       → plain row

Anything unparseable degrades to a text row, so the renderer never fails.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..app import App
from .images import _load_font, _parse_size

# Corporate-neutral palette (adjacent to, but legally distinct from, the tools
# being satirized).
BG = (241, 243, 246)
CARD = (255, 255, 255)
CARD_BORDER = (223, 227, 233)
TITLE = (23, 29, 41)
TEXT = (55, 65, 81)
MUTED = (130, 140, 155)
FIELD_BG = (247, 248, 250)
FIELD_BORDER = (209, 213, 219)
PRIMARY = (37, 99, 235)
PRIMARY_TEXT = (255, 255, 255)
DISABLED_BG = (229, 231, 235)
DISABLED_TEXT = (156, 163, 175)
TOOLTIP_BG = (17, 24, 39)
TOOLTIP_TEXT = (243, 244, 246)
ACCENT = (220, 38, 38)


def parse_spec(lines: list[str]) -> tuple[str, list[tuple[str, str]]]:
    lines = [ln.strip() for ln in (lines or []) if ln and ln.strip()]
    if not lines:
        return "Untitled", []
    title = lines[0]
    rows: list[tuple[str, str]] = []
    for ln in lines[1:]:
        kind, _, rest = ln.partition(":")
        kind_l = kind.strip().lower()
        if rest and kind_l in ("text", "field", "button", "button_disabled",
                               "tooltip", "counter", "toggle"):
            rows.append((kind_l, rest.strip()))
        else:
            rows.append(("text", ln))
    return title, rows


def render_ui_mockup(app: App, slide_lines: list[str], out_path: Path,
                     size: str = "1024x1024") -> Path:
    """Render the mockup window; always succeeds, always legible."""
    w, h = _parse_size(size)
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    title, rows = parse_spec(slide_lines)

    # Window card.
    margin = int(w * 0.07)
    card_x0, card_y0 = margin, int(h * 0.10)
    card_x1, card_y1 = w - margin, h - int(h * 0.10)
    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=24,
                           fill=CARD, outline=CARD_BORDER, width=2)

    # Title bar with traffic lights.
    bar_h = int(h * 0.055)
    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y0 + bar_h],
                           radius=24, fill=(249, 250, 251))
    draw.rectangle([card_x0, card_y0 + bar_h - 24, card_x1, card_y0 + bar_h],
                   fill=(249, 250, 251))
    draw.line([card_x0, card_y0 + bar_h, card_x1, card_y0 + bar_h],
              fill=CARD_BORDER, width=2)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = card_x0 + 28 + i * 34
        cy = card_y0 + bar_h // 2
        draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=color)

    title_font = _load_font(int(h * 0.026))
    draw.text((card_x0 + 130, card_y0 + bar_h // 2 - int(h * 0.015)),
              title[:60], font=title_font, fill=TITLE)

    # Body rows.
    x = card_x0 + int(w * 0.045)
    x1 = card_x1 - int(w * 0.045)
    y = card_y0 + bar_h + int(h * 0.035)
    body_font = _load_font(int(h * 0.028))
    small_font = _load_font(int(h * 0.022))
    big_font = _load_font(int(h * 0.05))
    row_gap = int(h * 0.022)

    def wrapped(text: str, font, max_w: int) -> list[str]:
        words, out, cur = text.split(), [], ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    out.append(cur)
                cur = word
        if cur:
            out.append(cur)
        return out or [""]

    for kind, value in rows[:9]:
        if y > card_y1 - int(h * 0.09):
            break
        if kind == "text":
            for line in wrapped(value, body_font, x1 - x)[:3]:
                draw.text((x, y), line, font=body_font, fill=TEXT)
                y += int(h * 0.038)
            y += row_gap // 2
        elif kind == "field":
            fh = int(h * 0.062)
            draw.rounded_rectangle([x, y, x1, y + fh], radius=12,
                                   fill=FIELD_BG, outline=FIELD_BORDER, width=2)
            line = wrapped(value, body_font, x1 - x - 40)[0]
            draw.text((x + 20, y + fh // 2 - int(h * 0.016)), line,
                      font=body_font, fill=MUTED)
            y += fh + row_gap
        elif kind in ("button", "button_disabled"):
            disabled = kind == "button_disabled"
            bw = min(int(draw.textlength(value, font=body_font)) + 76, x1 - x)
            bh = int(h * 0.06)
            draw.rounded_rectangle([x, y, x + bw, y + bh], radius=14,
                                   fill=DISABLED_BG if disabled else PRIMARY)
            draw.text((x + 38, y + bh // 2 - int(h * 0.016)), value,
                      font=body_font,
                      fill=DISABLED_TEXT if disabled else PRIMARY_TEXT)
            y += bh + row_gap
        elif kind == "tooltip":
            lines = wrapped(value, small_font, x1 - x - 120)[:2]
            th = len(lines) * int(h * 0.032) + 24
            tw = min(max(int(draw.textlength(ln, font=small_font)) for ln in lines) + 44,
                     x1 - x - 40)
            tx = x + 40
            draw.polygon([(tx + 30, y), (tx + 50, y), (tx + 40, y - 12)], fill=TOOLTIP_BG)
            draw.rounded_rectangle([tx, y, tx + tw, y + th], radius=10, fill=TOOLTIP_BG)
            ty = y + 12
            for ln in lines:
                draw.text((tx + 22, ty), ln, font=small_font, fill=TOOLTIP_TEXT)
                ty += int(h * 0.032)
            y += th + row_gap
        elif kind == "counter":
            label, _, number = value.rpartition(" ")
            if not label:
                label, number = value, ""
            draw.text((x, y), number or value, font=big_font, fill=ACCENT)
            ny = y + int(h * 0.055)
            for line in wrapped(label, small_font, x1 - x)[:2]:
                draw.text((x, ny), line, font=small_font, fill=MUTED)
                ny += int(h * 0.03)
            y = ny + row_gap
        elif kind == "toggle":
            fh = int(h * 0.05)
            for line in wrapped(value, body_font, x1 - x - 130)[:2]:
                draw.text((x, y), line, font=body_font, fill=TEXT)
                y += int(h * 0.038)
            tx0 = x1 - 96
            ty0 = y - int(h * 0.052)
            draw.rounded_rectangle([tx0, ty0, tx0 + 84, ty0 + fh - 8], radius=(fh - 8) // 2,
                                   fill=PRIMARY)
            r = (fh - 16) // 2
            draw.ellipse([tx0 + 84 - 8 - 2 * r, ty0 + 4, tx0 + 84 - 8, ty0 + 4 + 2 * r],
                         fill=CARD)
            y += row_gap
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
