"""Delete per-script image_cache files after VideoRenderer.render finishes.

Keeps Oracle free-tier disk from filling up with Pollinations/Pexels temps.
Applied from app.main lifespan (always; not only LOW_RAM).
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _cleanup_script_image_cache(script_id: str) -> None:
    cache_dir = Path(settings.storage_local_path) / "image_cache"
    if not cache_dir.is_dir() or not script_id:
        return
    removed = 0
    try:
        for p in cache_dir.glob(f"*{script_id}*"):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
                    removed += 1
                elif p.is_dir():
                    import shutil

                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
            except Exception:
                continue
        if removed:
            logger.info(
                "Cleaned image_cache for script",
                script_id=script_id,
                count=removed,
            )
    except Exception as exc:
        logger.warning("image_cache cleanup failed", error=str(exc), script_id=script_id)


def apply_image_cache_cleanup_patch() -> None:
    try:
        from app.agents.video_agent.renderer import VideoRenderer
    except Exception as exc:
        logger.warning("image_cache cleanup patch skipped", error=str(exc))
        return

    if getattr(VideoRenderer, "_image_cache_cleanup_applied", False):
        return

    _orig = VideoRenderer.render

    def render(self, script_id: str, *args, **kwargs):
        try:
            return _orig(self, script_id, *args, **kwargs)
        finally:
            _cleanup_script_image_cache(str(script_id))

    VideoRenderer.render = render  # type: ignore[method-assign]
    VideoRenderer._image_cache_cleanup_applied = True  # type: ignore[attr-defined]
    logger.info("Image-cache cleanup patch applied (after each render)")
