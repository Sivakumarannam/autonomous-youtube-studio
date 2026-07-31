import json
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.channel import ChannelCreate, ChannelUpdate
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.channel import Channel, ChannelStatus
from app.database.repositories.channel_repository import ChannelRepository

logger = get_logger(__name__)


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ChannelRepository(session)

    async def create(self, data: ChannelCreate) -> Channel:
        existing = await self._repo.get_by_name(data.name)
        if existing:
            raise ValidationError(f"Channel with name '{data.name}' already exists")

        channel = Channel(
            name=data.name,
            description=data.description,
            niche=data.niche,
            language=data.language,
            content_type=data.content_type,
            aspect_ratio=data.aspect_ratio,
            target_duration=data.target_duration,
            upload_schedule=data.upload_schedule,
            youtube_channel_id=data.youtube_channel_id,
        )
        created = await self._repo.create(channel)
        logger.info("Channel created", channel_id=str(created.id), name=created.name)
        return created

    async def get_by_id(self, channel_id: UUID) -> Channel:
        return await self._repo.get_by_id_or_raise(channel_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> tuple[Sequence[Channel], int]:
        channels = await self._repo.get_all(limit=limit, offset=offset)
        total = await self._repo.count()
        return channels, total

    async def get_active(self) -> Sequence[Channel]:
        return await self._repo.get_active()

    async def update(self, channel_id: UUID, data: ChannelUpdate) -> Channel:
        channel = await self._repo.get_by_id_or_raise(channel_id)
        update_kwargs = data.model_dump(exclude_none=True)

        if "name" in update_kwargs:
            existing = await self._repo.get_by_name(update_kwargs["name"])
            if existing and existing.id != channel_id:
                raise ValidationError(f"Channel name '{update_kwargs['name']}' already taken")

        updated = await self._repo.update(channel, **update_kwargs)
        logger.info("Channel updated", channel_id=str(channel_id))
        return updated

    async def delete(self, channel_id: UUID) -> None:
        channel = await self._repo.get_by_id_or_raise(channel_id)
        await self._repo.delete(channel)
        logger.info("Channel deleted", channel_id=str(channel_id))

    async def set_status(self, channel_id: UUID, status: ChannelStatus) -> Channel:
        channel = await self._repo.set_status(channel_id, status)
        if channel is None:
            raise NotFoundError("Channel", channel_id)
        return channel