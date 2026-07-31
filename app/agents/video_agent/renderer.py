from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.core.logging import get_logger

# ---------------------------------------------------------------------------
# Narration sanitizer — must match the one in service.py
# ---------------------------------------------------------------------------
_HASHTAG_RE = re.compile(r"#\w+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


def _clean_caption(text: str) -> str:
    """Strip emojis, hashtags, and URLs from text before rendering as caption."""
    text = _HASHTAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "N", "P", "Z")) or ch in (" ", "\n", "\t", "-", "'", '"'):
            cleaned.append(ch)
    text = "".join(cleaned)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Render constants — driven by video_quality_preset config
# ---------------------------------------------------------------------------

_FPS_BY_PRESET = {
    "draft": 18,
    "standard": 24,
    "high": 24,
    "cinematic": 24,
}
_FFMPEG_PRESET_BY_PRESET = {
    "draft": "ultrafast",
    "standard": "medium",
    "high": "slow",
    "cinematic": "slow",
}
_CRF_BY_PRESET = {
    "draft": 28,
    "standard": 20,
    "high": 18,
    "cinematic": 16,
}
_RENDER_THREADS = 2
_LONG_RESOLUTION = (1280, 720)
_SHORT_RESOLUTION = (720, 1280)
_CROSSFADE_DURATION = 0.35  # seconds — used when enable_transitions=True


def _render_fps() -> int:
    return _FPS_BY_PRESET.get(settings.video_quality_preset, 24)


def _render_preset() -> str:
    return _FFMPEG_PRESET_BY_PRESET.get(settings.video_quality_preset, "medium")


def _render_crf() -> int:
    return _CRF_BY_PRESET.get(settings.video_quality_preset, 20)


@dataclass
class VideoRenderResult:
    success: bool
    video_path: Optional[str] = None
    duration_seconds: float = 0.0
    file_size: int = 0
    error_message: Optional[str] = None


