"""AI image generation with provider fallback chain, disk cache, and quality enhancement.

Provider chain (in order):
  1. Hugging Face Inference API — when HF_API_TOKEN env var is set.
  2. Pollinations AI — free, no API key, 15 s timeout. Retries on 429
     (rate limited) with exponential backoff before falling through.
  3. Local gradient fallback — professional gradient background, never
     returns a plain solid-colour card.

Quality enhancements
--------------------
* Prompt enhancement: quality keywords appended before sending to providers.
* PIL post-processing: sharpness, contrast, and saturation boost after fetch.
* Gradient fallback: palette-derived multi-stop gradient instead of flat colour.

Config env vars
---------------
IMAGE_PROVIDER   override default provider order (default: "pollinations")
HF_API_TOKEN     enables HF provider; silently skipped when absent
HF_MODEL         HF model id (default: stabilityai/stable-diffusion-xl-base-1.0)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import random
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
_HF_API_BASE = "https://api-inference.huggingface.co/models"
# FLUX.1-schnell is genuinely free on the HF serverless tier (no Pro required).
# SDXL-base-1.0 now requires HF Pro — do not use it as default.
_DEFAULT_HF_MODEL = "black-forest-labs/FLUX.1-schnell"
# FLUX on Pollinations takes ~20-35 s; give it room to finish.
_POLLINATIONS_TIMEOUT = 60.0
_HF_TIMEOUT = 60.0

# Reduced retries with shorter initial delay — if Pollinations is rate-limiting
# hard, fall through to the gradient fallback faster rather than spending
# 5+ minutes retrying.
_POLLINATIONS_MAX_RETRIES = 3
_POLLINATIONS_BASE_BACKOFF_SECONDS = 8.0

# Per-cache-key in-process locks prevent concurrent requests for the same
# (script_id, prompt, size) from racing past the existence check and issuing
# redundant provider calls.  Keys are cache-path strings; values are asyncio
# Locks created on first access.
_cache_locks: dict[str, asyncio.Lock] = {}
_cache_locks_mutex = asyncio.Lock()

# Quality suffixes appended to prompts for better AI image results
_QUALITY_SUFFIX = (
    ", professional photography, highly detailed, 4K resolution, "
    "cinematic lighting, sharp focus, vibrant colors, studio quality"
)
_QUALITY_KEYWORDS = {"professional", "4k", "8k", "cinematic", "high quality", "detailed"}


async def _get_cache_lock(cache_path: Path) -> asyncio.Lock:
    """Return (creating if necessary) the per-path asyncio.Lock."""
    key = str(cache_path)
    # Fast path — no allocation needed when the lock already exists.
    if key in _cache_locks:
        return _cache_locks[key]
    async with _cache_locks_mutex:
        if key not in _cache_locks:
            _cache_locks[key] = asyncio.Lock()
        return _cache_locks[key]


def enhance_prompt(prompt: str) -> str:
    """Append quality keywords to a scene prompt for better AI image output.

    Only appends when the prompt doesn't already contain quality indicators,
    so manually crafted prompts are not polluted.
    """
    if not settings.image_prompt_enhance:
        return prompt
    if not prompt:
        return prompt
    lower = prompt.lower()
    if any(kw in lower for kw in _QUALITY_KEYWORDS):
        return prompt
    return prompt.rstrip() + _QUALITY_SUFFIX


def _enhance_image_bytes(image_bytes: bytes, width: int, height: int) -> bytes:
    """Apply PIL-based quality enhancement to downloaded image bytes.

    Applies: resize to exact target size, sharpness boost, contrast boost,
    and subtle colour saturation increase.  All operations are lightweight
    and run on CPU with negligible overhead.
    """
    if not settings.enable_image_enhance:
        return image_bytes
    try:
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Resize only if necessary (provider may return a different size)
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)

        # Sharpness: 1.0 = original, 1.3 = slightly crisper
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        # Contrast: slight lift to make details pop
        img = ImageEnhance.Contrast(img).enhance(1.1)
        # Colour saturation: make colours more vivid
        img = ImageEnhance.Color(img).enhance(1.15)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.debug("Image enhancement skipped", error=str(exc))
        return image_bytes


def _make_gradient_fallback(width: int, height: int, prompt: str) -> bytes:
    """Generate a professional multi-stop gradient fallback image.

    Derives palette from the prompt hash so different scenes get different
    colour schemes, maintaining visual variety without relying on external APIs.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    # Deterministic colour selection from prompt hash
    h = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    palettes = [
        ((8, 15, 40), (25, 55, 120)),      # deep blue
        ((18, 8, 38), (75, 25, 95)),       # deep purple
        ((8, 28, 18), (15, 75, 55)),       # forest teal
        ((28, 12, 8), (95, 45, 15)),       # warm amber
        ((8, 22, 32), (18, 65, 95)),       # ocean blue
        ((35, 8, 25), (100, 20, 60)),      # crimson
        ((10, 30, 30), (25, 85, 80)),      # cyan
    ]
    c1, c2 = palettes[h % len(palettes)]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        t = y / max(height - 1, 1)
        # Eased interpolation (smoothstep) for more natural gradient
        t_smooth = t * t * (3 - 2 * t)
        r = int(c1[0] + (c2[0] - c1[0]) * t_smooth)
        g = int(c1[1] + (c2[1] - c1[1]) * t_smooth)
        b = int(c1[2] + (c2[2] - c1[2]) * t_smooth)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Subtle Gaussian blur for a smoother gradient
    img = img.filter(ImageFilter.GaussianBlur(radius=3))

    # Overlay the prompt as readable text so the scene is never blank
    try:
        import textwrap
        draw = ImageDraw.Draw(img)
        font_size = max(32, width // 14)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
            )
        except (IOError, OSError):
            font = ImageFont.load_default()

        # Strip technical prompt keywords, keep human-readable words
        clean_prompt = re.sub(
            r"\b(ultra|realistic|cinematic|HDR|8K|4K|volumetric|lighting|"
            r"bokeh|photography|highly|detailed|sharp|focus|dramatic|"
            r"photorealistic|octane|render|unreal|engine|artstation)\b",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip(" ,.")
        chars_per_line = max(10, int(width * 0.8 / (font_size * 0.55)))
        lines = textwrap.wrap(clean_prompt, width=chars_per_line)[:4]
        text = "\n".join(lines)

        if text:
            # Semi-transparent overlay bar
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            test_bbox = ov_draw.textbbox((0, 0), text, font=font)
            text_h = test_bbox[3] - test_bbox[1]
            pad = int(height * 0.03)
            box_top = (height - text_h) // 2 - pad
            box_bot = (height + text_h) // 2 + pad
            ov_draw.rectangle([(0, box_top), (width, box_bot)], fill=(0, 0, 0, 150))
            img = img.convert("RGBA")
            img = Image.alpha_composite(img, overlay).convert("RGB")
            draw = ImageDraw.Draw(img)
            draw.multiline_text(
                (width // 2, height // 2),
                text,
                font=font,
                fill=(255, 255, 255),
                anchor="mm",
                align="center",
                spacing=int(font_size * 0.3),
            )
    except Exception:
        pass  # Text overlay is best-effort; gradient alone is still better than blank

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


class ImageProvider:
    """Async AI image generator with provider fallback and disk cache."""

    @classmethod
    async def generate(
        cls,
        prompt: str,
        width: int,
        height: int,
        script_id: str = "shared",
    ) -> Optional[str]:
        # Enhance prompt before caching (enhanced prompt is the cache key)
        enhanced_prompt = enhance_prompt(prompt)

        # Calculate cache path based on enhanced prompt
        cached = cls._cache_path(script_id, enhanced_prompt, width, height)
        # Get lock for this cache entry
        lock = await _get_cache_lock(cached)
        async with lock:
            if cached.exists():
                return str(cached)

            image_bytes: Optional[bytes] = None
            hf_error_str: str = ""

            # 1. Try Hugging Face — only when HF_API_TOKEN is configured.
            #    Never hardcode credentials; read exclusively from the environment.
            hf_token = os.environ.get("HF_API_TOKEN", "").strip()
            if hf_token:
                try:
                    image_bytes = await cls._from_huggingface(
                        enhanced_prompt, width, height, hf_token
                    )
                    logger.info("HuggingFace image fetch succeeded.")
                except Exception as exc:
                    hf_error_str = str(exc)
                    logger.info("HuggingFace failed, trying Pollinations.", error=hf_error_str)
            else:
                logger.debug("HF_API_TOKEN not set; skipping HuggingFace provider.")

            # 2. Try Pollinations when HF was unavailable or failed
            if image_bytes is None:
                try:
                    image_bytes = await cls._from_pollinations(
                        enhanced_prompt, width, height
                    )
                    logger.info("Pollinations image fetch succeeded.")
                except Exception as poll_exc:
                    logger.warning(
                        "All providers failed; using gradient fallback.",
                        hf_error=hf_error_str,
                        poll_error=str(poll_exc),
                    )
                    # 3. Professional gradient fallback — never a plain solid colour
                    image_bytes = _make_gradient_fallback(width, height, prompt)

            # Apply PIL quality enhancement
            if image_bytes is not None:
                image_bytes = _enhance_image_bytes(image_bytes, width, height)

            if not image_bytes:
                # Last resort: plain gradient (should never reach here)
                image_bytes = _make_gradient_fallback(width, height, prompt)

            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".tmp")
            tmp.write_bytes(image_bytes)
            tmp.replace(cached)
            return str(cached)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    _api_lock = asyncio.Lock()

    @classmethod
    async def _from_pollinations(
        cls,
        prompt: str,
        width: int,
        height: int,
    ) -> Optional[bytes]:
        """Fetch image from Pollinations AI sequentially to avoid 429s.

        Uses the FLUX model which produces significantly better images than
        the default model and is available at no cost via Pollinations.
        A deterministic seed derived from the prompt ensures the same prompt
        always returns a consistent image across retries.
        """
        async with cls._api_lock:
            # Derive a deterministic seed from the prompt so retries get the
            # same image, and different prompts get different images.
            seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 2147483647
            encoded = quote(prompt, safe="")
            url = (
                f"{_POLLINATIONS_BASE}/{encoded}"
                f"?width={width}&height={height}&nologo=true"
                f"&model=flux&seed={seed}"
            )

        last_exc: Optional[Exception] = None

        for attempt in range(_POLLINATIONS_MAX_RETRIES + 1):
            async with httpx.AsyncClient(
                timeout=_POLLINATIONS_TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)

            if response.status_code == 429:
                if attempt >= _POLLINATIONS_MAX_RETRIES:
                    response.raise_for_status()  # raises, caught by caller

                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = _POLLINATIONS_BASE_BACKOFF_SECONDS * (2 ** attempt)
                else:
                    delay = _POLLINATIONS_BASE_BACKOFF_SECONDS * (2 ** attempt)

                logger.info(
                    "Pollinations rate limited — backing off before retry.",
                    attempt=attempt + 1,
                    max_retries=_POLLINATIONS_MAX_RETRIES,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)
                continue

            try:
                response.raise_for_status()
            except Exception as exc:
                last_exc = exc
                raise

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                raise ValueError(
                    f"Pollinations returned unexpected content-type: {content_type!r}"
                )

            logger.info(
                "Pollinations image fetched",
                size_kb=round(len(response.content) / 1024, 1),
                url=url,
                attempt=attempt + 1,
            )
            return response.content

        # Unreachable in practice (the 429 branch either retries or raises
        # on the final attempt), but keeps type-checkers happy.
        if last_exc is not None:
            raise last_exc
        return None

    @staticmethod
    async def _from_huggingface(
        prompt: str,
        width: int,
        height: int,
        token: str,
    ) -> Optional[bytes]:
        """Fetch image from HuggingFace Inference API (using requests to avoid async DNS bugs)."""
        import requests

        model = os.environ.get("HF_MODEL", _DEFAULT_HF_MODEL).strip()
        url = f"{_HF_API_BASE}/{model}"
        payload = {
            "inputs": prompt,
            "parameters": {"width": width, "height": height},
        }

        def fetch():
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                raise ValueError(
                    f"HuggingFace returned unexpected content-type: {content_type!r}"
                )
            return response.content

        # Run the synchronous requests call in a thread pool
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, fetch)

        logger.info(
            "HuggingFace image fetched",
            model=model,
            size_kb=round(len(content) / 1024, 1),
        )
        return content

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_path(
        script_id: str,
        prompt: str,
        width: int,
        height: int,
    ) -> Path:
        """Return a deterministic cache path for (script_id, prompt, size)."""
        key = f"{prompt}:{width}:{height}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        cache_dir = (
            Path(settings.storage_local_path) / "image_cache" / script_id
        )
        return cache_dir / f"{digest}.jpg"
