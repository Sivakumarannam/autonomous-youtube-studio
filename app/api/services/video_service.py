from uuid import UUID

from app.agents.video_agent.service import VideoAgentService
from app.core.exceptions import NotFoundError
from app.database.models.video import Video, VideoStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.video_repository import VideoRepository


class VideoService:
    """
    Video API Service.

    Responsibilities:
    - Validate Script
    - Prevent duplicate Video records
    - Call VideoAgent
    - Return ORM objects
    """

    def __init__(self, session):
        self.session = session

        self.script_repository = ScriptRepository(session)
        self.video_repository = VideoRepository(session)

        self.video_agent = VideoAgentService(session)

    async def generate_video(
        self,
        script_id: UUID,
    ) -> Video:
        """
        Generate video for a script.
        """

        script = await self.script_repository.get_by_id(
            script_id
        )

        if script is None:
            raise NotFoundError(
                "Script",
                script_id,
            )

        existing_video = (
            await self.video_repository.get_by_script_id(
                script_id
            )
        )

        if existing_video is not None:
            if existing_video.status == VideoStatus.COMPLETE:
                # Already done — return immediately.
                return existing_video
            # GENERATING (stuck from a previous interrupted run) or FAILED:
            # delete and start fresh so the user always gets a real result.
            await self.video_repository.delete_video(existing_video)

        await self.video_agent.run_for_script(
            script=script,
            topic_title=script.seo_title or "Untitled",
            description=script.hook or script.content[:280],
            script_type=str(script.script_type),
        )

        video = await self.video_repository.get_by_script_id(
            script_id
        )

        if video is None:
            raise RuntimeError(
                "Video generation completed but Video record was not created."
            )

        return video

    async def regenerate_video(
        self,
        script_id: UUID,
    ) -> Video:
        """
        Force regenerate video.
        """

        script = await self.script_repository.get_by_id(
            script_id
        )

        if script is None:
            raise NotFoundError(
                "Script",
                script_id,
            )

        existing = (
            await self.video_repository.get_by_script_id(
                script_id
            )
        )

        if existing is not None:
            await self.video_repository.delete_video(
                existing
            )

        await self.video_agent.run_for_script(
            script=script,
            topic_title=script.seo_title or "Untitled",
            description=script.hook or script.content[:280],
            script_type=str(script.script_type),
        )

        video = await self.video_repository.get_by_script_id(
            script_id
        )

        if video is None:
            raise RuntimeError(
                "Video regeneration failed."
            )

        return video

    async def get_video(
        self,
        video_id: UUID,
    ) -> Video:
        """
        Get video by id.
        """

        return await self.video_repository.get_or_raise(
            video_id
        )

    async def get_by_script(
        self,
        script_id: UUID,
    ) -> Video:
        """
        Get video by script id.
        """

        video = (
            await self.video_repository.get_by_script_id(
                script_id
            )
        )

        if video is None:
            raise NotFoundError(
                "Video",
                script_id,
            )

        return video

    async def list_completed(
        self,
        limit: int = 20,
    ) -> list[Video]:
        """
        List completed videos.
        """

        return await self.video_repository.get_completed(
            limit=limit,
        )

    async def batch_generate(
        self,
        limit: int = 5,
    ) -> list:
        """
        Generate videos for approved scripts.
        """

        return (
            await self.video_agent.run_for_approved_scripts(
                limit=limit,
            )
        )

    async def delete_video(
        self,
        video_id: UUID,
    ) -> None:
        """
        Delete video.
        """

        video = (
            await self.video_repository.get_or_raise(
                video_id
            )
        )

        await self.video_repository.delete_video(
            video
        )