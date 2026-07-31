"""Publishing Workflow Service.

Enforces legal publish_status transitions and exposes query/mutation
operations for the publishing API endpoints.

Legal transitions (enforced here — reject all others):
    DRAFT     → APPROVED    (pipeline auto-approval only)
    APPROVED  → SCHEDULED   (set scheduled_at; pipeline or manual)
    APPROVED  → REJECTED    (manual reject)
    SCHEDULED → REJECTED    (manual reject — safety window intervention)

All other transitions raise PublishError.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, PublishError
from app.core.logging import get_logger
from app.database.models.upload import Upload, PublishStatus, UploadStatus
from app.database.repositories.upload_repository import UploadRepository

logger = get_logger(__name__)

# Allowed from → to transitions for external callers.
_LEGAL_TRANSITIONS: dict[PublishStatus, set[PublishStatus]] = {
    PublishStatus.DRAFT: {PublishStatus.APPROVED},
    PublishStatus.APPROVED: {PublishStatus.SCHEDULED, PublishStatus.REJECTED},
    PublishStatus.SCHEDULED: {PublishStatus.REJECTED},
}


class PublishingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._upload_repo = UploadRepository(session)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, upload_id: UUID) -> Upload:
        return await self._upload_repo.get_or_raise(upload_id)

    async def list_uploads(
        self,
        publish_status: PublishStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Upload]:
        if publish_status is not None:
            return await self._upload_repo.get_by_publish_status(
                publish_status, limit=limit
            )
        return await self._upload_repo.get_all_by_status(limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    async def approve(self, upload_id: UUID) -> Upload:
        """Approve a DRAFT upload (DRAFT → APPROVED).

        Used in manual mode (auto_publish_enabled=False) to advance the upload
        after a human review. The Scheduler will not pick it up until it also
        reaches SCHEDULED (via a subsequent /schedule call or auto-scheduling).
        """
        upload = await self._upload_repo.get_or_raise(upload_id)
        self._assert_transition(upload, PublishStatus.APPROVED)

        upload = await self._upload_repo.update(
            upload, publish_status=PublishStatus.APPROVED
        )
        logger.info("Upload approved.", upload_id=str(upload_id))
        return upload

    async def reject(self, upload_id: UUID, reason: str | None = None) -> Upload:
        """Reject an APPROVED or SCHEDULED upload (safety window intervention)."""
        upload = await self._upload_repo.get_or_raise(upload_id)
        self._assert_transition(upload, PublishStatus.REJECTED)

        # Guard: never reject a video that is already uploading or published.
        if upload.status in (UploadStatus.UPLOADING, UploadStatus.PUBLISHED):
            raise PublishError(
                f"Cannot reject upload {upload_id}: YouTube upload is already "
                f"{upload.status.value}."
            )

        upload = await self._upload_repo.update(
            upload,
            publish_status=PublishStatus.REJECTED,
            error_message=reason or "Rejected via publishing API.",
        )
        logger.info(
            "Upload rejected.",
            upload_id=str(upload_id),
            reason=reason,
        )
        return upload

    async def schedule(
        self, upload_id: UUID, scheduled_at: datetime
    ) -> Upload:
        """Manually set scheduled_at on an APPROVED upload → SCHEDULED."""
        upload = await self._upload_repo.get_or_raise(upload_id)
        self._assert_transition(upload, PublishStatus.SCHEDULED)

        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

        upload = await self._upload_repo.update(
            upload,
            publish_status=PublishStatus.SCHEDULED,
            scheduled_at=scheduled_at,
            status=UploadStatus.SCHEDULED,
        )
        logger.info(
            "Upload scheduled.",
            upload_id=str(upload_id),
            scheduled_at=scheduled_at.isoformat(),
        )
        return upload

    # ------------------------------------------------------------------
    # Deletion (destructive — removes from YouTube AND local records)
    # ------------------------------------------------------------------

    async def delete_video_everywhere(self, upload_id: UUID) -> None:
        """Delete a video from YouTube AND remove its local Upload record.

        Irreversible. Order matters: delete from YouTube FIRST. If that
        succeeds, then remove the local record. If the YouTube delete
        fails, the local record is kept so the failure stays visible and
        nothing is silently lost.
        """
        from app.integrations.youtube.auth import YouTubeAuthManager
        from app.integrations.youtube.client import YouTubeApiClient

        upload = await self._upload_repo.get_or_raise(upload_id)

        if not upload.youtube_video_id:
            # Never made it to YouTube — just clean up locally.
            await self._upload_repo.delete_upload(upload)
            logger.info(
                "Upload deleted (no YouTube video to remove).",
                upload_id=str(upload_id),
            )
            return

        auth = YouTubeAuthManager(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            refresh_token=settings.youtube_refresh_token,
        )
        client = YouTubeApiClient(auth)

        try:
            await client.delete_video(upload.youtube_video_id)
        finally:
            await client.close()
            await auth.close()

        await self._upload_repo.delete_upload(upload)
        logger.info(
            "Video deleted from YouTube and local record removed.",
            upload_id=str(upload_id),
            youtube_video_id=upload.youtube_video_id,
        )

    async def delete_local_only(self, upload_id: UUID) -> None:
        """Remove only the local Upload record — no YouTube API call.

        Used exclusively for the "already deleted on YouTube" confirmation
        flow: the user has explicitly confirmed the video is gone from
        YouTube already, so we skip delete_video entirely and just clean
        up our own record.
        """
        upload = await self._upload_repo.get_or_raise(upload_id)
        await self._upload_repo.delete_upload(upload)
        logger.info(
            "Local upload record removed (video already gone from YouTube).",
            upload_id=str(upload_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------------------------------------------------------------------

    def _assert_transition(
        self, upload: Upload, target: PublishStatus
    ) -> None:
        """Raise PublishError if the current → target transition is illegal."""
        current = upload.publish_status
        allowed = _LEGAL_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise PublishError(
                f"Cannot transition publish_status from {current.value!r} "
                f"to {target.value!r}. "
                f"Allowed targets from {current.value!r}: "
                f"{[s.value for s in allowed] or 'none'}."
            )