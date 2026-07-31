from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.database.models.thumbnail import Thumbnail
from app.database.repositories.base_repository import BaseRepository


class ThumbnailRepository(BaseRepository[Thumbnail]):
    def __init__(self, session):
        super().__init__(Thumbnail, session)

    async def get_by_script_id(
        self,
        script_id: UUID,
    ) -> Thumbnail | None:
        result = await self.session.execute(
            select(Thumbnail).where(
                Thumbnail.script_id == script_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_raise(
        self,
        thumbnail_id: UUID,
    ) -> Thumbnail:
        thumbnail = await self.get_by_id(thumbnail_id)

        if thumbnail is None:
            raise NotFoundError(
                "Thumbnail",
                thumbnail_id,
            )

        return thumbnail

    async def create_thumbnail(
        self,
        script_id: UUID,
        concept: str | None = None,
        file_path: str | None = None,
        status=None,
    ) -> Thumbnail:
        thumbnail = Thumbnail(
            script_id=script_id,
            concept=concept,
            file_path=file_path,
            status=status,
        )

        return await self.create(thumbnail)

    async def update_thumbnail(
        self,
        thumbnail: Thumbnail,
        **kwargs,
    ) -> Thumbnail:
        return await self.update(
            thumbnail,
            **kwargs,
        )

    async def delete_thumbnail(
        self,
        thumbnail: Thumbnail,
    ) -> None:
        await self.delete(thumbnail)