class VideoRenderer:
    """
    Assembles a real .mp4 from storyboard scenes.

    Each scene card shows:
      - The NARRATION text (what the voice is actually saying) — large, centred
      - The VISUAL hint (camera/image direction) — small, muted, bottom

    Scene durations are proportionally distributed across the real audio
    duration so the cards change in sync with the voice-over.

    Quality improvements (v2):
      - Higher FPS and better FFmpeg preset/CRF (driven by video_quality_preset)
      - Cross-fade transitions between scenes (enable_transitions)
      - Ken Burns zoom/pan effect on static image backgrounds (enable_ken_burns)
      - Cinematic dark gradient overlay for text readability (enable_cinematic_overlay)
      - Text stroke + shadow for professional caption styling (text_style_profile)
      - Professional gradient fallback backgrounds
    """

    def render(
        self,
        script_id: str,
        scenes: list[dict[str, Any]],
        audio_path: Optional[str],
        script_type: str = "long",
        image_paths: Optional[dict[int, str]] = None,
        presenter_path: Optional[str] = None,
        hook_text: Optional[str] = None,
    ) -> VideoRenderResult:
        if not scenes:
            return VideoRenderResult(
                success=False,
                error_message="No scenes available to render.",
            )

        videos_dir = Path(settings.storage_local_path) / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        frames_dir = videos_dir / "_frames" / script_id
        frames_dir.mkdir(parents=True, exist_ok=True)

        output_path = videos_dir / f"{script_id}.mp4"
        resolution = _SHORT_RESOLUTION if script_type == "short" else _LONG_RESOLUTION

        try:
            # When karaoke captions are enabled, generate background-only PNGs
            # (no baked caption text).  The renderer will add animated per-word
            # caption overlays in _assemble_video instead.
            karaoke_mode = settings.caption_style == "karaoke"

            frame_paths = self._render_scene_cards(
                scenes=scenes,
                frames_dir=frames_dir,
                resolution=resolution,
                image_paths=image_paths or {},
                bake_captions=not karaoke_mode,
            )

            duration, file_size = self._assemble_video(
                frame_paths=frame_paths,
                scenes=scenes,
                audio_path=audio_path,
                output_path=output_path,
                resolution=resolution,
                karaoke_mode=karaoke_mode,
                presenter_path=presenter_path,
                hook_text=hook_text,
            )

            return VideoRenderResult(
                success=True,
                video_path=str(output_path),
                duration_seconds=duration,
                file_size=file_size,
            )

        except ImportError as exc:
            logger.warning("Video rendering dependency missing", error=str(exc))
            return VideoRenderResult(
                success=False,
                error_message=f"Rendering dependency unavailable: {exc}",
            )

        except Exception as exc:
            logger.error("Video rendering failed", error=str(exc))
            return VideoRenderResult(
                success=False,
                error_message=str(exc),
            )

        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Scene card rendering
    # ------------------------------------------------------------------

    def _render_scene_cards(
        self,
        scenes: list[dict[str, Any]],
        frames_dir: Path,
        resolution: tuple[int, int],
        image_paths: dict[int, str] | None = None,
        bake_captions: bool = True,
    ) -> list[Path]:
        from PIL import Image, ImageDraw, ImageFont

        if image_paths is None:
            image_paths = {}

        width, height = resolution

        # Scale fonts proportionally to canvas height for consistent readability
        # at both 720x1280 (Shorts) and 1280x720 (landscape) resolutions.
        base = height / 1280  # 1.0 at Shorts height; ~0.56 at landscape
        narration_font = self._load_font(bold=True, size=max(36, int(52 * base)))
        visual_font = self._load_font(bold=True, size=max(28, int(38 * base)))
        label_font = self._load_font(bold=False, size=max(18, int(22 * base)))

        frame_paths: list[Path] = []

        for index, scene in enumerate(scenes):
            scene_num = scene.get("scene_number", index + 1)
            bg_image_path = image_paths.get(scene_num)

            # ------------------------------------------------------------------
            # Background: AI-generated image (cover crop) or gradient card
            # ------------------------------------------------------------------
            img = self._make_background(
                bg_image_path=bg_image_path,
                width=width,
                height=height,
                scene_index=index,
                narration=str(scene.get("narration") or ""),
            )

            # Cinematic overlay: dark gradient at bottom for text readability
            if settings.enable_cinematic_overlay:
                img = self._add_cinematic_overlay(img, width, height)

            draw = ImageDraw.Draw(img)
            accent_h = 0  # kept as 0 so any later reference stays harmless

            

            # PRIMARY: narration text — what the voice is saying
            narration_raw = str(
                scene.get("narration") or scene.get("description") or ""
            ).strip()
            # Always sanitize — strip emojis/hashtags that must not appear in captions
            narration = _clean_caption(narration_raw)

            if bake_captions and narration:
                # When an AI background image is in use, skip the centred
                # narration block — it clutters a photographic image.  The
                # caption bar at the bottom already shows the text clearly.
                if bg_image_path is None:
                    self._draw_wrapped_text_centered(
                        draw=draw,
                        text=narration[:500],
                        font=narration_font,
                        canvas_width=width,
                        canvas_height=height,
                        color=(235, 242, 255),
                        max_width=width - 100,
                        line_spacing=14,
                        max_lines=10,
                        vertical_offset=-50,
                    )

                # Caption bar at the bottom — styled like real YouTube subtitles
                # Always rendered regardless of background type.
                self._draw_caption_bar(
                    img=img,
                    draw=draw,
                    text=narration[:200],
                    font=visual_font,
                    canvas_width=width,
                    canvas_height=height,
                    max_width=width - 80,
                )

            frame_path = frames_dir / f"scene_{index:03d}.png"
            img.save(str(frame_path), "PNG", optimize=True)
            frame_paths.append(frame_path)

        return frame_paths

    def _make_background(
        self,
        bg_image_path: Optional[str],
        width: int,
        height: int,
        scene_index: int = 0,
        narration: str = "",
    ):
        """Return a PIL Image sized (width, height) to use as the scene background.

        When *bg_image_path* points to a valid image file the source is
        centre-cropped to fill the target resolution (cover behaviour, no
        stretch/distortion).  Falls back to a professional gradient card if
        the path is missing, unreadable, or not a valid image.
        """
        from PIL import Image, ImageDraw, ImageFilter

        if bg_image_path:
            try:
                src = Image.open(bg_image_path).convert("RGB")
                src_w, src_h = src.size
                # Scale uniformly so the image fully covers the canvas
                scale = max(width / src_w, height / src_h)
                new_w = max(width, int(src_w * scale))
                new_h = max(height, int(src_h * scale))
                src = src.resize((new_w, new_h), Image.LANCZOS)
                # Centre-crop to exact canvas size
                left = (new_w - width) // 2
                top = (new_h - height) // 2
                img = src.crop((left, top, left + width, top + height))
                logger.debug(
                    "AI background image composited",
                    path=bg_image_path,
                    src_size=f"{src_w}x{src_h}",
                    canvas=f"{width}x{height}",
                )
                return img
            except Exception as exc:
                logger.warning(
                    "Could not load scene background image; using gradient fallback.",
                    path=bg_image_path,
                    error=str(exc),
                )

        # Professional gradient fallback — palette derived from scene index + narration
        return self._make_gradient_background(width, height, scene_index, narration)

    def _make_gradient_background(
        self,
        width: int,
        height: int,
        scene_index: int,
        narration: str,
    ):
        """Create a branded gradient background with narration text overlay.

        Used whenever AI image generation fails or is skipped — ensures the
        scene is never a blank/empty screen.
        """
        from PIL import Image, ImageDraw, ImageFilter
        import hashlib
        import textwrap

        palettes = [
            ((8, 15, 40), (25, 55, 120)),       # deep blue
            ((18, 8, 38), (75, 25, 95)),        # deep purple
            ((8, 28, 18), (15, 75, 55)),        # forest teal
            ((28, 12, 8), (95, 45, 15)),        # warm amber
            ((8, 22, 32), (18, 65, 95)),        # ocean blue
            ((35, 8, 25), (100, 20, 60)),       # crimson
            ((10, 30, 30), (25, 85, 80)),       # cyan
        ]
        # Use scene index for consistent palette per scene within a run
        seed = int(hashlib.md5(narration[:32].encode()).hexdigest()[:4], 16)
        c1, c2 = palettes[(scene_index + seed) % len(palettes)]
        accent = palettes[(scene_index + seed + 1) % len(palettes)][1]

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        for y in range(height):
            t = y / max(height - 1, 1)
            # Smoothstep easing
            t_s = t * t * (3 - 2 * t)
            r = int(c1[0] + (c2[0] - c1[0]) * t_s)
            g = int(c1[1] + (c2[1] - c1[1]) * t_s)
            b = int(c1[2] + (c2[2] - c1[2]) * t_s)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        img = img.filter(ImageFilter.GaussianBlur(radius=2))

        # Overlay narration text so the scene is never blank
        if narration and narration.strip():
            draw = ImageDraw.Draw(img)
            font_size = max(36, int(width * 0.06))
            font = self._load_font(bold=True, size=font_size)

            # Wrap text to fit canvas width (leave 10% padding each side)
            chars_per_line = max(12, int(width * 0.9 / (font_size * 0.55)))
            lines = textwrap.wrap(narration.strip(), width=chars_per_line)[:5]
            text = "\n".join(lines)

            # Measure total text block height
            test_bbox = draw.textbbox((0, 0), text, font=font)
            text_h = test_bbox[3] - test_bbox[1]

            # Draw semi-transparent pill behind text
            pad_x, pad_y = int(width * 0.06), int(height * 0.025)
            box_top = (height - text_h) // 2 - pad_y
            box_bot = (height + text_h) // 2 + pad_y
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            ov_draw.rectangle(
                [(pad_x // 2, box_top), (width - pad_x // 2, box_bot)],
                fill=(0, 0, 0, 160),
            )
            img = img.convert("RGBA")
            img = Image.alpha_composite(img, overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Draw accent line above text block
            draw.rectangle(
                [(pad_x, box_top), (pad_x + int(width * 0.12), box_top + 4)],
                fill=accent,
            )

            # Draw text centered
            draw.multiline_text(
                (width // 2, height // 2),
                text,
                font=font,
                fill=(255, 255, 255),
                anchor="mm",
                align="center",
                spacing=int(font_size * 0.3),
            )

        return img

    def _add_cinematic_overlay(self, img, width: int, height: int):
        """Add a dark gradient overlay at the bottom of the frame.

        Ensures text captions remain readable regardless of image content.
        Also adds a subtle top vignette for cinematic feel.
        """
        from PIL import Image, ImageDraw

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Bottom gradient: transparent → dark over the lower 45% of the frame
        gradient_height = int(height * 0.45)
        gradient_start = height - gradient_height
        for y in range(gradient_start, height):
            alpha = int(185 * (y - gradient_start) / gradient_height)
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        # Subtle top vignette (first 15% of frame)
        top_h = int(height * 0.15)
        for y in range(top_h):
            alpha = int(80 * (1.0 - y / top_h))
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        # Subtle side vignettes
        side_w = int(width * 0.12)
        for x in range(side_w):
            alpha = int(60 * (1.0 - x / side_w))
            draw.line([(x, 0), (x, height)], fill=(0, 0, 0, alpha))
            draw.line([(width - 1 - x, 0), (width - 1 - x, height)], fill=(0, 0, 0, alpha))

        img_rgba = img.convert("RGBA")
        result = Image.alpha_composite(img_rgba, overlay)
        return result.convert("RGB")

    def _make_watermark_clip(self, width: int, height: int, duration: float):
        """
        Persistent low-opacity channel logo shown for the entire video.
        Returns None (skips silently) if no watermark image is configured
        or the file doesn't exist — this is optional branding, never a
        reason to fail a render.
        """
        from moviepy import ImageClip

        watermark_path = getattr(settings, "watermark_path", "")
        if not watermark_path or not Path(watermark_path).exists():
            return None

        wm_w = int(width * getattr(settings, "watermark_size_pct", 0.14))
        clip = ImageClip(watermark_path).resized(width=wm_w)
        clip = clip.with_opacity(getattr(settings, "watermark_opacity", 0.55))
        clip = clip.with_duration(duration)

        margin = getattr(settings, "watermark_margin_px", 20)
        position_map = {
            "top-right": (width - clip.w - margin, margin),
            "top-left": (margin, margin),
            "bottom-right": (width - clip.w - margin, height - clip.h - margin),
            "bottom-left": (margin, height - clip.h - margin),
        }
        pos = position_map.get(
            getattr(settings, "watermark_position", "top-right"),
            position_map["top-right"],
        )
        return clip.with_position(pos)

    def _make_end_card_clip(self, text: str, width: int, height: int, duration: float):
        """
        A short CTA card ("FOLLOW FOR MORE") shown only for the closing
        seconds of the video. Reuses the same measured-width text wrap
        as the hook overlay and caption bar to avoid edge clipping.
        """
        from PIL import Image, ImageDraw
        from moviepy import ImageClip
        import numpy as np

        if not text or not text.strip():
            return None

        font = self._load_font(bold=True, size=int(height * 0.05))
        max_line_width = width - 80

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        words = text.strip().upper().split()
        lines: list[str] = []
        current = ""
        for w in words:
            candidate = (current + " " + w).strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if current and (bbox[2] - bbox[0]) > max_line_width:
                lines.append(current)
                current = w
            else:
                current = candidate
        if current:
            lines.append(current)

        line_h = int(height * 0.05) + 14
        block_h = len(lines) * line_h + 32
        center_y = height // 2 - block_h // 2

        bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg)
        bg_draw.rounded_rectangle(
            [(40, center_y), (width - 40, center_y + block_h)],
            radius=12,
            fill=(0, 0, 0, 170),
        )
        img = Image.alpha_composite(img, bg)
        draw = ImageDraw.Draw(img)

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            y = center_y + 16 + i * line_h
            self._draw_text_with_shadow(
                draw, line, (x, y), font, fill=(255, 255, 255),
            )

        return ImageClip(np.array(img)).with_duration(duration)

    def _make_hook_overlay_clip(
        self,
        text: str,
        width: int,
        height: int,
        duration: float,
    ):
        """
        Render a bold hook headline shown only for the opening seconds of
        the video — distinct from the karaoke narration captions at the
        bottom. This is what a viewer sees in the first ~1-1.5s, before
        they've processed any audio, and is the single biggest lever for
        Shorts retention (most swipe-away decisions happen in that window).

        Positioned in the upper third so it never overlaps the caption
        bar at the bottom of the frame.
        """
        from PIL import Image, ImageDraw
        from moviepy import ImageClip
        import numpy as np

        if not text or not text.strip():
            return None

        font = self._load_font(bold=True, size=int(height * 0.045))
        max_line_width = width - 80

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Wrap by measured width, same approach as the caption bar fix —
        # a fixed word count per line causes edge clipping on long words.
        words = text.strip().upper().split()
        lines: list[str] = []
        current = ""
        for w in words:
            candidate = (current + " " + w).strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if current and (bbox[2] - bbox[0]) > max_line_width:
                lines.append(current)
                current = w
            else:
                current = candidate
        if current:
            lines.append(current)

        line_h = int(height * 0.045) + 14
        block_h = len(lines) * line_h + 28
        top = int(height * 0.08)

        bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg)
        bg_draw.rounded_rectangle(
            [(24, top), (width - 24, top + block_h)],
            radius=10,
            fill=(0, 0, 0, 150),
        )
        img = Image.alpha_composite(img, bg)
        draw = ImageDraw.Draw(img)

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            y = top + 14 + i * line_h
            self._draw_text_with_shadow(
                draw, line, (x, y), font, fill=(255, 215, 0),
            )

        clip = ImageClip(np.array(img)).with_duration(duration)
        return clip

    def _load_font(self, bold: bool, size: int):
        from PIL import ImageFont

        candidates = []
        if bold:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf",
                "arialbd.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "arial.ttf",
            ]

        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue

        return ImageFont.load_default()

    def _draw_text_with_shadow(
        self,
        draw,
        text: str,
        position: tuple[int, int],
        font,
        fill: tuple,
        shadow_color: tuple = (0, 0, 0),
        shadow_offset: tuple[int, int] = (2, 2),
    ) -> None:
        """Draw text with a drop shadow for depth and readability."""
        x, y = position
        sx, sy = shadow_offset
        draw.text((x + sx, y + sy), text, fill=shadow_color, font=font)
        draw.text((x, y), text, fill=fill, font=font)

    def _draw_caption_bar(
        self,
        img,
        draw,
        text: str,
        font,
        canvas_width: int,
        canvas_height: int,
        max_width: int,
    ) -> None:
        """
        Draws a YouTube-style caption bar near the bottom of the frame.
        Semi-transparent dark background, white text with stroke, max 2 lines.
        Profile "modern" adds text stroke for extra legibility.
        """
        from PIL import Image, ImageDraw

        if not text:
            return

        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= 2:
                    break
        if current and len(lines) < 2:
            lines.append(current)

        lines = lines[:2]
        if not lines:
            return

        try:
            line_height = font.size + 10
        except AttributeError:
            line_height = 30

        padding_v = 16
        padding_h = 20
        bar_height = len(lines) * line_height + padding_v * 2
        bar_top = canvas_height - bar_height - 30  # 30px above bottom accent

        # Draw rounded semi-transparent background using a separate RGBA layer
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

        # Re-draw text on top after compositing
        draw2 = ImageDraw.Draw(img)
        y = bar_top + padding_v

        use_stroke = settings.text_style_profile in ("modern", "bold")
        stroke_width = 2 if settings.text_style_profile == "bold" else 1

        for line in lines:
            bbox = draw2.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (canvas_width - line_w) // 2

            if use_stroke:
                # Draw stroke (outline) by rendering text in dark colour at offsets
                for dx, dy in [(-stroke_width, 0), (stroke_width, 0),
                               (0, -stroke_width), (0, stroke_width)]:
                    draw2.text((x + dx, y + dy), line, fill=(0, 0, 0), font=font)

            draw2.text((x, y), line, fill=(255, 255, 255), font=font)
            y += line_height

    def _draw_wrapped_text_centered(
        self,
        draw,
        text: str,
        font,
        canvas_width: int,
        canvas_height: int,
        color: tuple,
        max_width: int,
        line_spacing: int = 14,
        max_lines: int = 10,
        vertical_offset: int = 0,
    ) -> None:
        if not text:
            return

        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        lines = lines[:max_lines]

        try:
            line_height = font.size + line_spacing
        except AttributeError:
            line_height = 36

        total_block_height = len(lines) * line_height
        start_y = (canvas_height - total_block_height) / 2 + vertical_offset

        use_shadow = settings.text_style_profile in ("modern", "bold")

        y = start_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (canvas_width - line_w) // 2
            if use_shadow:
                draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
            draw.text((x, y), line, fill=color, font=font)
            y += line_height

    def _draw_wrapped_text(
        self,
        draw,
        text: str,
        font,
        canvas_width: int,
        start_y: float,
        color: tuple,
        max_width: int,
        line_spacing: int = 12,
        max_lines: int = 8,
    ) -> None:
        if not text:
            return

        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        try:
            line_height = font.size + line_spacing
        except AttributeError:
            line_height = 36

        y = start_y
        for line in lines[:max_lines]:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            draw.text(((canvas_width - line_w) // 2, y), line, fill=color, font=font)
            y += line_height

    # ------------------------------------------------------------------
    # Karaoke animated captions
    # ------------------------------------------------------------------

    def _make_karaoke_clip(
        self,
        frame_path: Path,
        scene: dict,
        scene_start: float,
        duration: float,
        width: int,
        height: int,
    ):
        """
        Create a MoviePy VideoClip with animated word-highlight captions.

        Each frame is generated by PIL: the background PNG is overlaid with a
        caption bar where the currently-spoken word is highlighted in gold and
        all other words are white.  This replaces the static baked-in caption.

        Requires Pillow + numpy (both already installed).  Falls back to a
        plain ImageClip on any failure so the pipeline never hard-fails.
        """
        try:
            import numpy as np
            from PIL import Image, ImageDraw
            from moviepy import VideoClip

            words: list[dict] = scene.get("word_timestamps", [])
            narration = _clean_caption(str(scene.get("narration") or ""))

            # Scale fonts proportionally
            base = height / 1280
            caption_font = self._load_font(bold=True, size=max(28, int(40 * base)))

            # Pre-load background image as numpy array
            bg_pil = Image.open(str(frame_path)).convert("RGB")
            # Ensure correct size
            if bg_pil.size != (width, height):
                bg_pil = bg_pil.resize((width, height), Image.LANCZOS)
            bg_array = np.array(bg_pil)

            # Highlight / inactive colours from config
            hl_hex = settings.karaoke_highlight_color.lstrip("#")
            base_hex = settings.karaoke_base_color.lstrip("#")
            hl_color = tuple(int(hl_hex[i:i+2], 16) for i in (0, 2, 4))
            base_color = tuple(int(base_hex[i:i+2], 16) for i in (0, 2, 4))

            def _make_frame(t: float) -> np.ndarray:
                abs_t = scene_start + t

                # Find the active word at this absolute timestamp
                active_idx = -1
                for idx, w in enumerate(words):
                    if w["start"] <= abs_t <= w["end"]:
                        active_idx = idx
                        break

                # Copy background
                frame = bg_array.copy()
                img = Image.fromarray(frame)
                draw = ImageDraw.Draw(img)

                # Draw karaoke caption bar
                self._draw_karaoke_bar(
                    img=img,
                    draw=draw,
                    words=words,
                    active_idx=active_idx,
                    font=caption_font,
                    width=width,
                    height=height,
                    hl_color=hl_color,
                    base_color=base_color,
                )
                return np.array(img)

            clip = VideoClip(_make_frame, duration=duration)
            return clip

        except Exception as exc:
            logger.warning(
                "Karaoke clip creation failed; falling back to static ImageClip",
                error=str(exc),
            )
            from moviepy import ImageClip
            return ImageClip(str(frame_path)).with_duration(duration)

    def _draw_karaoke_bar(
        self,
        img,
        draw,
        words: list[dict],
        active_idx: int,
        font,
        width: int,
        height: int,
        hl_color: tuple = (255, 215, 0),
        base_color: tuple = (255, 255, 255),
    ) -> None:
        """
        Draw an animated karaoke caption bar near the bottom of the frame.

        Shows all words of the current scene with the active word highlighted
        in gold.  Words are grouped into lines of ≤6 words each.
        """
        from PIL import Image, ImageDraw
        import math

        if not words:
            return

        try:
            font_size = font.size
        except AttributeError:
            font_size = 32

        # Group words into display lines by MEASURED pixel width, not a
        # fixed word count. A fixed count (e.g. 6 words/line regardless
        # of length) causes long words like "instruments" or "iconic" to
        # push the line past the frame edges — the text gets visually
        # clipped/cut off, which is illegible and hurts retention.
        # Leave the same side margins as the caption bar itself (16px
        # each side) plus a little breathing room for the shadow offset.
        max_line_width = width - 64
        lines: list[list[dict]] = []
        current_line: list[dict] = []
        current_text = ""
        # Need a draw handle to measure text before the bar background
        # is composited below — the one passed in works fine for this.
        for w in words:
            candidate_text = (current_text + " " + w["word"]).strip()
            bbox = draw.textbbox((0, 0), candidate_text, font=font)
            candidate_width = bbox[2] - bbox[0]
            if current_line and candidate_width > max_line_width:
                lines.append(current_line)
                current_line = [w]
                current_text = w["word"]
            else:
                current_line.append(w)
                current_text = candidate_text
        if current_line:
            lines.append(current_line)

        line_h = font_size + 10
        bar_padding = 14
        total_bar_h = len(lines) * line_h + bar_padding * 2
        bar_top = height - total_bar_h - int(height * 0.04)

        # Semi-transparent dark background bar
        bar_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar_overlay)
        bar_draw.rounded_rectangle(
            [(16, bar_top), (width - 16, bar_top + total_bar_h)],
            radius=8,
            fill=(0, 0, 0, 160),
        )
        img_rgba = img.convert("RGBA")
        img_rgba = Image.alpha_composite(img_rgba, bar_overlay)
        img.paste(img_rgba.convert("RGB"))

        # Redraw to get a fresh draw handle after paste
        draw = ImageDraw.Draw(img)

        # Track global word index across lines
        global_idx = 0
        for line_num, line_words in enumerate(lines):
            # Build rendered tokens with bboxes to calculate line width
            tokens = [w["word"] for w in line_words]
            total_line = " ".join(tokens)
            bbox = draw.textbbox((0, 0), total_line, font=font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            y = bar_top + bar_padding + line_num * line_h

            for word_dict in line_words:
                token = word_dict["word"]
                color = hl_color if global_idx == active_idx else base_color

                # Shadow
                draw.text((x + 2, y + 2), token, fill=(0, 0, 0), font=font)
                draw.text((x, y), token, fill=color, font=font)

                # Advance x position
                w_bbox = draw.textbbox((0, 0), token + " ", font=font)
                x += w_bbox[2] - w_bbox[0]
                global_idx += 1

    # ------------------------------------------------------------------
    # Ken Burns effect
    # ------------------------------------------------------------------

    def _apply_ken_burns(self, clip, width: int, height: int, scene_index: int):
        """Apply a subtle Ken Burns zoom/pan effect to an ImageClip.

        Alternates between zoom-in and zoom-out per scene for variety.
        The clip is zoomed and then centre-cropped back to canvas size so
        there are no black borders during the effect.
        """
        try:
            zoom_amount = 0.04  # 4% zoom over the full clip duration
            dur = max(clip.duration, 0.1)

            if scene_index % 2 == 0:
                # Zoom in: starts at 1.0, ends at 1.0 + zoom_amount
                zoom_fn = lambda t: 1.0 + zoom_amount * (t / dur)
            else:
                # Zoom out: starts at 1.0 + zoom_amount, ends at 1.0
                zoom_fn = lambda t: 1.0 + zoom_amount * (1.0 - t / dur)

            return (
                clip.resized(zoom_fn)
                .cropped(x_center=width / 2, y_center=height / 2, width=width, height=height)
            )
        except Exception as exc:
            logger.debug("Ken Burns effect failed; using static clip.", error=str(exc))
            return clip

    # ------------------------------------------------------------------
    # Video assembly
    # ------------------------------------------------------------------

    def _assemble_video(
        self,
        frame_paths: list[Path],
        scenes: list[dict[str, Any]],
        audio_path: Optional[str],
        output_path: Path,
        resolution: tuple[int, int] = _LONG_RESOLUTION,
        karaoke_mode: bool = False,
        presenter_path: Optional[str] = None,
        hook_text: Optional[str] = None,
    ) -> tuple[float, int]:
        from moviepy import (
            AudioFileClip,
            ImageClip,
            CompositeVideoClip,
            concatenate_videoclips,
            vfx,
        )

        width, height = resolution
        fade_dur = _CROSSFADE_DURATION if settings.enable_transitions else 0.0
        ken_burns = settings.enable_ken_burns

        # Load audio first so we know its real duration
        audio_clip = None
        audio_duration: Optional[float] = None

        if audio_path and Path(audio_path).exists():
            try:
                audio_clip = AudioFileClip(audio_path)
                audio_duration = audio_clip.duration
                logger.info(
                    "Voice audio loaded",
                    audio_path=audio_path,
                    duration=round(audio_duration, 2),
                )
            except Exception as exc:
                logger.warning("Could not load audio track", error=str(exc), audio_path=audio_path)
        elif audio_path:
            logger.warning("Voice audio_path set but file not found on disk.", audio_path=audio_path)
        else:
            logger.info("No voice audio for this script; rendering silent video.")

        # ------------------------------------------------------------------
        # Scene duration strategy (best available, in priority order):
        #
        # 1. WHISPER start_seconds — exact boundaries from faster-whisper.
        # 2. PROPORTIONAL — scale word-count durations to fit audio.
        # 3. NOMINAL — raw duration_seconds as-is (silent video).
        # ------------------------------------------------------------------
        if audio_duration is not None and all(
            "start_seconds" in s for s in scenes
        ):
            logger.info("========== RENDER TIMING ==========")

            clips = []

            last_scene = scenes[-1]
            if "end_seconds" in last_scene:
                effective_duration = min(
                    audio_duration,
                    float(last_scene["end_seconds"]) + 0.8,
                )
            else:
                effective_duration = audio_duration

            logger.info(
                "Effective video duration (narration end + tail)",
                audio_total=round(audio_duration, 2),
                effective=round(effective_duration, 2),
            )

            for i, (frame_path, scene) in enumerate(zip(frame_paths, scenes)):
                start = float(scene["start_seconds"])

                if i < len(scenes) - 1:
                    next_start = float(scenes[i + 1]["start_seconds"])
                    duration = max(0.5, next_start - start)
                else:
                    duration = max(0.5, effective_duration - start)

                logger.info(
                    f"Scene {i + 1}: "
                    f"Start={start:.2f}s  "
                    f"Duration={duration:.2f}s  "
                    f"End={start + duration:.2f}s"
                )

                if karaoke_mode and scene.get("word_timestamps"):
                    clip = self._make_karaoke_clip(
                        frame_path=frame_path,
                        scene=scene,
                        scene_start=start,
                        duration=duration,
                        width=width,
                        height=height,
                    )
                else:
                    clip = ImageClip(str(frame_path)).with_duration(duration)

                if ken_burns:
                    clip = self._apply_ken_burns(clip, width, height, i)

                if fade_dur > 0 and i > 0:
                    actual_start = max(0.0, start - fade_dur)
                    clip = (
                        clip.with_start(actual_start)
                        .with_duration(duration + fade_dur)
                        .with_effects([vfx.CrossFadeIn(fade_dur)])
                    )
                else:
                    clip = clip.with_start(start)

                clips.append(clip)

            logger.info(f"Audio duration : {audio_duration:.2f}s")
            logger.info("==============================")
            logger.info(
                "Using Whisper start_seconds for exact scene transitions.",
                scenes=len(clips),
            )

            video = CompositeVideoClip(clips, size=(width, height))
            video = video.with_duration(effective_duration)

        else:
            raw_durations = [
                max(0.5, float(scene.get("duration_seconds", 5) or 5))
                for scene in scenes
            ]
            if audio_duration is not None:
                total_raw = sum(raw_durations)
                scene_durations = [
                    max(0.5, (d / total_raw) * audio_duration)
                    for d in raw_durations
                ]
            else:
                scene_durations = [float(d) for d in raw_durations]

            raw_clips = []
            running_start = 0.0
            for i, (fp, scene, dur) in enumerate(zip(frame_paths, scenes, scene_durations)):
                if karaoke_mode and scene.get("word_timestamps"):
                    clip = self._make_karaoke_clip(
                        frame_path=fp,
                        scene=scene,
                        scene_start=running_start,
                        duration=dur,
                        width=width,
                        height=height,
                    )
                else:
                    clip = ImageClip(str(fp)).with_duration(dur)
                if ken_burns:
                    clip = self._apply_ken_burns(clip, width, height, i)
                raw_clips.append(clip)
                running_start += dur

            if fade_dur > 0 and len(raw_clips) > 1:
                faded = [raw_clips[0]]
                for clip in raw_clips[1:]:
                    faded.append(clip.with_effects([vfx.CrossFadeIn(fade_dur)]))
                video = concatenate_videoclips(
                    faded,
                    method="compose",
                    padding=-fade_dur,
                )
            else:
                video = concatenate_videoclips(raw_clips, method="compose")

            clips = raw_clips

        # ------------------------------------------------------------------
        # Attach voice/music audio track (own try/except — fully closed
        # before any other code runs)
        # ------------------------------------------------------------------
        if audio_clip is not None:
            try:
                video_dur = float(video.duration)
                if audio_clip.duration > video_dur + 0.1:
                    audio_clip = audio_clip.subclipped(0, video_dur)
                video = video.with_audio(audio_clip)
                logger.info(
                    "Voice audio attached to video",
                    audio_path=audio_path,
                    audio_trimmed_to=round(video_dur, 2),
                )
            except Exception as exc:
                logger.warning("Could not attach audio to video clip", error=str(exc))

        # ------------------------------------------------------------------
        # Picture-in-picture presenter overlay (optional, own try/except,
        # fully separate from the audio-attach block above)
        # ------------------------------------------------------------------
        if presenter_path and Path(presenter_path).exists():
            try:
                from moviepy import VideoFileClip, vfx

                presenter_clip = VideoFileClip(presenter_path)

                pip_w = int(width * settings.presenter_pip_size_pct)
                pip_h = int(pip_w * presenter_clip.h / presenter_clip.w)
                presenter_clip = presenter_clip.resized(width=pip_w)

                margin = settings.presenter_pip_margin_px
                position_map = {
                    "bottom-right": (width - pip_w - margin, height - pip_h - margin),
                    "bottom-left": (margin, height - pip_h - margin),
                    "top-right": (width - pip_w - margin, margin),
                    "top-left": (margin, margin),
                }
                pip_pos = position_map.get(
                    settings.presenter_pip_position, position_map["bottom-right"]
                )

                base_duration = float(video.duration)
                if presenter_clip.duration < base_duration:
                    presenter_clip = presenter_clip.with_effects([vfx.Loop(duration=base_duration)])
                else:
                    presenter_clip = presenter_clip.subclipped(0, base_duration)

                presenter_clip = presenter_clip.with_position(pip_pos)

                video = CompositeVideoClip(
                    [video, presenter_clip], size=(width, height)
                )
                video = video.with_duration(base_duration)

                logger.info(
                    "Presenter PiP overlay composited",
                    pip_size=f"{pip_w}x{pip_h}",
                    position=settings.presenter_pip_position,
                )
            except Exception as exc:
                logger.warning(
                    "Presenter PiP overlay failed — rendering without it",
                    error=str(exc),
                )

        # ------------------------------------------------------------------
        # Hook headline overlay — first ~1.5s only, distinct from the
        # karaoke narration captions. This is what a viewer sees before
        # they've processed any audio, so it's the highest-leverage
        # retention element on the whole video.
        # ------------------------------------------------------------------
        if hook_text and getattr(settings, "hook_overlay_enabled", True):
            try:
                hook_duration = min(
                    getattr(settings, "hook_overlay_duration_s", 1.5),
                    float(video.duration),
                )
                hook_clip = self._make_hook_overlay_clip(
                    text=hook_text,
                    width=width,
                    height=height,
                    duration=hook_duration,
                )
                if hook_clip is not None:
                    hook_clip = hook_clip.with_start(0)
                    hook_base_duration = float(video.duration)
                    video = CompositeVideoClip([video, hook_clip], size=(width, height))
                    video = video.with_duration(hook_base_duration)
                    logger.info("Hook overlay composited", duration=hook_duration)
            except Exception as exc:
                logger.warning(
                    "Hook overlay failed — rendering without it", error=str(exc)
                )

        # ------------------------------------------------------------------
        # Channel watermark — persistent, low-opacity, whole video
        # ------------------------------------------------------------------
        if getattr(settings, "watermark_enabled", True):
            try:
                wm_duration = float(video.duration)
                watermark_clip = self._make_watermark_clip(width, height, wm_duration)
                if watermark_clip is not None:
                    watermark_clip = watermark_clip.with_start(0)
                    video = CompositeVideoClip([video, watermark_clip], size=(width, height))
                    video = video.with_duration(wm_duration)
                    logger.info("Watermark composited")
            except Exception as exc:
                logger.warning("Watermark failed — rendering without it", error=str(exc))

        # ------------------------------------------------------------------
        # End-card CTA — last ~1.5s only ("Follow for more")
        # ------------------------------------------------------------------
        if getattr(settings, "end_card_enabled", True):
            try:
                total_duration = float(video.duration)
                end_card_duration = min(
                    getattr(settings, "end_card_duration_s", 1.5), total_duration
                )
                end_card_clip = self._make_end_card_clip(
                    text=getattr(settings, "end_card_text", "FOLLOW FOR MORE"),
                    width=width,
                    height=height,
                    duration=end_card_duration,
                )
                if end_card_clip is not None:
                    end_card_clip = end_card_clip.with_start(total_duration - end_card_duration)
                    video = CompositeVideoClip([video, end_card_clip], size=(width, height))
                    video = video.with_duration(total_duration)
                    logger.info("End-card CTA composited", duration=end_card_duration)
            except Exception as exc:
                logger.warning("End-card CTA failed — rendering without it", error=str(exc))

        fps = _render_fps()
        preset = _render_preset()
        crf = _render_crf()

        logger.info(
            "Encoding video",
            preset=preset,
            fps=fps,
            crf=crf,
            quality_profile=settings.video_quality_preset,
        )

        # Explicit absolute temp-audio path. Without this, MoviePy derives
        # the temp filename from output_path's own resolution, which is
        # fragile when storage_local_path is relative (e.g. "./storage") —
        # it can end up resolving against the process's current working
        # directory instead of the intended storage folder, landing in a
        # location the app's non-root user can't write to.
        temp_audiofile = str((output_path.parent / f"{output_path.stem}_TEMP_MPY_audio.m4a").resolve())

        try:
            video.write_videofile(
                str(output_path.resolve()),
                fps=fps,
                codec="libx264",
                audio_codec="aac" if video.audio is not None else None,
                preset=preset,
                threads=_RENDER_THREADS,
                ffmpeg_params=["-crf", str(crf)],
                temp_audiofile=temp_audiofile if video.audio is not None else None,
                remove_temp=True,
                logger=None,
            )
            duration = float(video.duration)
        finally:
            video.close()
            for clip in clips:
                clip.close()
            if audio_clip is not None:
                audio_clip.close()

        file_size = output_path.stat().st_size if output_path.exists() else 0
        return duration, file_size
