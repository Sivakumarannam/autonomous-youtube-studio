"""Static caption bar with anti-edge-clipping layout (up to 3 lines)."""
from __future__ import annotations

from app.core.config import settings


def draw_caption_bar(
    renderer,
    img,
    draw,
    text: str,
    font,
    canvas_width: int,
    canvas_height: int,
    max_width: int,
) -> None:
    """YouTube-style caption bar; never draws text past safe side margins."""
    from PIL import Image, ImageDraw

    if not text:
        return

    side_margin = 48
    safe_max = min(max_width, canvas_width - 2 * side_margin)
    if safe_max < 80:
        safe_max = max(80, canvas_width - 32)

    try:
        base_size = int(getattr(font, "size", 32) or 32)
    except Exception:
        base_size = 32

    def _measure(s: str, fnt) -> int:
        bbox = draw.textbbox((0, 0), s, font=fnt)
        return bbox[2] - bbox[0]

    def _fit_token(token: str, fnt, limit: int):
        if _measure(token, fnt) <= limit:
            return fnt, token
        size = int(getattr(fnt, "size", base_size) or base_size)
        trial = fnt
        for new_size in range(size - 2, max(16, size // 2) - 1, -2):
            try:
                trial = renderer._load_font(bold=True, size=new_size)
            except Exception:
                break
            if _measure(token, trial) <= limit:
                return trial, token
        t = token
        while len(t) > 3 and _measure(t + "…", trial) > limit:
            t = t[:-1]
        return trial, (t + "…") if t != token else t

    max_lines = 3  # was 2 — CTA was cut mid-sentence
    words = text.split()
    lines: list[str] = []
    current = ""
    line_font = font

    for word in words:
        word_font, word_fit = _fit_token(word, line_font, safe_max)
        if word_font is not line_font and not current:
            line_font = word_font
            word = word_fit
        elif word_font is not line_font:
            word = word_fit

        candidate = f"{current} {word}".strip() if current else word
        if _measure(candidate, line_font) <= safe_max:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)

    lines = lines[:max_lines]
    if not lines:
        return

    # If still overflowing last line, ellipsis instead of hard cut
    fitted_lines: list[str] = []
    for i, line in enumerate(lines):
        if _measure(line, line_font) <= safe_max:
            fitted_lines.append(line)
        else:
            size = int(getattr(line_font, "size", base_size) or base_size)
            trial = line_font
            text_out = line
            for new_size in range(size, 15, -2):
                trial = renderer._load_font(bold=True, size=new_size)
                if _measure(line, trial) <= safe_max:
                    line_font = trial
                    text_out = line
                    break
            else:
                t = line
                while len(t) > 3 and _measure(t + "…", trial) > safe_max:
                    t = t[:-1]
                text_out = t + "…"
                line_font = trial
            fitted_lines.append(text_out)
    lines = fitted_lines

    # leftover words → put on last line with …
    used = " ".join(lines).split()
    if len(used) < len(words) and lines:
        rest = " ".join(words[len(used):])
        last = lines[-1]
        extra = f"{last} {rest}".strip()
        if _measure(extra, line_font) <= safe_max:
            lines[-1] = extra
        else:
            t = extra
            while len(t) > 3 and _measure(t + "…", line_font) > safe_max:
                t = t[:-1]
            lines[-1] = t + "…"

    try:
        line_height = int(getattr(line_font, "size", 28) or 28) + 8
    except Exception:
        line_height = 28

    padding_v = 14
    bar_height = len(lines) * line_height + padding_v * 2
    bottom_gap = max(32, int(canvas_height * 0.025))
    bar_top = canvas_height - bar_height - bottom_gap

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [(0, bar_top), (canvas_width, bar_top + bar_height)],
        fill=(0, 0, 0, 190),
    )
    img.paste(
        Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"),
        (0, 0),
    )

    draw2 = ImageDraw.Draw(img)
    y = bar_top + padding_v

    use_stroke = settings.text_style_profile in ("modern", "bold")
    stroke_width = 2 if settings.text_style_profile == "bold" else 1

    for line in lines:
        line_w = _measure(line, line_font)
        x = (canvas_width - line_w) // 2
        x = max(side_margin, min(x, canvas_width - side_margin - line_w))

        if use_stroke:
            for dx, dy in [
                (-stroke_width, 0),
                (stroke_width, 0),
                (0, -stroke_width),
                (0, stroke_width),
            ]:
                draw2.text((x + dx, y + dy), line, fill=(0, 0, 0), font=line_font)

        draw2.text((x, y), line, fill=(255, 255, 255), font=line_font)
        y += line_height
