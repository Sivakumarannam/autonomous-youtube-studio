from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.models.video import Video, VideoStatus
from app.database.repositories.base_repository import BaseRepository


class VideoRepository(BaseRepository[Video]):
    """
    Repository for Video model.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Video, session)

    async def get_by_script_id(
        self,
        script_id: UUID,
    ) -> Video | None:
        """
        Return the video record for a script.
        """
        result = await self.session.execute(
            select(Video).where(
                Video.script_id == script_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_raise(
        self,
        video_id: UUID,
    ) -> Video:
        """
        Return a video or raise NotFoundError.
        """
        video = await self.get_by_id(video_id)

        if video is None:
            raise NotFoundError(
                "Video",
                video_id,
            )

        return video

    async def get_pending(
        self,
        limit: int = 10,
    ) -> list[Video]:
        """
        Get pending video generation jobs.
        """
        result = await self.session.execute(
            select(Video)
            .where(
                Video.status == VideoStatus.PENDING
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_generating(
        self,
        limit: int = 10,
    ) -> list[Video]:
        """
        Get currently generating videos.
        """
        result = await self.session.execute(
            select(Video)
            .where(
                Video.status == VideoStatus.GENERATING
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_completed(
        self,
        limit: int = 20,
    ) -> list[Video]:
        """
        Get completed videos.
        """
        result = await self.session.execute(
            select(Video)
            .where(
                Video.status == VideoStatus.COMPLETE
            )
            .order_by(
                Video.created_at.desc()
            )
            .limit(limit)
        )

        return list(result.scalars().all())

    async def update_video(
        self,
        video: Video,
        **kwargs,
    ) -> Video:
        """
        Update a video record.
        """
        return await self.update(
            video,
            **kwargs,
        )

    async def mark_generating(
        self,
        video: Video,
    ) -> Video:
        """
        Mark a video as generating.
        """
        return await self.update(
            video,
            status=VideoStatus.GENERATING,
        )

    async def mark_complete(
        self,
        video: Video,
        video_path: str,
        duration: float,
        file_size: int,
    ) -> Video:
        """
        Mark a video as complete.
        """
        return await self.update(
            video,
            status=VideoStatus.COMPLETE,
            video_path=video_path,
            duration=duration,
            file_size=file_size,
            error_message=None,
        )

    async def mark_failed(
        self,
        video: Video,
        error_message: str,
    ) -> Video:
        """
        Mark a video as failed.
        """
        return await self.update(
            video,
            status=VideoStatus.FAILED,
            error_message=error_message,
        )

    async def delete_video(
        self,
        video: Video,
    ) -> None:
        """
        Delete a video record.
        """
        await self.delete(video)