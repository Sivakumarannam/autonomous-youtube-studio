from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.research import Research, ResearchStatus
from app.database.repositories.base_repository import BaseRepository


class ResearchRepository(BaseRepository[Research]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Research, session)

    async def get_by_topic_id(self, topic_id: UUID) -> Optional[Research]:
        result = await self.session.execute(
            select(Research).where(Research.topic_id == topic_id)
        )
        return result.scalar_one_or_none()

    async def get_by_status(self, status: ResearchStatus, limit: int = 50) -> Sequence[Research]:
        result = await self.session.execute(
            select(Research)
            .where(Research.status == status)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_complete(self, limit: int = 50) -> Sequence[Research]:
        return await self.get_by_status(ResearchStatus.COMPLETE, limit)

    async def set_status(self, research_id: UUID, status: ResearchStatus) -> Optional[Research]:
        research = await self.get_by_id(research_id)
        if research is None:
            return None
        return await self.update(research, status=status)

    async def upsert_for_topic(self, topic_id: UUID, **kwargs) -> Research:
        existing = await self.get_by_topic_id(topic_id)
        if existing:
            return await self.update(existing, **kwargs)
        research = Research(topic_id=topic_id, **kwargs)
        return await self.create(research)