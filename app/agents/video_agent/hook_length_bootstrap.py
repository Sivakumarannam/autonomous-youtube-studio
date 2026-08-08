"""Shorten on-screen hook so it fits 2 lines (no edge clip).

Applied from app.main lifespan after video_hook_bootstrap.
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_WORDS = 6
_MAX_CHARS = 40


def _shorten_hook(text: str) -> str:
    t = " ".join((text or "").strip().split())
    if not t:
        return t
    # Prefer first sentence if long spoken hook
    for sep in (".", "!", "?"):
        if sep in t:
            first = t.split(sep)[0].strip()
            if 6 <= len(first) <= _MAX_CHARS + 8:
                t = first
                break
    words = t.upper().split()
    if len(words) > _MAX_WORDS:
        words = words[:_MAX_WORDS]
    out = " ".join(words)
    if len(out) > _MAX_CHARS:
        cut = out[: _MAX_CHARS - 1].rsplit(" ", 1)
        out = (cut[0] if cut else out[: _MAX_CHARS - 1]) + "…"
    return out


def apply_hook_length_patch() -> None:
    try:
        from app.agents.video_agent.renderer import VideoRenderer
    except Exception as exc:
        logger.warning("hook length patch skipped", error=str(exc))
        return

    if getattr(VideoRenderer, "_hook_length_patched", False):
        return

    _orig = VideoRenderer._make_hook_overlay_clip

    def _make_hook_overlay_clip(self, text, width, height, duration):
        short = _shorten_hook(text or "")
        return _orig(self, short, width, height, duration)

    VideoRenderer._make_hook_overlay_clip = _make_hook_overlay_clip  # type: ignore[method-assign]
    VideoRenderer._hook_length_patched = True  # type: ignore[attr-defined]
    logger.info("Hook overlay length patch applied (max %s words)", _MAX_WORDS)
