from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.script import Script, ScriptType, ScriptStatus
from app.database.repositories.base_repository import BaseRepository


class ScriptRepository(BaseRepository[Script]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Script, session)

    async def get_by_topic_id(self, topic_id: UUID) -> Sequence[Script]:
        result = await self.session.execute(
            select(Script)
            .where(Script.topic_id == topic_id)
            .order_by(desc(Script.created_at))
        )
        return result.scalars().all()

    async def get_by_channel(
        self,
        channel_id: UUID,
        script_type: Optional[ScriptType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Script]:
        conditions = [Script.channel_id == channel_id]
        if script_type is not None:
            conditions.append(Script.script_type == script_type)
        result = await self.session.execute(
            select(Script)
            .where(and_(*conditions))
            .order_by(desc(Script.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_status(
        self,
        status: ScriptStatus,
        script_type: Optional[ScriptType] = None,
        limit: int = 50,
    ) -> Sequence[Script]:
        conditions = [Script.status == status]
        if script_type is not None:
            conditions.append(Script.script_type == script_type)
        result = await self.session.execute(
            select(Script)
            .where(and_(*conditions))
            .order_by(desc(Script.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_approved(self, script_type: Optional[ScriptType] = None, limit: int = 50) -> Sequence[Script]:
        return await self.get_by_status(ScriptStatus.APPROVED, script_type, limit)

    async def get_drafts(self, script_type: Optional[ScriptType] = None, limit: int = 50) -> Sequence[Script]:
        return await self.get_by_status(ScriptStatus.DRAFT, script_type, limit)

    async def set_status(self, script_id: UUID, status: ScriptStatus) -> Optional[Script]:
        script = await self.get_by_id(script_id)
        if script is None:
            return None
        return await self.update(script, status=status)

    async def get_for_topic_and_type(
        self, topic_id: UUID, script_type: ScriptType
    ) -> Optional[Script]:
        result = await self.session.execute(
            select(Script).where(
                and_(Script.topic_id == topic_id, Script.script_type == script_type)
            )
        )
        return result.scalar_one_or_none()

    async def count_by_channel_and_type(
        self, channel_id: UUID, script_type: ScriptType
    ) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count()).select_from(Script).where(
                and_(
                    Script.channel_id == channel_id,
                    Script.script_type == script_type,
                )
            )
        )
        return result.scalar_one()