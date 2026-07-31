from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analytics_agent.service import AnalyticsAgentService
from app.core.exceptions import NotFoundError
from app.database.models.analytics import Analytics
from app.database.models.upload import UploadStatus
from app.database.repositories.analytics_repository import AnalyticsRepository
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository

_DEFAULT_WINDOW_DAYS = 28


class AnalyticsService:
    """
    Analytics API Service.

    Responsibilities:
    - Resolve internal video_id → Upload record → youtube_video_id.
    - Delegate the actual YouTube Analytics API call to AnalyticsAgentService.
    - Expose snapshot listing via AnalyticsRepository.
    - Never write raw SQL; all DB operations go through repositories.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._video_repo = VideoRepository(session)
        self._upload_repo = UploadRepository(session)
        self._analytics_repo = AnalyticsRepository(session)
        self._agent_svc = AnalyticsAgentService(session)

    async def fetch_for_video(
        self,
        video_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Analytics:
        """
        Fetch a fresh analytics snapshot from YouTube and persist it.

        Raises ``NotFoundError`` when the video or its upload record are not
        found, or when the video has not been published to YouTube yet.
        """
        # 1 — Verify the video exists.
        video = await self._video_repo.get_by_id(video_id)
        if video is None:
            raise NotFoundError("Video", video_id)

        # 2 — Verify an Upload record exists and the video is on YouTube.
        upload = await self._upload_repo.get_by_video_id(video_id)
        if upload is None:
            raise NotFoundError("Upload", video_id)

        if upload.status != UploadStatus.PUBLISHED or not upload.youtube_video_id:
            raise NotFoundError(
                "Published upload for video",
                video_id,
            )

        # 3 — Default date range: last 28 days.
        today = date.today()
        resolved_end = end_date or today
        resolved_start = start_date or (resolved_end - timedelta(days=_DEFAULT_WINDOW_DAYS))

        # 4 — Delegate to the agent service which calls YouTube & saves the row.
        return await self._agent_svc.fetch_for_upload(
            upload=upload,
            start_date=resolved_start,
            end_date=resolved_end,
        )

    async def get_latest(self, video_id: UUID) -> Analytics:
        """
        Return the most recently stored Analytics snapshot for a video.

        Raises ``NotFoundError`` when the video, its upload, or any snapshot
        are not found.
        """
        video = await self._video_repo.get_by_id(video_id)
        if video is None:
            raise NotFoundError("Video", video_id)

        upload = await self._upload_repo.get_by_video_id(video_id)
        if upload is None:
            raise NotFoundError("Upload", video_id)

        snapshot = await self._analytics_repo.get_latest_by_upload_id(upload.id)
        if snapshot is None:
            raise NotFoundError("Analytics snapshot for video", video_id)

        return snapshot

    async def list_for_video(self, video_id: UUID) -> list[Analytics]:
        """
        Return all Analytics snapshots for a video, newest first.

        Raises ``NotFoundError`` when the video or its upload are not found.
        """
        video = await self._video_repo.get_by_id(video_id)
        if video is None:
            raise NotFoundError("Video", video_id)

        upload = await self._upload_repo.get_by_video_id(video_id)
        if upload is None:
            raise NotFoundError("Upload", video_id)

        return await self._analytics_repo.get_by_upload_id(upload.id)