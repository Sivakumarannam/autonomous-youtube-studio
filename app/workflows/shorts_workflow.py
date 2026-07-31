"""
Shorts Production Workflow.

Orchestrates: topic → research lookup → ShortScriptAgent → script persist → status advance
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.short_script_agent.agent import ShortScriptAgent
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.topic import Topic, TopicStatus
from app.database.repositories.research_repository import ResearchRepository
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


@dataclass
class ShortsWorkflowResult:
    topic_id: str
    topic_title: str
    script_id: str | None = None
    word_count: int = 0
    duration_seconds: int = 0
    status: str = "complete"
    error: str | None = None
    elapsed_seconds: float = 0.0


class ShortsProductionWorkflow:
    """
    Full Shorts production pipeline.

    Steps:
      1. Load topic + associated research
      2. Run ShortScriptAgent (40-90 words, 15-30s)
      3. Persist Script record
      4. Advance topic status to PRODUCING
      5. Log execution
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_repo = TopicRepository(session)
        self._research_repo = ResearchRepository(session)
        self._script_repo = ScriptRepository(session)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def run_for_topic(
        self,
        topic: Topic,
        niche: str = "technology",
    ) -> ShortsWorkflowResult:
        start = time.monotonic()
        logger.info("ShortsWorkflow.run_for_topic", topic_id=str(topic.id))

        # Check for existing short script
        existing = await self._script_repo.get_for_topic_and_type(topic.id, ScriptType.SHORT)
        if existing and existing.status != ScriptStatus.REJECTED:
            logger.info("Short script already exists", script_id=str(existing.id))
            return ShortsWorkflowResult(
                topic_id=str(topic.id),
                topic_title=topic.title,
                script_id=str(existing.id),
                word_count=existing.word_count,
                duration_seconds=existing.estimated_duration,
                status="complete",
            )

        research = await self._research_repo.get_by_topic_id(topic.id)
        agent = ShortScriptAgent(llm_provider=get_llm_provider())

        try:
            script = await agent.run(
                topic=topic,
                research=research,
                session=self._session,
                niche=niche,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            await self._log(
                AgentLogLevel.ERROR,
                f"ShortsWorkflow failed for topic '{topic.title}': {exc}",
                entity_id=str(topic.id),
                execution_time=elapsed,
            )
            return ShortsWorkflowResult(
                topic_id=str(topic.id),
                topic_title=topic.title,
                status="failed",
                error=str(exc),
                elapsed_seconds=round(elapsed, 3),
            )

        # Advance topic status
        await self._topic_repo.update(topic, status=TopicStatus.PRODUCING)

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"Short script generated for '{topic.title}' ({script.word_count} words)",
            context=json.dumps({"script_id": str(script.id), "words": script.word_count}),
            entity_id=str(topic.id),
            execution_time=elapsed,
        )

        return ShortsWorkflowResult(
            topic_id=str(topic.id),
            topic_title=topic.title,
            script_id=str(script.id),
            word_count=script.word_count,
            duration_seconds=script.estimated_duration,
            elapsed_seconds=round(elapsed, 3),
        )

    async def run_for_topic_id(
        self,
        topic_id: UUID,
        niche: str = "technology",
    ) -> ShortsWorkflowResult:
        topic = await self._topic_repo.get_by_id_or_raise(topic_id)
        return await self.run_for_topic(topic, niche=niche)

    async def run_scripting_topics(
        self,
        niche: str = "technology",
        limit: int = 5,
        channel_id: UUID | None = None,
    ) -> list[ShortsWorkflowResult]:
        """Process all topics in SCRIPTING status that need a short script."""
        topics = await self._topic_repo.get_by_status(
            TopicStatus.SCRIPTING,
            channel_id=channel_id,
            limit=limit,
        )

        results: list[ShortsWorkflowResult] = []
        for topic in topics:
            if topic.content_type in ("short", "both"):
                result = await self.run_for_topic(topic, niche=niche)
                results.append(result)

        logger.info(
            "ShortsWorkflow.run_scripting complete",
            processed=len(results),
            succeeded=sum(1 for r in results if r.status == "complete"),
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
            agent_name="ShortsProductionWorkflow",
            level=level,
            message=message,
            context=context,
            entity_type="topic",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()