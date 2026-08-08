"""Skip bottom caption on first scene when top hook overlay is on.

Stops double-reading the same line (yellow headline + black caption bar)
in the first ~1.5–2s of Shorts.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_skip_hook_caption_patch() -> None:
    try:
        from app.agents.video_agent.renderer import VideoRenderer
    except Exception as exc:
        logger.warning("skip-hook-caption patch skipped", error=str(exc))
        return

    if getattr(VideoRenderer, "_skip_hook_caption_patched", False):
        return

    if not hasattr(VideoRenderer, "_render_scene_cards"):
        logger.warning("skip-hook-caption: _render_scene_cards missing")
        return

    _orig_cards = VideoRenderer._render_scene_cards

    def _render_scene_cards(self, *args, **kwargs):
        _orig_draw = self._draw_caption_bar
        calls = {"n": 0}

        def _draw_once(*a, **kw):
            calls["n"] += 1
            # First caption = first scene narration (usually = hook text)
            if calls["n"] == 1 and getattr(settings, "hook_overlay_enabled", True):
                return None
            return _orig_draw(*a, **kw)

        self._draw_caption_bar = _draw_once  # type: ignore[method-assign]
        try:
            return _orig_cards(self, *args, **kwargs)
        finally:
            self._draw_caption_bar = _orig_draw  # type: ignore[method-assign]

    VideoRenderer._render_scene_cards = _render_scene_cards  # type: ignore[method-assign]
    VideoRenderer._skip_hook_caption_patched = True  # type: ignore[attr-defined]
    logger.info("Skip first-scene caption under hook overlay applied")
