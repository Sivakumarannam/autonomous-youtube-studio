import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.long_script_agent.agent import LongScriptAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script
from app.database.models.topic import Topic
from app.database.repositories.research_repository import ResearchRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class LongScriptAgentService:
    AGENT_NAME = "LongScriptAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._topic_repo = TopicRepository(session)
        self._research_repo = ResearchRepository(session)

    async def run_for_topic(self, topic: Topic, niche: str = "technology") -> Script:
        start = time.monotonic()
        agent = LongScriptAgent(llm_provider=get_llm_provider())
        research = await self._research_repo.get_by_topic_id(topic.id)

        # RAG context injection — optional, config-gated, fail-safe
        rag_context: str | None = None
        if settings.rag_research_enabled:
            try:
                from app.rag.rag_research_service import RagResearchService

                rag_svc = RagResearchService()
                await rag_svc.build_for_topic(
                    topic_id=str(topic.id),
                    query=topic.title or "",
                    niche=niche,
                )
                rag_context = await rag_svc.retrieve_context(
                    topic_id=str(topic.id),
                    query=topic.title or "",
                )
            except Exception as exc:
                logger.warning(
                    "RAG context retrieval failed; generating without it",
                    topic_id=str(topic.id),
                    error=str(exc),
                )

        try:
            script = await agent.run(
                topic=topic,
                research=research,
                session=self._session,
                niche=niche,
                rag_context=rag_context,
            )
        except Exception as e:
            await self._log(
                AgentLogLevel.ERROR,
                f"Long script failed: {e}",
                entity_id=str(topic.id),
                execution_time=time.monotonic() - start,
            )
            raise

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"Long script generated for: {topic.title}",
            context=json.dumps(
                {
                    "script_id": str(script.id),
                    "words": script.word_count,
                    "rag_enabled": rag_context is not None,
                }
            ),
            entity_id=str(topic.id),
            execution_time=elapsed,
        )
        return script

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type="topic",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()