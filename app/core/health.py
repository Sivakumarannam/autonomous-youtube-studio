"""
Startup Health Checks — validates that all required services are available.

Called from app/main.py lifespan on startup.  Results are logged clearly;
missing optional services produce warnings, missing required services produce errors.

Checks:
  ✓ Ollama (LLM)         — required for script generation
  ✓ FFmpeg               — required for video encoding
  ✓ Whisper              — required for caption timing
  ✓ gTTS / Kokoro        — required for voice synthesis
  ✓ Pollinations         — required for AI images
  ✓ Pexels               — optional stock photos (needs API key)
  ✓ Background Music     — optional (local storage/music/ files, or Jamendo API key)
  ✓ Pixabay (informational) — key detection only; Pixabay's public API has no
                               music-search endpoint, so it is NOT used for
                               background music. Kept here only so you can see
                               whether the key is configured, in case it's used
                               elsewhere (e.g. future stock-photo support).
  ✓ YouTube API           — required for upload
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

CHECK_OK = "✓"
CHECK_WARN = "⚠"
CHECK_FAIL = "✗"


@dataclass
class CheckResult:
    name: str
    ok: bool
    required: bool
    message: str


async def run_all() -> list[CheckResult]:
    """Run all health checks and return results."""
    results = []

    results.append(await _check_llm())
    results.append(_check_ffmpeg())
    results.append(_check_whisper())
    results.append(_check_gtts())
    results.append(_check_kokoro())
    results.append(await _check_pollinations())
    results.append(_check_pexels())
    results.append(_check_music())
    results.append(_check_pixabay_key_only())
    results.append(_check_youtube())

    # Log summary
    logger.info("=" * 50)
    logger.info("STARTUP VALIDATION RESULTS")
    logger.info("=" * 50)
    for r in results:
        icon = CHECK_OK if r.ok else (CHECK_WARN if not r.required else CHECK_FAIL)
        level = "info" if r.ok else ("warning" if not r.required else "error")
        getattr(logger, level)(
            f"{icon} {r.name}",
            status="OK" if r.ok else "MISSING",
            message=r.message,
            required=r.required,
        )
    logger.info("=" * 50)

    failed_required = [r for r in results if not r.ok and r.required]
    if failed_required:
        names = [r.name for r in failed_required]
        logger.error(
            "Required services are unavailable — some pipeline stages will fail",
            missing=names,
        )
    else:
        logger.info("All required services are available. System ready.")

    return results


async def _check_llm() -> CheckResult:
    """Check whichever LLM provider is configured (not just Ollama)."""
    provider = settings.llm_provider.lower()
    name = f"LLM ({provider})"

    if provider == "mock":
        return CheckResult(name, True, True, "Mock provider active — no real LLM calls made")

    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.ollama_base_url}/api/tags")
                if resp.status_code == 200:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                    return CheckResult(name, True, True, f"Running — {len(models)} model(s) loaded")
                return CheckResult(name, False, True, f"HTTP {resp.status_code} from Ollama")
        except Exception:
            return CheckResult(
                name, False, True,
                f"Not reachable at {settings.ollama_base_url} — install: https://ollama.ai"
            )

    if provider == "groq":
        if not settings.groq_api_key:
            return CheckResult(name, False, True, "GROQ_API_KEY not set — get a free key at console.groq.com")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                )
                if resp.status_code == 200:
                    model_count = len(resp.json().get("data", []))
                    return CheckResult(name, True, True,
                        f"API reachable — {model_count} models available, using {settings.groq_model}")
                return CheckResult(name, False, True, f"Groq API returned HTTP {resp.status_code}")
        except Exception as e:
            return CheckResult(name, False, True, f"Groq API unreachable: {e}")

    if provider == "gemini":
        ok = bool(settings.gemini_api_key)
        return CheckResult(name, ok, True,
            "API key configured" if ok else "GEMINI_API_KEY not set")

    if provider in ("openai", "anthropic"):
        key = settings.openai_api_key if provider == "openai" else settings.anthropic_api_key
        ok = bool(key)
        return CheckResult(name, ok, True,
            "API key configured" if ok else f"{provider.upper()}_API_KEY not set")

    return CheckResult(name, False, True, f"Unknown provider '{provider}'")


def _check_ffmpeg() -> CheckResult:
    name = "FFmpeg"
    path = shutil.which("ffmpeg")
    if path:
        try:
            out = subprocess.check_output(
                ["ffmpeg", "-version"], stderr=subprocess.STDOUT, text=True
            )
            version = out.split("\n")[0].split("version ")[-1].split(" ")[0]
            return CheckResult(name, True, True, f"Found at {path} (version {version})")
        except Exception:
            return CheckResult(name, True, True, f"Found at {path}")
    return CheckResult(
        name, False, True,
        "Not found — install: https://ffmpeg.org/download.html or 'choco install ffmpeg' on Windows"
    )


def _check_whisper() -> CheckResult:
    name = "Faster-Whisper"
    try:
        import faster_whisper  # noqa
        return CheckResult(name, True, False, "Package installed")
    except ImportError:
        return CheckResult(
            name, False, False,
            "Not installed — captions will use word-count timing. Install: pip install faster-whisper"
        )


def _check_gtts() -> CheckResult:
    name = "gTTS (voice fallback)"
    try:
        import gtts  # noqa
        return CheckResult(name, True, True, "Package installed — internet required for synthesis")
    except ImportError:
        return CheckResult(
            name, False, True,
            "Not installed — install: pip install gTTS"
        )


def _check_kokoro() -> CheckResult:
    name = "Kokoro TTS (high-quality voice)"
    try:
        from app.integrations.kokoro_tts import is_available
        if is_available():
            return CheckResult(name, True, False, "Model loaded — will use as primary TTS")
        else:
            try:
                import kokoro_onnx  # noqa
                return CheckResult(
                    name, False, False,
                    "Package installed but model files missing. See docs/SETUP_GUIDE.md"
                )
            except ImportError:
                return CheckResult(
                    name, False, False,
                    "Not installed — using gTTS fallback. Install: pip install kokoro-onnx"
                )
    except Exception:
        return CheckResult(name, False, False, "Check failed — using gTTS fallback")


async def _check_pollinations() -> CheckResult:
    name = "Pollinations AI (images)"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://image.pollinations.ai/", follow_redirects=True)
            if resp.status_code < 500:
                return CheckResult(name, True, False, "Reachable — free FLUX image generation active")
        return CheckResult(name, False, False, "Not reachable — will use gradient fallback")
    except Exception:
        return CheckResult(name, False, False, "Not reachable — will use gradient fallback")


def _check_pexels() -> CheckResult:
    name = "Pexels (stock photos)"
    key = settings.pexels_api_key
    if key:
        return CheckResult(name, True, False, "API key configured — stock photos enabled")
    return CheckResult(
        name, False, False,
        "No API key — get a free key at https://www.pexels.com/api/ and set PEXELS_API_KEY"
    )


def _check_music() -> CheckResult:
    """
    Real availability check for background music.

    Priority used by app.integrations.music_provider at runtime:
      1. Local MP3s in storage/music/  (checked first, zero network dependency)
      2. Jamendo API (JAMENDO_CLIENT_ID) — automated fallback

    Pixabay is intentionally NOT part of this chain — see module docstring.
    """
    name = "Background Music (local / Jamendo)"

    local_dir = Path("./storage/music")
    has_local = local_dir.exists() and any(local_dir.glob("*.mp3"))
    if has_local:
        count = len(list(local_dir.glob("*.mp3")))
        return CheckResult(
            name, True, False,
            f"{count} local track(s) found in storage/music/ — background music enabled"
        )

    jamendo_key = getattr(settings, "jamendo_client_id", "")
    if jamendo_key:
        return CheckResult(
            name, True, False,
            "Jamendo API key configured — background music enabled via automated fallback "
            "(verify Jamendo's licensing terms before use on a monetized channel)"
        )

    return CheckResult(
        name, False, False,
        "No local tracks and no JAMENDO_CLIENT_ID — background music disabled. "
        "Add MP3s to storage/music/ (named by genre, e.g. electronic.mp3) or get a "
        "free key at https://devportal.jamendo.com/ and set JAMENDO_CLIENT_ID"
    )


def _check_pixabay_key_only() -> CheckResult:
    """
    Informational only. Pixabay's public REST API has no music-search
    endpoint, so a configured PIXABAY_API_KEY does NOT enable background
    music — that is handled entirely by _check_music() above (local files
    or Jamendo). This check exists only so the key's presence is visible
    in startup logs, e.g. in case it's wired up for stock photos/video in
    the future.
    """
    name = "Pixabay (key detected only — not used for music)"
    key = settings.pixabay_api_key
    if key:
        return CheckResult(name, True, False, "API key configured — not currently used by any active provider")
    return CheckResult(name, False, False, "No API key configured — no effect on current pipeline")


def _check_youtube() -> CheckResult:
    name = "YouTube API"
    if settings.youtube_client_id and settings.youtube_refresh_token:
        return CheckResult(name, True, False, "OAuth credentials configured — upload enabled")
    if settings.youtube_api_key:
        return CheckResult(name, True, False, "API key configured (analytics only — OAuth needed for upload)")
    return CheckResult(
        name, False, False,
        "No credentials — configure YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN"
    )