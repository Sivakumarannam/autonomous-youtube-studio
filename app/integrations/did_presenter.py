from __future__ import annotations

import os
import time
import requests
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class DIDPresenter:

    def __init__(self):
        # Prefer the app's central Settings (so DID_API_KEY shows up
        # alongside every other API key in config.py), but still fall
        # back to a raw env var read so this class works standalone too.
        try:
            from app.core.config import settings
            self.api_key = getattr(settings, "did_api_key", "") or os.environ.get("DID_API_KEY")
        except Exception:
            self.api_key = os.environ.get("DID_API_KEY")

        if not self.api_key:
            raise RuntimeError(
                "DID_API_KEY is missing (set it in .env or as an env var)"
            )

        self.headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(
        self,
        image_path: str,
        audio_path: str,
        output_path: str,
    ) -> str | None:

        logger.info("D-ID: uploading image")

        with open(image_path, "rb") as img:
            image_response = requests.post(
                "https://api.d-id.com/images",
                headers={"Authorization": f"Basic {self.api_key}"},
                files={"image": img},
            )
        image_response.raise_for_status()
        image_url = image_response.json()["url"]

        logger.info("D-ID: uploading audio")

        with open(audio_path, "rb") as audio:
            audio_response = requests.post(
                "https://api.d-id.com/audios",
                headers={"Authorization": f"Basic {self.api_key}"},
                files={"audio": audio},
            )
        audio_response.raise_for_status()
        audio_url = audio_response.json()["url"]

        logger.info("D-ID: creating video")

        payload = {
            "source_url": image_url,
            "script": {
                "type": "audio",
                "audio_url": audio_url,
            },
        }

        response = requests.post(
            "https://api.d-id.com/talks",
            headers=self.headers,
            json=payload,
        )
        response.raise_for_status()
        talk_id = response.json()["id"]

        logger.info("D-ID: video created", id=talk_id)

        while True:
            status_response = requests.get(
                f"https://api.d-id.com/talks/{talk_id}",
                headers=self.headers,
            )
            status_response.raise_for_status()
            data = status_response.json()
            status = data.get("status")

            logger.info("D-ID status", status=status)

            if status == "done":
                video_url = data["result_url"]
                break
            if status == "error":
                raise RuntimeError("D-ID generation failed")

            time.sleep(5)

        logger.info("D-ID downloading video")

        video = requests.get(video_url)
        video.raise_for_status()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(video.content)

        logger.info("D-ID finished", output=output_path)

        return output_path
