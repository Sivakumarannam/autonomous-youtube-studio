from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel, ChannelStatus
from app.database.repositories.base_repository import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Channel, session)

    async def get_by_name(self, name: str) -> Optional[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.name == name)
        )
        return result.scalar_one_or_none()

    async def get_active(self) -> Sequence[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.status == ChannelStatus.ACTIVE)
        )
        return result.scalars().all()

    async def get_by_youtube_id(self, youtube_channel_id: str) -> Optional[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.youtube_channel_id == youtube_channel_id)
        )
        return result.scalar_one_or_none()

    async def get_by_niche(self, niche: str) -> Sequence[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.niche.ilike(f"%{niche}%"))
        )
        return result.scalars().all()

    async def set_status(self, channel_id: UUID, status: ChannelStatus) -> Optional[Channel]:
        channel = await self.get_by_id(channel_id)
        if channel is None:
            return None
        return await self.update(channel, status=status)