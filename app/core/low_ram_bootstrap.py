"""Apply low-RAM safeguards at process start (Oracle Always Free ~1 GB).

Called from app.main lifespan when settings.low_ram_mode is True.
Skips faster-whisper so the OOM killer never fires during transcription.

Instead of pure word-count timing, prefers sentence timings written next to
the voice MP3 by Kokoro (``*.timings.json``) when available.

Long-form is allowed under LOW_RAM with hard caps on scene count and duration.
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
    stems = {
        path.stem,
        path.stem.replace("_mixed", ""),
        path.stem.replace("_kokoro", ""),
        path.stem.replace("_mixed", "").replace("_kokoro", ""),
    }
    candidates: list[Path] = []
    for stem in stems:
        candidates.append(path.with_name(stem + ".timings.json"))
        candidates.append(path.parent / f"{stem}.timings.json")
    # Any sibling timings for same uuid prefix
    prefix = path.stem.split("_")[0]
    if len(prefix) >= 8:
        candidates.extend(sorted(path.parent.glob(f"{prefix}*.timings.json")))

    data = None
    used = None
    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key in seen:
            continue
        seen.add(key)
        if not c.is_file():
            continue
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

    # Parse raw timing rows
    parsed: list[tuple[float, float, str]] = []
    for item in raw:
        if isinstance(item, dict):
            start = float(item.get("start", item.get("start_seconds", 0.0)))
            end = float(item.get("end", item.get("end_seconds", start + 1.0)))
            text = str(item.get("text") or "")
            parsed.append((start, max(start + 0.4, end), text))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            start, end = float(item[0]), float(item[1])
            parsed.append((start, max(start + 0.4, end), ""))

    if not parsed:
        return None

    timestamps: list[tuple[float, float]] = []
    word_ts: list[list[dict]] = []

    # Map scene sentences onto Kokoro rows (index-aligned; stretch if counts differ)
    n_sent = len(sentences)
    n_raw = len(parsed)
    for i, sent in enumerate(sentences):
        if n_raw == n_sent:
            start, end, _ = parsed[i]
        elif n_raw > 0:
            # Proportional map when split counts differ
            j0 = int(i * n_raw / n_sent)
            j1 = int((i + 1) * n_raw / n_sent) - 1
            j0 = min(max(j0, 0), n_raw - 1)
            j1 = min(max(j1, j0), n_raw - 1)
            start = parsed[j0][0]
            end = parsed[j1][1]
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
        kokoro_rows=n_raw,
        matched=n_sent == n_raw,
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

    # Cap long-form scene count / duration under LOW_RAM (still allows long)
    _orig_resolve = video_service.VideoAgentService._resolve_scenes

    async def _resolve_scenes_capped(self, script_id, output, script, audio_path=None):
        scenes = await _orig_resolve(self, script_id, output, script, audio_path=audio_path)
        script_type = str(getattr(script, "script_type", "") or "").lower()
        if script_type != "long":
            return scenes
        if not getattr(settings, "allow_long_form_on_low_ram", True):
            from app.core.exceptions import PipelineError

            raise PipelineError(
                "Long-form is disabled while LOW_RAM_MODE is on "
                "(set ALLOW_LONG_FORM_ON_LOW_RAM=true to enable with caps)."
            )
        max_scenes = int(getattr(settings, "low_ram_long_max_scenes", 30) or 30)
        max_dur = float(getattr(settings, "low_ram_long_max_duration_s", 480.0) or 480.0)
        if len(scenes) > max_scenes:
            logger.warning(
                "low_ram long: truncating scenes",
                before=len(scenes),
                after=max_scenes,
            )
            scenes = scenes[:max_scenes]
        total = sum(float(sc.get("duration_seconds") or 0) for sc in scenes)
        if total > max_dur and total > 0:
            scale = max_dur / total
            for sc in scenes:
                sc["duration_seconds"] = max(
                    0.8, float(sc.get("duration_seconds") or 1.0) * scale
                )
            logger.warning(
                "low_ram long: scaled duration to cap",
                before_s=round(total, 1),
                after_s=round(max_dur, 1),
            )
        return scenes

    video_service.VideoAgentService._resolve_scenes = _resolve_scenes_capped  # type: ignore[assignment]

    try:
        import app.agents.video_agent.renderer as video_renderer

        def _render_fps_low_ram() -> int:
            return int(getattr(settings, "low_ram_long_target_fps", 24) or 24)

        video_renderer._render_fps = _render_fps_low_ram  # type: ignore[assignment]
    except Exception as exc:
        logger.warning("low_ram fps patch skipped", error=str(exc))

    logger.info(
        "LOW_RAM_MODE active — Whisper skipped; Shorts + capped Long; static captions + light encode",
        video_quality_preset=settings.video_quality_preset,
        caption_style=settings.caption_style,
        enable_ken_burns=settings.enable_ken_burns,
        enable_transitions=settings.enable_transitions,
        allow_long=getattr(settings, "allow_long_form_on_low_ram", True),
        long_max_duration_s=getattr(settings, "low_ram_long_max_duration_s", 480.0),
        long_max_scenes=getattr(settings, "low_ram_long_max_scenes", 30),
    )
