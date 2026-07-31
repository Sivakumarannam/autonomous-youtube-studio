from __future__ import annotations

import inspect
from typing import Any, Dict, Optional

import httpx

from app.core.logging import get_logger
from .auth import YouTubeAuthManager
from .exceptions import YouTubeVideoNotFoundError

logger = get_logger(__name__)


class YouTubeApiClient:
    def __init__(
        self,
        auth_manager: YouTubeAuthManager,
        base_url: str = "https://www.googleapis.com/youtube/v3",
        timeout_seconds: int = 30,
    ):
        self.auth_manager = auth_manager
        self.base_url = base_url.rstrip("/")
        self.session = httpx.AsyncClient(timeout=timeout_seconds)

    async def _headers(self) -> Dict[str, str]:
        token = await self.auth_manager.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = await self._headers()
        response = await self.session.request(method, url, headers=headers, params=params, json=json)
        await self._maybe_await(response.raise_for_status())
        return await self._maybe_await(response.json())

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def get_video_details(self, video_id: str) -> Dict[str, Any]:
        return await self._request(
            "GET",
            "videos",
            params={"part": "snippet,contentDetails,status", "id": video_id},
        )

    async def delete_video(self, video_id: str) -> None:
        """Permanently delete a video from YouTube. Irreversible.

        Uses a raw request rather than _request(), since YouTube returns
        204 No Content on success with no JSON body to parse.

        Special-cases 404 videoNotFound: this is an EXPECTED business
        scenario (the video was already deleted directly on YouTube by the
        user, outside this app) — raises YouTubeVideoNotFoundError so
        callers can prompt the user instead of surfacing a generic 500.
        All other non-2xx statuses keep the existing raise_for_status
        behavior, unchanged.
        """
        url = f"{self.base_url}/videos"
        headers = await self._headers()
        response = await self.session.delete(
            url,
            headers=headers,
            params={"id": video_id},
        )

        if response.status_code in (200, 204):
            return

        if response.status_code == 404:
            logger.info(
                "YouTube delete_video: video already gone (404 videoNotFound).",
                video_id=video_id,
                response_body=response.text,
            )
            raise YouTubeVideoNotFoundError(video_id)

        logger.error(
            "YouTube delete_video failed.",
            status_code=response.status_code,
            response_body=response.text,
            video_id=video_id,
        )
        await self._maybe_await(response.raise_for_status())

    async def create_video_metadata(
        self,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        category_id: str = "22",
        privacy_status: str = "private",
        default_language: str = "en",
        notify_subscribers: bool = True,
        made_for_kids: bool = False,
        ai_generated: bool = True,
    ) -> Dict[str, Any]:
        return {
            "snippet": {
                "title": title,
                "description": description,
                "tags": (tags or [])[:20],          # YouTube ignores >20 tags
                "categoryId": category_id,
                "defaultLanguage": default_language,
                "defaultAudioLanguage": default_language,
            },
            "status": {
                "privacyStatus": privacy_status,
                # Required by YouTube policy — must be false for general audiences.
                "selfDeclaredMadeForKids": made_for_kids,
                # Notify subscribers when the video goes public.
                "notifySubscribers": notify_subscribers,
                # AI-generated content disclosure — required by YouTube policy
                # for any video that uses AI to create visuals, voice, or script.
                # containsSyntheticMedia was added to the Data API v3 in 2024.
                "containsSyntheticMedia": ai_generated,
            },
        }

    async def post_top_level_comment(self, video_id: str, text: str) -> Dict[str, Any]:
        """
        Post a top-level comment on a video via commentThreads.insert.

        Note: the YouTube Data API has no endpoint to PIN a comment —
        pinning is a UI-only action (confirmed against the current API
        docs, not just an oversight here). This posts the comment so
        it's seeded immediately after upload; pinning it still requires
        one manual tap in YouTube Studio or the app.
        """
        return await self._request(
            "POST",
            "commentThreads",
            params={"part": "snippet"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": text},
                    },
                }
            },
        )

    async def close(self) -> None:
        await self.session.aclose()