"""Prefer script.cta for end-card overlay; honor end_card_duration_s.

Applied from app.main lifespan. Safe no-op if renderer API changes.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _display_text(cta_text: Optional[str]) -> str:
    fallback = getattr(settings, "end_card_text", "FOLLOW FOR MORE") or "FOLLOW FOR MORE"
    raw = (cta_text or "").strip() or fallback.strip()
    words = raw.split()
    if len(words) > 7:
        raw = " ".join(words[:7])
    return raw.upper()


def apply_end_cta_patch() -> None:
    try:
        from app.agents.video_agent.renderer import VideoRenderer
    except Exception as exc:
        logger.warning("End-CTA patch skipped — renderer import failed", error=str(exc))
        return

    if getattr(VideoRenderer, "_end_cta_patch_applied", False):
        return

    _orig_render = VideoRenderer.render
    _orig_make = VideoRenderer._make_end_card_clip

    def render(self, *args, cta_text: Optional[str] = None, **kwargs):
        self._pending_cta_text = cta_text
        return _orig_render(self, *args, **kwargs)

    def _make_end_card_clip(self, text: str, width: int, height: int, duration: float):
        pending = getattr(self, "_pending_cta_text", None)
        if pending:
            text = _display_text(pending)
        try:
            want = float(getattr(settings, "end_card_duration_s", 2.5) or 2.5)
            if duration < want:
                duration = min(want, duration * 2 if duration else want)
        except Exception:
            pass
        return _orig_make(self, text, width, height, duration)

    VideoRenderer.render = render  # type: ignore[method-assign]
    VideoRenderer._make_end_card_clip = _make_end_card_clip  # type: ignore[method-assign]
    VideoRenderer._end_cta_patch_applied = True  # type: ignore[attr-defined]
    logger.info("End-card CTA patch applied (prefer script.cta, duration from settings)")
