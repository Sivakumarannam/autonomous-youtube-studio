"""
PresenterService — AI avatar / lip-sync, pluggable between two backends:

  PRESENTER_PROVIDER=sadtalker  (default, FREE)
      Hosted SadTalker Gradio Space on Hugging Face. No cost, but
      shared public infrastructure — can queue, and the specific Space
      can go down or change its API since it's someone else's demo.
      See sadtalker_presenter.py for setup notes and version pins.

  PRESENTER_PROVIDER=did  (PAID)
      D-ID's hosted API. Costs credits per generated video, but is
      fast and reliable — no public queue, no Gradio version chasing.
      See did_presenter.py.

Setup required (sadtalker, free):
    1. Set PRESENTER_ENABLED=true
    2. Leave PRESENTER_PROVIDER unset or set it to "sadtalker"
    3. (Optional) Set PRESENTER_HF_SPACE / PRESENTER_HF_TOKEN if you
       don't want the default public Space
    4. On Windows, also set PYTHONIOENCODING=utf-8 before running —
       gradio_client prints a unicode checkmark that crashes on the
       default Windows console encoding otherwise.

Setup required (did, paid):
    1. Set PRESENTER_ENABLED=true
    2. Set PRESENTER_PROVIDER=did
    3. Set DID_API_KEY in .env

Both providers:
    - Put a real face photo at storage/avatars/female_presenter.png
      and/or storage/avatars/male_presenter.png
    - If PRESENTER_ENABLED is false, or the call fails for any reason,
      this service returns None and the pipeline continues without a
      presenter — it never blocks or fails the video render.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_AVATAR_DIR = Path("./storage/avatars")
_FEMALE = _AVATAR_DIR / "female_presenter.png"
_MALE = _AVATAR_DIR / "male_presenter.png"

# Generous timeout: the free sadtalker route can sit in a shared public
# queue on top of its own 1-3 min inference time.
_REQUEST_TIMEOUT = 900.0


class PresenterService:
    """Facade for AI avatar generation, routed to the configured provider."""

    def __init__(self) -> None:
        self.provider = os.environ.get("PRESENTER_PROVIDER", "sadtalker").lower()

    def is_available(self) -> bool:
        """Return True when presenter generation is enabled and configured."""
        from app.core.config import settings

        if not getattr(settings, "presenter_enabled", False):
            return False

        if self.provider == "did":
            return bool(getattr(settings, "did_api_key", "") or os.environ.get("DID_API_KEY"))
        if self.provider == "sadtalker":
            return True  # has its own sensible default Space id
        return False

    def get_default_avatar(self, gender: str = "female") -> Optional[str]:
        """Return the path to the default avatar image for the given gender."""
        path = _FEMALE if gender.lower() == "female" else _MALE
        return str(path) if path.exists() else None

    async def generate(
        self,
        audio_path: str,
        output_path: str,
        gender: str = "female",
        avatar_image: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a lip-synced presenter video via the configured provider.

        Returns the output path on success, or None if unavailable/failed.
        Never raises — the pipeline must be able to continue without a
        presenter regardless of what goes wrong here.
        """
        if not self.is_available():
            logger.info("Presenter generation skipped (no free provider available)")
            return None

        image_path = avatar_image or self.get_default_avatar(gender)
        if not image_path:
            logger.warning("No avatar image found", gender=gender)
            return None

        if not Path(audio_path).exists():
            logger.warning("Audio missing", audio_path=audio_path)
            return None

        try:
            logger.info("Generating presenter", provider=self.provider)

            if self.provider == "did":
                from app.integrations.did_presenter import DIDPresenter
                result = await asyncio.to_thread(
                    DIDPresenter().generate, image_path, audio_path, output_path,
                )
            else:
                from app.integrations.sadtalker_presenter import SadTalkerPresenter
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        SadTalkerPresenter().generate, image_path, audio_path, output_path,
                    ),
                    timeout=_REQUEST_TIMEOUT,
                )

            return result

        except asyncio.TimeoutError:
            logger.warning(
                "Presenter request timed out (likely queued on a shared public Space)",
                provider=self.provider,
            )
            return None
        except Exception as e:
            logger.error("Presenter failed", provider=self.provider, error=str(e))
            return None
