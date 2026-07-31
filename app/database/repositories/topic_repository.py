from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.topic import Topic, TopicStatus, TopicSource
from app.database.repositories.base_repository import BaseRepository


class TopicRepository(BaseRepository[Topic]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Topic, session)

    async def get_by_channel(
        self,
        channel_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Topic]:
        result = await self.session.execute(
            select(Topic)
            .where(Topic.channel_id == channel_id)
            .order_by(desc(Topic.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_status(
        self,
        status: TopicStatus,
        channel_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> Sequence[Topic]:
        conditions = [Topic.status == status]
        if channel_id is not None:
            conditions.append(Topic.channel_id == channel_id)
        result = await self.session.execute(
            select(Topic)
            .where(and_(*conditions))
            .order_by(desc(Topic.score))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_pending(self, channel_id: Optional[UUID] = None, limit: int = 10) -> Sequence[Topic]:
        return await self.get_by_status(TopicStatus.PENDING, channel_id, limit)

    async def get_top_scored(self, channel_id: UUID, limit: int = 10) -> Sequence[Topic]:
        result = await self.session.execute(
            select(Topic)
            .where(Topic.channel_id == channel_id)
            .order_by(desc(Topic.score))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_source(self, source: TopicSource, limit: int = 50) -> Sequence[Topic]:
        result = await self.session.execute(
            select(Topic)
            .where(Topic.source == source)
            .order_by(desc(Topic.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def title_exists(self, title: str, channel_id: UUID) -> bool:
        result = await self.session.execute(
            select(Topic).where(
                and_(Topic.title == title, Topic.channel_id == channel_id)
            )
        )
        return result.scalar_one_or_none() is not None

    async def set_status(self, topic_id: UUID, status: TopicStatus) -> Optional[Topic]:
        topic = await self.get_by_id(topic_id)
        if topic is None:
            return None
        return await self.update(topic, status=status)

    async def get_eligible_for_automation(
        self, channel_id: UUID
    ) -> Optional[Topic]:
        """Return one topic eligible for automatic daily selection.

        Excludes REJECTED (manually or quality-gate rejected), FAILED
        (permanent pipeline failure), and PUBLISHED (already turned into a
        successful video) — so the Daily Automation Scheduler never repeats
        a topic that already succeeded or is known-bad. Highest score first.
        """
        excluded = (TopicStatus.REJECTED, TopicStatus.FAILED, TopicStatus.PUBLISHED)
        result = await self.session.execute(
            select(Topic)
            .where(
                and_(
                    Topic.channel_id == channel_id,
                    Topic.status.notin_(excluded),
                )
            )
            .order_by(desc(Topic.score))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_published_count(self, channel_id: UUID) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count()).select_from(Topic).where(
                and_(
                    Topic.channel_id == channel_id,
                    Topic.status == TopicStatus.PUBLISHED,
                )
            )
        )
        return result.scalar_one()