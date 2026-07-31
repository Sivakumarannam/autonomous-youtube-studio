from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.storyboard_agent.models import StoryboardRequest
from app.agents.storyboard_agent.service import StoryboardService
from app.database.repositories.storyboard_repository import StoryboardRepository


class StoryboardAPIService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = StoryboardService()
        self.repository = StoryboardRepository(db)

    async def generate(
        self,
        script_id: UUID,
        script: str,
    ):
        request = StoryboardRequest(script=script)

        result = await self.agent.generate(request)

        scenes = {
            "scenes": [
                scene.model_dump()
                for scene in result.scenes
            ]
        }

        storyboard = await self.repository.create_storyboard(
            script_id=script_id,
            scenes=scenes,
        )

        return storyboard

    async def get(
        self,
        storyboard_id: UUID,
    ):
        return await self.repository.get_or_raise(
            storyboard_id,
        )

    async def update(
        self,
        storyboard_id: UUID,
        scenes: dict,
    ):
        storyboard = await self.repository.get_or_raise(
            storyboard_id,
        )

        return await self.repository.update_storyboard(
            storyboard,
            scenes,
        )

    async def delete(
        self,
        storyboard_id: UUID,
    ):
        storyboard = await self.repository.get_or_raise(
            storyboard_id,
        )

        await self.repository.delete_storyboard(
            storyboard,
        )

        return {
            "message": "Storyboard deleted successfully."
        }