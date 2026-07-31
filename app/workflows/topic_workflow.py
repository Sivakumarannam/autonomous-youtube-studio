"""
Top-level Topic Discovery Workflow.

Orchestrates: channel load → topic agent → dedup → persist → notify
This is the entry point called by the scheduler and API.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.topic_agent.agent import TopicAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.channel import Channel
from app.database.models.topic import Topic, TopicSource, TopicStatus
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


@dataclass
class TopicWorkflowResult:
    channel_id: str
    channel_name: str
    topics_generated: int
    topics_saved: int
    topics_skipped: int
    elapsed_seconds: float
    error: str | None = None
    status: str = "complete"
    saved_topic_ids: list[str] = field(default_factory=list)


class TopicDiscoveryWorkflow:
    """
    Full topic discovery pipeline for one or all channels.

    Steps:
      1. Load channel(s)
      2. Run TopicAgent (LLM-powered trend detection)
      3. Deduplicate against existing topics
      4. Persist new topics
      5. Log execution
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channel_repo = ChannelRepository(session)
        self._topic_repo = TopicRepository(session)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def run_for_channel(
        self,
        channel: Channel,
        count: int = 5,
        content_type: str = "long",
    ) -> TopicWorkflowResult:
        start = time.monotonic()
        logger.info("TopicWorkflow.run_for_channel", channel=channel.name, count=count)

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
        except Exception as exc:
            elapsed = time.monotonic() - start
            await self._log(
                AgentLogLevel.ERROR,
                f"TopicWorkflow failed for channel '{channel.name}': {exc}",
                entity_type="channel",
                entity_id=str(channel.id),
                execution_time=elapsed,
            )
            return TopicWorkflowResult(
                channel_id=str(channel.id),
                channel_name=channel.name,
                topics_generated=0,
                topics_saved=0,
                topics_skipped=0,
                elapsed_seconds=elapsed,
                error=str(exc),
                status="failed",
            )

        saved, skipped = await self._persist_topics(
            channel=channel,
            raw_topics=raw_topics,
            source=TopicSource.GOOGLE_TRENDS,
            content_type=content_type,
        )

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"TopicWorkflow saved {len(saved)} topics for '{channel.name}'",
            context=json.dumps({"saved": len(saved), "skipped": skipped}),
            entity_type="channel",
            entity_id=str(channel.id),
            execution_time=elapsed,
        )

        return TopicWorkflowResult(
            channel_id=str(channel.id),
            channel_name=channel.name,
            topics_generated=len(raw_topics),
            topics_saved=len(saved),
            topics_skipped=skipped,
            elapsed_seconds=round(elapsed, 3),
            saved_topic_ids=[str(t.id) for t in saved],
        )

    async def run_for_channel_id(
        self,
        channel_id: UUID,
        count: int = 5,
        content_type: str = "long",
    ) -> TopicWorkflowResult:
        channel = await self._channel_repo.get_by_id_or_raise(channel_id)
        return await self.run_for_channel(channel, count=count, content_type=content_type)

    async def run_for_all_active_channels(
        self,
        count: int = 5,
    ) -> list[TopicWorkflowResult]:
        channels = await self._channel_repo.get_active()
        if not channels:
            logger.warning("TopicWorkflow: no active channels found")
            return []

        results: list[TopicWorkflowResult] = []
        for channel in channels:
            result = await self.run_for_channel(channel, count=count)
            results.append(result)

        total_saved = sum(r.topics_saved for r in results)
        logger.info(
            "TopicWorkflow.run_all complete",
            channels=len(channels),
            total_saved=total_saved,
        )
        return results

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _persist_topics(
        self,
        channel: Channel,
        raw_topics: list[dict],
        source: TopicSource,
        content_type: str,
    ) -> tuple[list[Topic], int]:
        saved: list[Topic] = []
        skipped = 0

        for item in raw_topics:
            title = item.get("topic", "").strip()
            if not title:
                continue
            if await self._topic_repo.title_exists(title, channel.id):
                skipped += 1
                logger.debug("Duplicate topic skipped", title=title)
                continue

            topic = Topic(
                channel_id=channel.id,
                title=title,
                score=float(item.get("score", 0.0)),
                reason=str(item.get("reason", "")),
                source=source,
                keywords=json.dumps(item.get("keywords", [])),
                content_type=item.get("content_type", content_type),
                status=TopicStatus.PENDING,
            )
            created = await self._topic_repo.create(topic)
            saved.append(created)

        return saved, skipped

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name="TopicDiscoveryWorkflow",
            level=level,
            message=message,
            context=context,
            entity_type=entity_type,
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()