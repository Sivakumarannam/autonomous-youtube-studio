from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.storyboard import Storyboard
from app.database.repositories.base_repository import BaseRepository


class StoryboardRepository(BaseRepository[Storyboard]):
    def __init__(self, session: AsyncSession):
        super().__init__(Storyboard, session)

    async def get_by_script_id(
        self,
        script_id: UUID,
    ) -> Storyboard | None:

        result = await self.session.execute(
            select(Storyboard).where(
                Storyboard.script_id == script_id
            )
        )

        return result.scalar_one_or_none()

    async def create_storyboard(
        self,
        script_id: UUID,
        scenes: dict,
    ) -> Storyboard:

        storyboard = Storyboard(
            script_id=script_id,
            scenes=scenes,
        )

        return await self.create(storyboard)
    

    async def get_storyboard(
        self,
        storyboard_id: UUID,
    ) -> Storyboard | None:
        return await self.get_by_id(storyboard_id)


    async def update_storyboard(
        self,
        storyboard: Storyboard,
        scenes: dict,
    ) -> Storyboard:
        storyboard.scenes = scenes
        return await self.update(storyboard)


    async def delete_storyboard(
        self,
        storyboard: Storyboard,
    ) -> None:
        await self.delete(storyboard)


    async def get_or_raise(
        self,
        storyboard_id: UUID,
    ) -> Storyboard:
        return await self.get_by_id_or_raise(storyboard_id)