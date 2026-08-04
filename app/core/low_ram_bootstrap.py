"""Apply low-RAM safeguards at process start (Oracle Always Free ~1 GB).

Called from app.main lifespan when settings.low_ram_mode is True.
Skips faster-whisper so the OOM killer never fires during transcription.

Instead of pure word-count timing, prefers sentence timings written next to
the voice MP3 by Kokoro (``*.timings.json``) when available.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _timings_from_sidecar(
    audio_path: str,
    sentences: list[str],
) -> tuple[list[tuple[float, float]], list[list[dict]]] | None:
    """Load ``{audio}.timings.json`` written during Kokoro synthesis."""
    if not audio_path or not sentences:
        return None

    path = Path(audio_path)
    candidates = [
        path.with_suffix(".timings.json"),
        path.with_name(path.stem.replace("_mixed", "") + ".timings.json"),
    ]
    for c in list(candidates):
        if "_kokoro" in c.name:
            candidates.append(c.with_name(c.name.replace("_kokoro", "")))

    data = None
    used = None
    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                used = c
                break
            except Exception:
                continue
    if not data:
        return None

    raw = data.get("sentences") or data.get("timings") or []
    if not raw:
        return None

    timestamps: list[tuple[float, float]] = []
    word_ts: list[list[dict]] = []

    for i, sent in enumerate(sentences):
        if i < len(raw):
            item = raw[i]
            if isinstance(item, dict):
                start = float(item.get("start", 0.0))
                end = float(item.get("end", start + 1.0))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                start, end = float(item[0]), float(item[1])
            else:
                return None
        else:
            prev_end = timestamps[-1][1] if timestamps else 0.0
            start, end = prev_end, prev_end + 1.0

        real_dur = max(0.4, end - start)
        timestamps.append((start, end))

        words = sent.split()
        if words:
            n = len(words)
            word_ts.append(
                [
                    {
                        "word": w,
                        "start": start + (j / n) * real_dur,
                        "end": start + ((j + 1) / n) * real_dur,
                    }
                    for j, w in enumerate(words)
                ]
            )
        else:
            word_ts.append([])

    if len(timestamps) != len(sentences):
        return None

    logger.info(
        "low_ram_mode: using Kokoro sentence timings sidecar",
        path=str(used),
        sentences=len(sentences),
    )
    return timestamps, word_ts


def apply_low_ram_patches() -> None:
    """No-op unless LOW_RAM_MODE=true."""
    if not settings.low_ram_mode:
        return

    import app.agents.video_agent.service as video_service

    def _align_without_whisper(audio_path: str, sentences: list[str], *_args, **_kwargs):
        result = _timings_from_sidecar(audio_path, sentences)
        if result is not None:
            return result
        logger.info("low_ram_mode: Whisper skipped; no timings sidecar — word-count timing")
        return None

    video_service.transcribe_sentences_from_audio = _align_without_whisper  # type: ignore[assignment]

    logger.info(
        "LOW_RAM_MODE active — Whisper skipped; use static captions + light encode",
        video_quality_preset=settings.video_quality_preset,
        caption_style=settings.caption_style,
        enable_ken_burns=settings.enable_ken_burns,
        enable_transitions=settings.enable_transitions,
    )
