from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.storyboard_agent.models import StoryboardRequest
from app.agents.storyboard_agent.service import StoryboardService
from app.agents.thumbnail_agent.service import ThumbnailAgentService
from app.agents.video_agent.service import VideoAgentService
from app.agents.voice_agent.service import VoiceAgentService
from app.agents.upload_agent.service import UploadAgentService

from app.database.models.video import Video

from app.core.logging import get_logger

logger = get_logger(__name__)


class PublishingWorkflow:

    def __init__(self, session: AsyncSession):

        self.session = session

        self.storyboard = StoryboardService()

        self.thumbnail = ThumbnailAgentService(session)

        self.voice = VoiceAgentService(session)

        self.video = VideoAgentService(session)

        self.upload = UploadAgentService(session)

    async def run(
        self,
        script,
        niche: str = "technology",
    ):

        logger.info("Publishing workflow started")

        storyboard = await self.storyboard.generate(
            StoryboardRequest(
                script=script.content,
            )
        )

        voice = await self.voice.run_for_script(
            script,
        )

        result = await self.session.execute(
            select(Video).where(
                Video.script_id == script.id
            )
        )

        video = result.scalar_one()

        thumbnail = await self.thumbnail.run_for_script(
            script=script,
            video=video,
            niche=niche,
        )

        rendered_video = await self.video.run_for_script(
            script=script,
            topic_title=script.seo_title or "",
        )

        upload = await self.upload.run_for_video(
            video_title=rendered_video.title,
        )

        logger.info("Publishing workflow completed")

        return {
            "storyboard": storyboard,
            "voice": voice,
            "thumbnail": thumbnail,
            "video": rendered_video,
            "upload": upload,
        }