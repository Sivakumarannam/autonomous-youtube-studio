"""Instagram automation via Meta Graph API.

Posts video Reels to Instagram Business after successful YouTube upload.
Requires:
  - META_ACCESS_TOKEN  (long-lived page/user access token)
  - INSTAGRAM_BUSINESS_ACCOUNT_ID  (numeric IG account ID)
  - A publicly accessible video URL (uses YouTube URL after upload)

Enable with INSTAGRAM_ENABLED=true.

Limitation: Reels must be uploaded via a public URL — we pass the YouTube
video URL (youtu.be/…) as the video source.  Instagram then fetches it.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog

from app.core.config import settings
from app.integrations.instagram_token_store import get_current_token

logger = structlog.get_logger(__name__)

GRAPH_BASE = "https://graph.instagram.com/v26.0"


def build_ig_caption(title: str, description: str, yt_url: str) -> str:
    """Build a rich Instagram caption from upload metadata.

    Structure:
      • Hook line (title)
      • Body teaser (first sentence of description)
      • CTA with YouTube link
      • Up to 20 hashtags extracted from title + description keywords
    """
    import re

    # Hook
    hook = title.strip() or "New video out now!"

    # Teaser — first sentence of description, stripped of chapter blocks
    clean_desc = re.sub(r"⏱ Chapters:.*", "", description, flags=re.DOTALL).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", clean_desc)[0][:200] if clean_desc else ""

    # Extract hashtags already in description
    existing_tags = re.findall(r"#\w+", description)
    unique_tags: list[str] = []
    seen: set[str] = set()
    for t in existing_tags:
        low = t.lower()
        if low not in seen:
            unique_tags.append(t)
            seen.add(low)

    # Add keyword-based tags from title
    stop_words = {"the", "a", "an", "and", "or", "but", "for", "with", "in", "on", "at", "to", "of", "is"}
    for word in re.findall(r"[a-zA-Z]{4,}", title):
        if word.lower() not in stop_words:
            tag = f"#{word.capitalize()}"
            if tag.lower() not in seen and len(unique_tags) < 20:
                unique_tags.append(tag)
                seen.add(tag.lower())

    # Always include a core set
    for core in ["#YouTube", "#YouTubeShorts", "#Reels", "#Trending", "#Viral", "#Learning"]:
        if core.lower() not in seen and len(unique_tags) < 20:
            unique_tags.append(core)
            seen.add(core.lower())

    hashtag_block = " ".join(unique_tags[:20])

    parts = [f"🎬 {hook}"]
    if first_sentence:
        parts.append(first_sentence)
    parts.append("👇 Watch the full video — link in bio!")
    parts.append(f"▶️ YouTube: {yt_url}")
    parts.append(f"\n{hashtag_block}")

    return "\n\n".join(parts)


class InstagramPublisher:
    """Publish a Reel to Instagram Business via Graph API."""

    def __init__(self) -> None:
        self._account_id = settings.instagram_business_account_id
        self._token, _ = get_current_token()

    def _enabled(self) -> bool:
        # Re-read each call so auto-enable in config, and any freshly
        # auto-refreshed token, are picked up without a restart.
        token, _ = get_current_token()
        account = settings.instagram_business_account_id
        return bool(settings.instagram_enabled and account and token)

    async def post_reel(
        self,
        video_url: str,
        caption: str,
        cover_url: Optional[str] = None,
    ) -> Optional[str]:
        """Upload a Reel and publish it.  Returns the IG media ID or None on failure."""
        if not self._enabled():
            logger.info("Instagram disabled or not configured — skipping.")
            return None

        try:
            container_id = await self._create_container(video_url, caption, cover_url)
            if not container_id:
                return None
            await self._wait_for_ready(container_id)
            media_id = await self._publish(container_id)
            logger.info("Instagram Reel published", media_id=media_id)
            return media_id
        except Exception as exc:
            logger.warning("Instagram post failed (non-fatal)", error=str(exc))
            return None

    async def _create_container(self, video_url: str, caption: str, cover_url: Optional[str]) -> Optional[str]:
        token, _ = get_current_token()
        account = settings.instagram_business_account_id
        params: dict = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token,
        }
        if cover_url:
            params["cover_url"] = cover_url

        url = f"{GRAPH_BASE}/{account}/media"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, data=params)
            if r.is_error:
                logger.error(
                    "Instagram media creation failed — Meta API response",
                    status_code=r.status_code,
                    response_body=r.text[:1500],
                )
            r.raise_for_status()
            data = r.json()
            container_id = data.get("id")
            logger.info("Instagram container created", container_id=container_id)
            return container_id

    async def _wait_for_ready(self, container_id: str, max_wait: int = 120) -> None:
        """Poll until container status is FINISHED."""
        url = f"{GRAPH_BASE}/{container_id}"
        token, _ = get_current_token()
        params = {"fields": "status_code", "access_token": token}
        for _ in range(max_wait // 5):
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, params=params)
                if r.is_error:
                    logger.error(
                        "Instagram container status check failed — Meta API response",
                        status_code=r.status_code,
                        response_body=r.text[:1500],
                    )
                r.raise_for_status()
                status = r.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError("Instagram container processing failed")
        raise TimeoutError("Instagram container not ready within timeout")

    async def _publish(self, container_id: str) -> str:
        url = f"{GRAPH_BASE}/{settings.instagram_business_account_id}/media_publish"
        token, _ = get_current_token()
        params = {"creation_id": container_id, "access_token": token}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, data=params)
            if r.is_error:
                logger.error(
                    "Instagram publish failed — Meta API response",
                    status_code=r.status_code,
                    response_body=r.text[:1500],
                )
            r.raise_for_status()
            return r.json().get("id", "")


# Module-level singleton
_publisher = InstagramPublisher()


async def post_to_instagram(
    video_url: str,
    caption: str,
    cover_url: Optional[str] = None,
) -> Optional[str]:
    """Convenience function for posting a Reel. Returns IG media ID or None."""
    return await _publisher.post_reel(video_url, caption, cover_url)
