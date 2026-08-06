"""Ensure Kokoro always writes timings.json (including single-pass fallback).

Applied from low_ram_bootstrap when LOW_RAM_MODE is on.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_timings_fallback_patch() -> None:
    try:
        from app.agents.voice_agent import agent as va
    except Exception as exc:
        logger.warning("timings fallback patch skipped", error=str(exc))
        return

    if getattr(va.VoiceAgent, "_timings_fallback_patched", False):
        return

    _orig = va.VoiceAgent._kokoro_synthesise

    async def _kokoro_synthesise(self, text, file_path, gender="female", speed=1.0):
        ok = await _orig(self, text, file_path, gender, speed)
        if not ok:
            return False
        timings_path = Path(file_path).with_suffix(".timings.json")
        if timings_path.is_file() and timings_path.stat().st_size > 10:
            return True
        try:
            from pydub import AudioSegment  # type: ignore

            src = Path(file_path)
            if not src.is_file():
                return True
            dur = len(AudioSegment.from_file(str(src))) / 1000.0
        except Exception:
            dur = max(2.0, len((text or "").split()) * 0.35)
        try:
            from app.integrations.kokoro_tts import split_spoken_sentences

            rows = split_spoken_sentences(text) or [text]
        except Exception:
            rows = [text]
        n = max(1, len(rows))
        payload = {
            "sentences": [
                {
                    "text": s,
                    "start": float(i * (dur / n)),
                    "end": float((i + 1) * (dur / n)),
                }
                for i, s in enumerate(rows)
            ]
        }
        timings_path.write_text(json.dumps(payload), encoding="utf-8")
        logger.info(
            "Kokoro timings estimated (post-hoc fallback)",
            path=str(timings_path),
            duration_s=round(dur, 2),
            count=n,
        )
        return True

    va.VoiceAgent._kokoro_synthesise = _kokoro_synthesise  # type: ignore[method-assign]
    va.VoiceAgent._timings_fallback_patched = True  # type: ignore[attr-defined]
    logger.info("Kokoro timings fallback patch applied")
