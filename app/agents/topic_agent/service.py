import json
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.topic_agent.agent import TopicAgent
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.channel import Channel
from app.database.models.topic import Topic, TopicSource
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class TopicAgentService:
    """
    Orchestrates the Topic Agent:
    1. Loads active channels
    2. Runs the Topic Agent per channel
    3. Saves discovered topics
    4. Logs execution to agent_logs
    """

    AGENT_NAME = "TopicAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channel_repo = ChannelRepository(session)
        self._topic_repo = TopicRepository(session)

    async def run_for_channel(
        self,
        channel: Channel,
        count: int = 5,
        content_type: str = "long",
    ) -> list[Topic]:
        start = time.monotonic()
        agent = TopicAgent(llm_provider=get_llm_provider())

        sources = [TopicSource.GOOGLE_TRENDS, TopicSource.YOUTUBE_TRENDS]

        try:
            raw_topics = await agent.run(
                channel_id=channel.id,
                count=count,
                sources=sources,
                content_type=content_type,
                niche=channel.niche,
                language=channel.language,
            )
        except Exception as e:
            await self._log(
                level=AgentLogLevel.ERROR,
                message=f"Topic generation failed: {e}",
                entity_type="channel",
                entity_id=str(channel.id),
                execution_time=time.monotonic() - start,
            )
            raise

        saved: list[Topic] = []
        for item in raw_topics:
            title = item.get("topic", "").strip()
            if not title:
                continue
            if await self._topic_repo.title_exists_any_content_type(title, channel.id):
                logger.debug("Skipping duplicate (any content_type)", title=title)
                continue

            topic = Topic(
                channel_id=channel.id,
                title=title,
                score=float(item.get("score", 0.0)),
                reason=item.get("reason", ""),
                source=TopicSource.GOOGLE_TRENDS,
                keywords=json.dumps(item.get("keywords", [])),
                content_type=item.get("content_type", content_type),
            )
            created = await self._topic_repo.create(topic)
            saved.append(created)

        elapsed = time.monotonic() - start

        await self._log(
            level=AgentLogLevel.INFO,
            message=f"Generated {len(saved)} new topics for channel '{channel.name}'",
            context=json.dumps({"saved": len(saved), "channel": channel.name}),
            entity_type="channel",
            entity_id=str(channel.id),
            execution_time=elapsed,
        )

        return saved

    async def run_for_all_active_channels(self, count: int = 5) -> dict[str, int]:
        channels = await self._channel_repo.get_active()
        results: dict[str, int] = {}

        for channel in channels:
            try:
                saved = await self.run_for_channel(channel, count=count)
                results[str(channel.id)] = len(saved)
            except Exception as e:
                logger.error("Failed for channel", channel=channel.name, error=str(e))
                results[str(channel.id)] = 0

        return results

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        log_entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type=entity_type,
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(log_entry)
        await self._session.flush()
