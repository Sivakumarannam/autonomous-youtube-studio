from __future__ import annotations

import inspect
from typing import Any, Dict, Iterable, Optional

import httpx

from .auth import YouTubeAuthManager


class YouTubeAnalyticsService:
    def __init__(
        self,
        auth_manager: YouTubeAuthManager,
        base_url: str = "https://youtubeanalytics.googleapis.com/v2",
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

    async def fetch_video_analytics(
        self,
        video_id: str,
        start_date: str,
        end_date: str,
        metrics: Optional[Iterable[str]] = None,
        dimensions: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch analytics for a single YouTube video.

        When *dimensions* is ``None`` (the default) the request is sent without
        a ``dimensions`` parameter, which causes the YouTube Analytics API to
        return a single aggregated row for the requested date range.

        Pass a non-empty iterable to *dimensions* (e.g. ``["day"]``) to receive
        per-dimension rows instead.
        """
        params: Dict[str, str] = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "metrics": ",".join(
                metrics
                or [
                    "views",
                    "likes",
                    "comments",
                    "shares",
                    "estimatedMinutesWatched",
                    "averageViewDuration",
                    "averageViewPercentage",
                    "subscribersGained",
                    "subscribersLost",
                    "impressions",
                    "impressionClickThroughRate",
                ]
            ),
            "filters": f"video=={video_id}",
        }

        if dimensions is not None:
            dim_str = ",".join(dimensions)
            if dim_str:
                params["dimensions"] = dim_str

        headers = await self._headers()
        response = await self.session.get(
            f"{self.base_url}/reports",
            headers=headers,
            params=params,
        )

        # IMPORTANT: show real Google error before raising
        if response.status_code != 200:
            print("\n========== YOUTUBE ANALYTICS ERROR ==========")
            print("STATUS:", response.status_code)
            print("URL:", str(response.url))
            print("RESPONSE:", response.text)
            print("============================================\n")

        # now raise normally (so your flow still fails correctly)
        response.raise_for_status()

        return response.json()

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def close(self) -> None:
        await self.session.aclose()
