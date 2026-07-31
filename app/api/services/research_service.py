from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.research import Research, ResearchStatus
from app.database.repositories.research_repository import ResearchRepository
from app.database.repositories.topic_repository import TopicRepository

logger = get_logger(__name__)


class ResearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ResearchRepository(session)
        self._topic_repo = TopicRepository(session)

    async def get_by_id(self, research_id: UUID) -> Research:
        return await self._repo.get_by_id_or_raise(research_id)

    async def get_by_topic_id(self, topic_id: UUID) -> Optional[Research]:
        await self._topic_repo.get_by_id_or_raise(topic_id)
        return await self._repo.get_by_topic_id(topic_id)

    async def get_all(self, limit: int = 50, offset: int = 0) -> tuple[Sequence[Research], int]:
        research_list = await self._repo.get_all(limit=limit, offset=offset)
        total = await self._repo.count()
        return research_list, total

    async def create_or_update(
        self,
        topic_id: UUID,
        summary: str,
        key_facts: Optional[str] = None,
        references: Optional[str] = None,
        raw_data: Optional[str] = None,
        status: ResearchStatus = ResearchStatus.COMPLETE,
    ) -> Research:
        await self._topic_repo.get_by_id_or_raise(topic_id)
        return await self._repo.upsert_for_topic(
            topic_id=topic_id,
            summary=summary,
            key_facts=key_facts,
            references=references,
            raw_data=raw_data,
            status=status,
        )

    async def set_status(self, research_id: UUID, status: ResearchStatus) -> Research:
        research = await self._repo.set_status(research_id, status)
        if research is None:
            raise NotFoundError("Research", research_id)
        return research