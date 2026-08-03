"""Apply low-RAM safeguards at process start (Oracle Always Free ~1 GB).

Called from app.main lifespan when settings.low_ram_mode is True.
Skips faster-whisper so the OOM killer never fires during transcription.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_low_ram_patches() -> None:
    """No-op unless LOW_RAM_MODE=true."""
    if not settings.low_ram_mode:
        return

    import app.agents.video_agent.service as video_service

    def _skip_whisper(*_args, **_kwargs):
        logger.info("low_ram_mode: Whisper alignment skipped (word-count timing)")
        return None

    video_service.transcribe_sentences_from_audio = _skip_whisper  # type: ignore[assignment]

    logger.info(
        "LOW_RAM_MODE active — Whisper skipped; use static captions + light encode",
        video_quality_preset=settings.video_quality_preset,
        caption_style=settings.caption_style,
        enable_ken_burns=settings.enable_ken_burns,
        enable_transitions=settings.enable_transitions,
    )
