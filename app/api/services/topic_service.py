import json
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.topic import TopicCreate, TopicUpdate, TopicGenerateRequest
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.topic import Topic, TopicStatus, TopicSource
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.topic_repository import TopicRepository

logger = get_logger(__name__)


class TopicService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = TopicRepository(session)
        self._channel_repo = ChannelRepository(session)

    async def create(self, data: TopicCreate) -> Topic:
        await self._channel_repo.get_by_id_or_raise(data.channel_id)

        if await self._repo.title_exists_any_content_type(data.title, data.channel_id):
            raise ValidationError(
                f"Topic '{data.title}' already exists for this channel "
                f"(short and long share the same topic pool)"
            )

        topic = Topic(
            channel_id=data.channel_id,
            title=data.title,
            description=data.description,
            score=data.score,
            reason=data.reason,
            source=data.source,
            keywords=json.dumps(data.keywords) if data.keywords else None,
            content_type=data.content_type,
        )
        created = await self._repo.create(topic)
        logger.info("Topic created", topic_id=str(created.id), title=created.title)
        return created

    async def get_by_id(self, topic_id: UUID) -> Topic:
        return await self._repo.get_by_id_or_raise(topic_id)

    async def get_by_channel(
        self,
        channel_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Topic], int]:
        await self._channel_repo.get_by_id_or_raise(channel_id)
        topics = await self._repo.get_by_channel(channel_id, limit=limit, offset=offset)
        total = await self._repo.count()
        return topics, total

    async def get_all(self, limit: int = 50, offset: int = 0) -> tuple[Sequence[Topic], int]:
        topics = await self._repo.get_all(limit=limit, offset=offset)
        total = await self._repo.count()
        return topics, total

    async def get_pending(self, channel_id: Optional[UUID] = None) -> Sequence[Topic]:
        return await self._repo.get_pending(channel_id=channel_id)

    async def update(self, topic_id: UUID, data: TopicUpdate) -> Topic:
        topic = await self._repo.get_by_id_or_raise(topic_id)
        update_kwargs = data.model_dump(exclude_none=True)
        updated = await self._repo.update(topic, **update_kwargs)
        logger.info("Topic updated", topic_id=str(topic_id))
        return updated

    async def set_status(self, topic_id: UUID, status: TopicStatus) -> Topic:
        topic = await self._repo.set_status(topic_id, status)
        if topic is None:
            raise NotFoundError("Topic", topic_id)
        return topic

    async def delete(self, topic_id: UUID) -> None:
        topic = await self._repo.get_by_id_or_raise(topic_id)
        await self._repo.delete(topic)
        logger.info("Topic deleted", topic_id=str(topic_id))

    async def save_generated_topics(
        self,
        channel_id: UUID,
        generated: list[dict],
        source: TopicSource,
        content_type: str,
    ) -> list[Topic]:
        saved: list[Topic] = []
        for item in generated:
            title = item.get("topic", "").strip()
            if not title:
                continue
            if await self._repo.title_exists_any_content_type(title, channel_id):
                logger.debug("Skipping duplicate topic", title=title)
                continue
            topic = Topic(
                channel_id=channel_id,
                title=title,
                score=float(item.get("score", 0.0)),
                reason=item.get("reason", ""),
                source=source,
                keywords=json.dumps(item.get("keywords", [])),
                content_type=item.get("content_type", content_type),
            )
            created = await self._repo.create(topic)
            saved.append(created)
        logger.info("Topics saved", count=len(saved), channel_id=str(channel_id))
        return saved
