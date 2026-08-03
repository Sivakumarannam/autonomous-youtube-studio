"""Patch VideoRenderer caption bar to avoid edge clipping (Step 3)."""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_caption_clip_patch() -> None:
    try:
        from app.agents.video_agent.renderer import VideoRenderer
        from app.agents.video_agent.caption_bar import draw_caption_bar
    except Exception as exc:
        logger.warning("caption clip patch skipped", error=str(exc))
        return

    if getattr(VideoRenderer, "_caption_clip_patched", False):
        return

    def _draw_caption_bar(self, img, draw, text, font, canvas_width, canvas_height, max_width):
        # Widen default if caller still passes width-80
        if max_width >= canvas_width - 80:
            max_width = canvas_width - 96
        return draw_caption_bar(
            self, img, draw, text, font, canvas_width, canvas_height, max_width
        )

    VideoRenderer._draw_caption_bar = _draw_caption_bar  # type: ignore[method-assign]
    VideoRenderer._caption_clip_patched = True  # type: ignore[attr-defined]
    logger.info("Caption edge-clip patch applied (static bar)")
