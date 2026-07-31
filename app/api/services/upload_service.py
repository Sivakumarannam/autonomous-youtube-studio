import json
from uuid import UUID

from app.agents.upload_agent.models import UploadSettings
from app.agents.upload_agent.service import UploadAgentService
from app.core.exceptions import NotFoundError, UploadError
from app.database.models.upload import Upload, UploadStatus
from app.database.models.video import VideoStatus
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository


class UploadService:
    """
    Upload API Service.

    Responsibilities:
    - Validate Video exists and is COMPLETE.
    - Create or reset the Upload record.
    - Delegate the actual YouTube upload to UploadAgentService.
    - Return ORM objects; never write raw SQL.
    """

    def __init__(self, session):
        self.session = session
        self.video_repository = VideoRepository(session)
        self.upload_repository = UploadRepository(session)
        self.upload_agent = UploadAgentService(session)

    async def trigger_upload(
        self,
        video_id: UUID,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        privacy_status: str = "private",
    ) -> Upload:
        """
        Trigger a YouTube upload for a completed video.

        - PUBLISHED → return existing record unchanged (idempotent).
        - UPLOADING  → raise UploadError (another upload is in progress).
        - PENDING / FAILED → (re)set and run.
        """
        video = await self.video_repository.get_by_id(video_id)
        if video is None:
            raise NotFoundError("Video", video_id)

        if video.status != VideoStatus.COMPLETE:
            raise UploadError(
                f"Video {video_id} is not ready to upload "
                f"(status: {video.status.value}). "
                "Generate and complete the video first."
            )

        existing = await self.upload_repository.get_by_video_id(video_id)

        if existing is not None:
            if existing.status == UploadStatus.PUBLISHED:
                return existing
            if existing.status == UploadStatus.UPLOADING:
                raise UploadError(
                    f"Video {video_id} upload is already in progress."
                )
            # PENDING or FAILED — reset metadata and retry
            upload = await self.upload_repository.update(
                existing,
                status=UploadStatus.PENDING,
                title=title,
                description=description,
                tags=json.dumps(tags or []),
                privacy_status=privacy_status,
                youtube_video_id=None,
                youtube_url=None,
                error_message=None,
                response_data=None,
                published_at=None,
            )
        else:
            upload = Upload(
                video_id=video_id,
                title=title,
                description=description,
                tags=json.dumps(tags or []),
                privacy_status=privacy_status,
                status=UploadStatus.PENDING,
            )
            self.session.add(upload)
            await self.session.flush()
            await self.session.refresh(upload)

        settings = UploadSettings(
            title=title or "",
            description=description or "",
            tags=tags or [],
        )
        return await self.upload_agent.run_upload_for_video(
            video=video,
            upload=upload,
            settings=settings,
        )

    async def get_upload(self, upload_id: UUID) -> Upload:
        return await self.upload_repository.get_or_raise(upload_id)

    async def get_by_video(self, video_id: UUID) -> Upload:
        video = await self.video_repository.get_by_id(video_id)
        if video is None:
            raise NotFoundError("Video", video_id)

        upload = await self.upload_repository.get_by_video_id(video_id)
        if upload is None:
            raise NotFoundError("Upload", video_id)
        return upload

    async def list_uploads(
        self,
        status: UploadStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Upload]:
        return await self.upload_repository.get_all_by_status(
            status=status,
            limit=limit,
            offset=offset,
        )

    async def delete_upload(self, upload_id: UUID) -> None:
        upload = await self.upload_repository.get_or_raise(upload_id)
        await self.upload_repository.delete_upload(upload)