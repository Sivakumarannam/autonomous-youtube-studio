from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.thumbnail_agent.service import ThumbnailAgentService
from app.core.exceptions import NotFoundError
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.thumbnail_repository import ThumbnailRepository
from app.database.repositories.video_repository import VideoRepository


class ThumbnailAPIService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.thumbnail_repo = ThumbnailRepository(db)
        self.script_repo = ScriptRepository(db)
        self.agent_service = ThumbnailAgentService(db)

    async def generate(
        self,
        script_id: UUID,
        niche: str = "technology",
    ):
        script = await self.script_repo.get_by_id_or_raise(script_id)

        await self.agent_service.run_for_script(
            script=script,
            niche=niche,
        )

        thumbnail = await self.thumbnail_repo.get_by_script_id(script_id)
        if thumbnail is None:
            raise NotFoundError("Thumbnail", script_id)

        return thumbnail

    async def get(self, thumbnail_id: UUID):
        return await self.thumbnail_repo.get_or_raise(thumbnail_id)

    async def get_by_script(self, script_id: UUID):
        thumbnail = await self.thumbnail_repo.get_by_script_id(script_id)
        if thumbnail is None:
            raise NotFoundError("Thumbnail", script_id)
        return thumbnail

    async def update(self, thumbnail_id: UUID, **kwargs):
        thumbnail = await self.thumbnail_repo.get_or_raise(thumbnail_id)
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if updates:
            thumbnail = await self.thumbnail_repo.update_thumbnail(thumbnail, **updates)
        return thumbnail

    async def delete(self, thumbnail_id: UUID) -> dict:
        thumbnail = await self.thumbnail_repo.get_or_raise(thumbnail_id)
        await self.thumbnail_repo.delete_thumbnail(thumbnail)
        return {"message": "Thumbnail deleted successfully."}