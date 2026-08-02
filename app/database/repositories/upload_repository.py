from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.video import Video
from app.database.repositories.base_repository import BaseRepository
from app.websocket.manager import broadcast_safe


class UploadRepository(BaseRepository[Upload]):
    """Repository for Upload model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Upload, session)

    async def update(self, obj: Upload, **kwargs: Any) -> Upload:
        """Update an Upload and broadcast the change over WebSocket.

        Covers publish/reject/schedule transitions and Scheduler-driven
        status changes, all of which route through this method.
        """
        updated = await super().update(obj, **kwargs)
        await broadcast_safe(
            {
                "type": "upload",
                "event": "updated",
                "id": str(updated.id),
                "status": updated.status.value
                if hasattr(updated.status, "value")
                else str(updated.status),
                "publish_status": updated.publish_status.value
                if hasattr(updated.publish_status, "value")
                else str(updated.publish_status),
                "scheduled_at": updated.scheduled_at,
            }
        )
        return updated

    async def get_by_video_id(self, video_id: UUID) -> Upload | None:
        result = await self.session.execute(
            select(Upload).where(Upload.video_id == video_id)
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, upload_id: UUID) -> Upload:
        upload = await self.get_by_id(upload_id)
        if upload is None:
            raise NotFoundError("Upload", upload_id)
        return upload

    async def get_all_by_status(
        self,
        status: UploadStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Upload]:
        stmt = select(Upload)
        if status is not None:
            stmt = stmt.where(Upload.status == status)
        stmt = stmt.order_by(Upload.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_publish_status(
        self,
        publish_status: PublishStatus,
        limit: int = 50,
    ) -> list[Upload]:
        result = await self.session.execute(
            select(Upload)
            .where(Upload.publish_status == publish_status)
            .order_by(Upload.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_due_for_publish(self) -> list[Upload]:
        """Return uploads that the Scheduler should now push to YouTube.

        Criteria:
          - publish_status = SCHEDULED  (editorial approval done)
          - scheduled_at  <= now()      (delay window has passed)
          - UploadStatus  not in (PUBLISHED, UPLOADING)  (not already in flight)
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Upload).where(
                and_(
                    Upload.publish_status == PublishStatus.SCHEDULED,
                    Upload.scheduled_at <= now,
                    Upload.status.notin_(
                        [UploadStatus.PUBLISHED, UploadStatus.UPLOADING]
                    ),
                )
            )
        )
        return list(result.scalars().all())

    async def mark_uploading(self, upload: Upload) -> Upload:
        return await self.update(upload, status=UploadStatus.UPLOADING)

    async def mark_published(
        self,
        upload: Upload,
        youtube_video_id: str,
        youtube_url: str,
        response_data: str | None = None,
    ) -> Upload:
        return await self.update(
            upload,
            status=UploadStatus.PUBLISHED,
            youtube_video_id=youtube_video_id,
            youtube_url=youtube_url,
            published_at=datetime.now(timezone.utc),
            response_data=response_data,
            error_message=None,
        )

    async def mark_failed(self, upload: Upload, error_message: str) -> Upload:
        return await self.update(
            upload,
            status=UploadStatus.FAILED,
            error_message=error_message,
        )

    async def get_due_for_instagram(self) -> list[Upload]:
        """Return published uploads whose instagram_scheduled_at has passed and not yet posted.

        Excludes rows marked instagram_failed_permanently=True so the scheduler
        never retries an upload that has already exhausted its attempt cap.
        """
        from sqlalchemy import and_, select
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Upload).where(
                and_(
                    Upload.status == UploadStatus.PUBLISHED,
                    Upload.instagram_posted.is_(False),
                    Upload.instagram_scheduled_at.isnot(None),
                    Upload.instagram_scheduled_at <= now,
                    Upload.instagram_failed_permanently.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    async def mark_instagram_failed_permanently(self, upload: Upload) -> Upload:
        """Mark an upload as permanently failed for Instagram cross-posting.

        Called when instagram_retry_count reaches the cap (3 attempts).
        The row is then excluded from get_due_for_instagram() forever.
        """
        return await self.update(
            upload,
            instagram_failed_permanently=True,
        )

    async def mark_instagram_posted(
        self, upload: Upload, media_id: str
    ) -> Upload:
        return await self.update(
            upload,
            instagram_posted=True,
            instagram_posted_at=datetime.now(timezone.utc),
            instagram_media_id=media_id,
        )

    async def delete_upload(self, upload: Upload) -> None:
        """Delete an Upload and any Analytics rows tied to it.

        Analytics.upload_id is NOT NULL, so simply deleting the Upload
        would make SQLAlchemy try to null out that FK on any linked
        Analytics row and violate the constraint. Analytics data for a
        deleted video is no longer meaningful anyway, so we remove it
        first, in the same transaction.
        """
        from sqlalchemy import delete as sa_delete
        from app.database.models.analytics import Analytics

        await self.session.execute(
            sa_delete(Analytics).where(Analytics.upload_id == upload.id)
        )
        await self.delete(upload)

    async def get_published_videos(self, limit: int = 15) -> list[Upload]:
        """Get recently published videos with related video and script info.

        Eagerly loads Upload.video and Video.script so the dashboard
        template can render upload.video.script.title without triggering
        a lazy-load outside the async session context (which raises
        MissingGreenlet).
        """
        result = await self.session.execute(
            select(Upload)
            .options(selectinload(Upload.video).selectinload(Video.script))
            .where(Upload.status == UploadStatus.PUBLISHED)
            .order_by(Upload.published_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())