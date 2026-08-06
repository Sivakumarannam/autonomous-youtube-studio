from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_, or_
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
        for key, value in kwargs.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        updated = obj
        await broadcast_safe(
            {
                "type": "upload_updated",
                "upload_id": str(updated.id),
                "status": str(updated.status),
                "publish_status": str(updated.publish_status),
                "scheduled_at": updated.scheduled_at.isoformat()
                if updated.scheduled_at
                else None,
            }
        )
        return updated

    async def get_by_video_id(self, video_id: UUID) -> Upload | None:
        result = await self.session.execute(
            select(Upload).where(Upload.video_id == video_id)
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, upload_id: UUID) -> Upload:
        obj = await self.get(upload_id)
        if obj is None:
            raise NotFoundError("Upload", str(upload_id))
        return obj

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
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Upload).where(
                and_(
                    Upload.publish_status == PublishStatus.SCHEDULED,
                    Upload.scheduled_at <= now,
                    Upload.youtube_video_id.is_(None),
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
        youtube_url: str | None = None,
    ) -> Upload:
        # Note: PublishStatus has no PUBLISHED member (draft|approved|scheduled|rejected).
        # Live state is UploadStatus.PUBLISHED + youtube_video_id.
        return await self.update(
            upload,
            status=UploadStatus.PUBLISHED,
            youtube_video_id=youtube_video_id,
            youtube_url=youtube_url,
            published_at=datetime.now(timezone.utc),
        )

    async def mark_failed(self, upload: Upload, error_message: str) -> Upload:
        return await self.update(
            upload,
            status=UploadStatus.FAILED,
            error_message=error_message,
        )

    async def get_due_for_instagram(self) -> list[Upload]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Upload).where(
                and_(
                    Upload.status == UploadStatus.PUBLISHED,
                    Upload.instagram_scheduled_at.isnot(None),
                    Upload.instagram_scheduled_at <= now,
                    Upload.instagram_posted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def mark_instagram_failed_permanently(self, upload: Upload) -> Upload:
        return await self.update(upload, instagram_failed_permanently=True)

    async def mark_instagram_posted(self, upload: Upload) -> Upload:
        return await self.update(
            upload,
            instagram_posted_at=datetime.now(timezone.utc),
        )

    async def delete_upload(self, upload: Upload) -> None:
        from sqlalchemy import delete as sa_delete
        from app.database.models.analytics import Analytics

        await self.session.execute(
            sa_delete(Analytics).where(Analytics.upload_id == upload.id)
        )
        await self.delete(upload)

    async def get_published_videos(self, limit: int = 15) -> list[Upload]:
        result = await self.session.execute(
            select(Upload)
            .options(selectinload(Upload.video).selectinload(Video.script))
            .where(Upload.status == UploadStatus.PUBLISHED)
            .order_by(Upload.published_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_dashboard_videos(self, limit: int = 20) -> list[Upload]:
        """Pending schedule (no YT id) + live rows (status published or has youtube_id)."""
        opts = selectinload(Upload.video).selectinload(Video.script)

        scheduled = await self.session.execute(
            select(Upload)
            .options(opts)
            .where(
                and_(
                    Upload.publish_status == PublishStatus.SCHEDULED,
                    Upload.youtube_video_id.is_(None),
                    Upload.status.notin_(
                        [UploadStatus.PUBLISHED, UploadStatus.UPLOADING]
                    ),
                )
            )
            .order_by(Upload.scheduled_at.asc().nulls_last())
            .limit(limit)
        )
        published = await self.session.execute(
            select(Upload)
            .options(opts)
            .where(
                or_(
                    Upload.status == UploadStatus.PUBLISHED,
                    Upload.youtube_video_id.isnot(None),
                )
            )
            .order_by(Upload.published_at.desc().nulls_last())
            .limit(limit)
        )
        seen: set[str] = set()
        out: list[Upload] = []
        for u in list(scheduled.scalars().all()) + list(published.scalars().all()):
            key = str(u.id)
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
            if len(out) >= limit:
                break
        return out
