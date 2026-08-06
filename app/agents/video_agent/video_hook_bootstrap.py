"""Prefer spoken script.hook for on-screen overlay (monkeypatch render path).

Applied from app.main lifespan so the first ~1.5s headline uses the spoken
curiosity-gap hook instead of only seo_title. Falls back to seo_title when
the spoken hook is too long for the frame. Also applies hook length cap.
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_video_hook_overlay_patch() -> None:
    """Wrap VideoAgentService.run_for_script so render() gets a short hook."""
    try:
        from app.agents.video_agent import service as vas
    except Exception as exc:
        logger.warning("video hook patch skipped", error=str(exc))
        return

    if getattr(vas.VideoAgentService, "_hook_overlay_patched", False):
        return

    original = vas.VideoAgentService.run_for_script

    async def run_for_script(self, script, topic_title="", description="", script_type="long"):
        orig_render = self._renderer.render

        def render_wrapper(*args, **kwargs):
            hook = (getattr(script, "hook", None) or "").strip()
            seo = (getattr(script, "seo_title", None) or topic_title or "").strip()
            # Prefer short SEO title when spoken hook is a long sentence
            if seo and (not hook or len(hook.split()) > 10):
                kwargs["hook_text"] = seo
            elif hook:
                kwargs["hook_text"] = hook
            elif not kwargs.get("hook_text"):
                kwargs["hook_text"] = seo or topic_title
            return orig_render(*args, **kwargs)

        self._renderer.render = render_wrapper  # type: ignore[method-assign]
        try:
            return await original(self, script, topic_title, description, script_type)
        finally:
            self._renderer.render = orig_render  # type: ignore[method-assign]

    vas.VideoAgentService.run_for_script = run_for_script  # type: ignore[assignment]
    vas.VideoAgentService._hook_overlay_patched = True  # type: ignore[attr-defined]
    logger.info("Video hook overlay patch applied (prefer script.hook / short seo)")

    # Cap on-screen hook length (max 8 words) so text is not edge-clipped
    try:
        from app.agents.video_agent.hook_length_bootstrap import apply_hook_length_patch

        apply_hook_length_patch()
    except Exception as exc:
        logger.warning("hook length patch not applied", error=str(exc))
