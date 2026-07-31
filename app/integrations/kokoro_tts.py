"""
Kokoro TTS Provider — high-quality free neural text-to-speech.

Kokoro uses ONNX runtime (already installed) and produces human-quality audio
without requiring a GPU.  Model files must be downloaded once (see SETUP_GUIDE.md).

Voice IDs:
  Female: af_heart (default), af_bella, af_nicole, af_sarah
  Male:   am_adam (default), am_michael

Installation:
    pip install kokoro-onnx
    # Download models: see docs/SETUP_GUIDE.md
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Model files are stored in storage/models/kokoro/
# kokoro-onnx v0.5+ uses the v1.0 model format.
# The int8 build (~92 MB) gives nearly identical quality to fp32 (~325 MB) on CPU.
_MODEL_DIR = Path(os.environ.get("KOKORO_MODEL_DIR", "./storage/models/kokoro"))
_ONNX_PATH = _MODEL_DIR / "kokoro-v1.0.int8.onnx"
_VOICES_PATH = _MODEL_DIR / "voices-v1.0.bin"

# Voice selections per gender (v1.0 voice IDs)
FEMALE_VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah"]
MALE_VOICES = ["am_adam", "am_michael"]
DEFAULT_FEMALE = "af_heart"
DEFAULT_MALE = "am_adam"

_kokoro_instance: Optional[object] = None


def _get_kokoro():
    """Lazy-load the Kokoro model. Returns None if unavailable."""
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance

    if not _ONNX_PATH.exists() or not _VOICES_PATH.exists():
        logger.debug(
            "Kokoro model files not found — skipping Kokoro TTS",
            onnx=str(_ONNX_PATH),
            voices=str(_VOICES_PATH),
        )
        return None

    try:
        from kokoro_onnx import Kokoro  # type: ignore
        _kokoro_instance = Kokoro(str(_ONNX_PATH), str(_VOICES_PATH))
        logger.info("Kokoro TTS model loaded", model_dir=str(_MODEL_DIR))
        return _kokoro_instance
    except ImportError:
        logger.debug("kokoro-onnx package not installed — skipping Kokoro TTS")
        return None
    except Exception as exc:
        logger.warning("Kokoro TTS load failed", error=str(exc))
        return None


def is_available() -> bool:
    """Return True if Kokoro is installed and model files exist."""
    return _get_kokoro() is not None


def pick_voice(gender: str = "female") -> str:
    """Return an appropriate Kokoro voice ID for the requested gender."""
    if gender.lower() in ("male", "m"):
        return DEFAULT_MALE
    return DEFAULT_FEMALE


def _split_into_chunks(text: str, max_chars: int = 800) -> list[str]:
    """
    Split text into sentence-bounded chunks of at most max_chars each.
    Keeps sentences together so Kokoro gets natural prosody boundaries.
    """
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        # If a single sentence is longer than the limit, hard-split it
        if len(sent) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(sent), max_chars):
                chunks.append(sent[i : i + max_chars])
            continue
        if current and len(current) + 1 + len(sent) > max_chars:
            chunks.append(current.strip())
            current = sent
        else:
            current = (current + " " + sent).strip() if current else sent
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if c]


def synthesise_sync(
    text: str,
    output_path: str,
    voice: str = DEFAULT_FEMALE,
    speed: float = 1.0,
    language: str = "en-us",
) -> bool:
    """
    Synthesise `text` to a WAV file using Kokoro.

    Long texts are split into sentence-bounded chunks (~800 chars each) and
    their audio is concatenated, so there is no character-count ceiling.

    Returns True on success, False on any failure (caller falls back to gTTS).
    The output is WAV; the caller is responsible for converting to MP3 if needed.
    """
    kokoro = _get_kokoro()
    if kokoro is None:
        return False

    try:
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore

        chunks = _split_into_chunks(text)
        logger.info(
            "Kokoro TTS synthesising",
            voice=voice,
            chunks=len(chunks),
            total_chars=len(text),
            output=output_path,
        )

        all_samples: list = []
        sample_rate: int = 24000

        for i, chunk in enumerate(chunks):
            samples, sr = kokoro.create(
                chunk,
                voice=voice,
                speed=speed,
                lang=language,
            )
            sample_rate = sr
            all_samples.append(samples)
            logger.debug("Kokoro chunk done", chunk=i + 1, total=len(chunks))

        combined = np.concatenate(all_samples) if len(all_samples) > 1 else all_samples[0]
        sf.write(output_path, combined, sample_rate)
        logger.info(
            "Kokoro TTS synthesis complete",
            voice=voice,
            sample_rate=sample_rate,
            output=output_path,
        )
        return True
    except ImportError as exc:
        logger.debug("Kokoro dependency missing", error=str(exc))
        return False
    except Exception as exc:
        logger.warning("Kokoro synthesis failed", error=str(exc))
        return False


async def synthesise(
    text: str,
    output_path: str,
    voice: str = DEFAULT_FEMALE,
    speed: float = 1.0,
    language: str = "en-us",
) -> bool:
    """Async wrapper around synthesise_sync — runs in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        synthesise_sync,
        text,
        output_path,
        voice,
        speed,
        language,
    )
