from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.script import ScriptUpdate
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.database.models.script import Script, ScriptType, ScriptStatus
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository

logger = get_logger(__name__)


class ScriptService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ScriptRepository(session)
        self._topic_repo = TopicRepository(session)
        self._channel_repo = ChannelRepository(session)

    async def get_by_id(self, script_id: UUID) -> Script:
        return await self._repo.get_by_id_or_raise(script_id)

    async def get_by_channel(
        self,
        channel_id: UUID,
        script_type: Optional[ScriptType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Script], int]:
        await self._channel_repo.get_by_id_or_raise(channel_id)
        scripts = await self._repo.get_by_channel(channel_id, script_type, limit, offset)
        total = await self._repo.count()
        return scripts, total

    async def get_by_topic(self, topic_id: UUID) -> Sequence[Script]:
        await self._topic_repo.get_by_id_or_raise(topic_id)
        return await self._repo.get_by_topic_id(topic_id)

    async def get_all(
        self,
        limit: int = 50,
        offset: int = 0,
        script_type: Optional[ScriptType] = None,
        status: Optional[ScriptStatus] = None,
    ) -> tuple[Sequence[Script], int]:
        if status is not None:
            scripts = await self._repo.get_by_status(status, script_type, limit)
            total = len(scripts)
        else:
            scripts = await self._repo.get_all(limit=limit, offset=offset)
            total = await self._repo.count()
        return scripts, total

    async def update(self, script_id: UUID, data: ScriptUpdate) -> Script:
        script = await self._repo.get_by_id_or_raise(script_id)
        update_kwargs = data.model_dump(exclude_none=True)
        updated = await self._repo.update(script, **update_kwargs)
        logger.info("Script updated", script_id=str(script_id))
        return updated

    async def set_status(self, script_id: UUID, status: ScriptStatus) -> Script:
        script = await self._repo.set_status(script_id, status)
        if script is None:
            raise NotFoundError("Script", script_id)
        return script

    async def delete(self, script_id: UUID) -> None:
        script = await self._repo.get_by_id_or_raise(script_id)
        await self._repo.delete(script)
        logger.info("Script deleted", script_id=str(script_id))