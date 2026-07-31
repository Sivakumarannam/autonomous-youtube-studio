import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.seo_agent.agent import SEOAgent
from app.agents.seo_agent.models import SEOAgentOutput
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script, ScriptStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class SEOAgentService:
    """
    Orchestrates the SEO Agent with DB persistence.

    Generates SEO metadata for a script and writes the results back
    to the Script record (seo_title, seo_description, seo_tags, hashtags).
    """

    AGENT_NAME = "SEOAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._script_repo = ScriptRepository(session)
        self._topic_repo = TopicRepository(session)

    async def run_for_script(
        self,
        script: Script,
        niche: str = "technology",
        language: str = "en",
    ) -> SEOAgentOutput:
        start = time.monotonic()
        agent = SEOAgent(llm_provider=get_llm_provider())

        # Resolve topic title
        topic = await self._topic_repo.get_by_id(script.topic_id)
        topic_title = topic.title if topic else "YouTube Video"

        try:
            output = await agent.run(
                script=script,
                topic_title=topic_title,
                niche=niche,
                language=language,
            )
        except Exception as exc:
            await self._log(
                AgentLogLevel.ERROR,
                f"SEO generation failed: {exc}",
                entity_id=str(script.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # Hard-enforce tag limits (YouTube ignores >20; we always want >=5)
        output.tags = output.tags[:20]
        if not output.tags:
            output.tags = [output.title.split()[0]] if output.title else ["video"]

        # Persist SEO data back to the Script record
        await self._script_repo.update(
            script,
            seo_title=output.title,
            seo_description=output.description,
            seo_tags=json.dumps(output.tags),
            hashtags=json.dumps(output.hashtags),
        )

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"SEO metadata generated for script (score={output.overall_seo_score:.1f})",
            context=json.dumps({
                "script_id": str(script.id),
                "seo_score": output.overall_seo_score,
                "title": output.title,
            }),
            entity_id=str(script.id),
            execution_time=elapsed,
        )
        return output

    async def run_for_approved_scripts(
        self,
        niche: str = "technology",
        limit: int = 10,
    ) -> list[SEOAgentOutput]:
        """Batch-process all approved scripts that lack SEO metadata."""
        scripts = await self._script_repo.get_approved(limit=limit)
        results: list[SEOAgentOutput] = []

        for script in scripts:
            # Skip if already has SEO data
            if script.seo_title:
                continue
            try:
                output = await self.run_for_script(script, niche=niche)
                results.append(output)
            except Exception as exc:
                logger.error(
                    "SEO batch failed for script",
                    script_id=str(script.id),
                    error=str(exc),
                )
        return results

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
            entity_type="script",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()