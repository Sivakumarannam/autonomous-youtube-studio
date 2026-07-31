"""
Research Workflow.

Orchestrates: pending topic selection → ResearchAgent → persist → advance status
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
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


@dataclass
class ResearchWorkflowResult:
    topic_id: str
    topic_title: str
    research_id: str | None = None
    status: str = "complete"
    error: str | None = None
    elapsed_seconds: float = 0.0


class ResearchWorkflow:
    """
    Full research pipeline for a single topic or all pending topics.

    Steps:
      1. Load topic
      2. Mark research as processing
      3. Run ResearchAgent (LLM-powered research)
      4. Persist structured research data
      5. Advance topic status to SCRIPTING
      6. Log execution
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_repo = TopicRepository(session)
        self._research_repo = ResearchRepository(session)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def run_for_topic(
        self,
        topic: Topic,
        niche: str = "technology",
    ) -> ResearchWorkflowResult:
        start = time.monotonic()
        logger.info("ResearchWorkflow.run_for_topic", topic_id=str(topic.id), title=topic.title)

        # Create/update research record as processing
        research = await self._research_repo.upsert_for_topic(
            topic_id=topic.id,
            status=ResearchStatus.PROCESSING,
        )
        await self._topic_repo.update(topic, status=TopicStatus.RESEARCHING)

        agent = ResearchAgent(llm_provider=get_llm_provider())

        try:
            result = await agent.run(topic=topic, niche=niche, language="en")
        except Exception as exc:
            elapsed = time.monotonic() - start
            await self._research_repo.update(research, status=ResearchStatus.FAILED)
            await self._topic_repo.update(topic, status=TopicStatus.FAILED)
            await self._log(
                AgentLogLevel.ERROR,
                f"ResearchWorkflow failed for topic '{topic.title}': {exc}",
                entity_id=str(topic.id),
                execution_time=elapsed,
            )
            return ResearchWorkflowResult(
                topic_id=str(topic.id),
                topic_title=topic.title,
                status="failed",
                error=str(exc),
                elapsed_seconds=round(elapsed, 3),
            )

        # Persist research
        research = await self._research_repo.update(
            research,
            summary=result.get("summary", ""),
            key_facts=json.dumps(result.get("key_facts", [])),
            references=json.dumps(result.get("references", [])),
            raw_data=json.dumps(result),
            status=ResearchStatus.COMPLETE,
        )

        # Advance topic to SCRIPTING
        await self._topic_repo.update(topic, status=TopicStatus.SCRIPTING)

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"Research complete for '{topic.title}'",
            context=json.dumps({"research_id": str(research.id)}),
            entity_id=str(topic.id),
            execution_time=elapsed,
        )

        return ResearchWorkflowResult(
            topic_id=str(topic.id),
            topic_title=topic.title,
            research_id=str(research.id),
            elapsed_seconds=round(elapsed, 3),
        )

    async def run_for_topic_id(
        self,
        topic_id: UUID,
        niche: str = "technology",
    ) -> ResearchWorkflowResult:
        topic = await self._topic_repo.get_by_id_or_raise(topic_id)
        return await self.run_for_topic(topic, niche=niche)

    async def run_pending_topics(
        self,
        niche: str = "technology",
        limit: int = 5,
    ) -> list[ResearchWorkflowResult]:
        """Process all topics in PENDING or RESEARCHING status."""
        topics = await self._topic_repo.get_by_status(TopicStatus.PENDING, limit=limit)
        if not topics:
            topics = await self._topic_repo.get_by_status(TopicStatus.RESEARCHING, limit=limit)

        if not topics:
            logger.info("ResearchWorkflow: no pending topics found")
            return []

        results: list[ResearchWorkflowResult] = []
        for topic in topics:
            result = await self.run_for_topic(topic, niche=niche)
            results.append(result)

        succeeded = sum(1 for r in results if r.status == "complete")
        logger.info(
            "ResearchWorkflow.run_pending complete",
            processed=len(results),
            succeeded=succeeded,
        )
        return results

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name="ResearchWorkflow",
            level=level,
            message=message,
            context=context,
            entity_type="topic",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()