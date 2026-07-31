import json
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.research_agent.agent import ResearchAgent
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.research import Research, ResearchStatus
from app.database.models.topic import Topic, TopicStatus
from app.database.repositories.research_repository import ResearchRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class ResearchAgentService:
    """
    Orchestrates the Research Agent with DB persistence.
    """

    AGENT_NAME = "ResearchAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_repo = TopicRepository(session)
        self._research_repo = ResearchRepository(session)

    async def run_for_topic(self, topic: Topic, niche: str = "technology") -> Research:
        start = time.monotonic()
        agent = ResearchAgent(llm_provider=get_llm_provider())

        # Mark topic as researching
        await self._topic_repo.update(topic, status=TopicStatus.RESEARCHING)

        # Mark research as processing
        research = await self._research_repo.upsert_for_topic(
            topic_id=topic.id, status=ResearchStatus.PROCESSING
        )

        try:
            result = await agent.run(
                topic=topic,
                niche=niche,
                language="en",
            )
        except Exception as e:
            await self._research_repo.update(research, status=ResearchStatus.FAILED)
            await self._topic_repo.update(topic, status=TopicStatus.FAILED)
            await self._log(
                AgentLogLevel.ERROR,
                f"Research failed: {e}",
                entity_type="topic",
                entity_id=str(topic.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # Save results
        research = await self._research_repo.update(
            research,
            summary=result["summary"],
            key_facts=json.dumps(result["key_facts"]),
            references=json.dumps(result["references"]),
            raw_data=json.dumps(result),
            status=ResearchStatus.COMPLETE,
        )

        # Advance topic status
        await self._topic_repo.update(topic, status=TopicStatus.SCRIPTING)

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"Research completed for topic: {topic.title}",
            context=json.dumps({"topic_id": str(topic.id)}),
            entity_type="topic",
            entity_id=str(topic.id),
            execution_time=elapsed,
        )

        return research

    async def run_pending_topics(self, niche: str = "technology", limit: int = 5) -> list[Research]:
        topics = await self._topic_repo.get_by_status(TopicStatus.RESEARCHING, limit=limit)
        if not topics:
            topics = await self._topic_repo.get_pending(limit=limit)

        results: list[Research] = []
        for topic in topics:
            try:
                research = await self.run_for_topic(topic, niche=niche)
                results.append(research)
            except Exception as e:
                logger.error("Research failed for topic", topic_id=str(topic.id), error=str(e))
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
        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type=entity_type,
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()