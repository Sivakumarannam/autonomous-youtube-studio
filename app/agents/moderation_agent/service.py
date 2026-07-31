import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.moderation_agent.agent import ModerationAgent
from app.agents.moderation_agent.models import ModerationAgentOutput
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script, ScriptStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class ModerationAgentService:
    """
    Orchestrates the Moderation Agent with DB persistence.

    On approval  → leaves Script status unchanged (caller advances it).
    On rejection → sets Script status to REJECTED and logs reasons.
    """

    AGENT_NAME = "ModerationAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._script_repo = ScriptRepository(session)
        self._topic_repo = TopicRepository(session)

    async def run_for_script(
        self,
        script: Script,
        niche: str = "technology",
        raise_on_failure: bool = False,
    ) -> ModerationAgentOutput:
        start = time.monotonic()
        agent = ModerationAgent(llm_provider=get_llm_provider())

        topic = await self._topic_repo.get_by_id(script.topic_id)
        topic_title = topic.title if topic else ""

        try:
            output = await agent.run(
                script=script,
                topic_title=topic_title,
                niche=niche,
                raise_on_failure=raise_on_failure,
            )
        except Exception as exc:
            await self._log(
                AgentLogLevel.ERROR,
                f"Moderation check failed: {exc}",
                entity_id=str(script.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # On rejection, mark script as rejected
        if not output.approved:
            await self._script_repo.update(script, status=ScriptStatus.REJECTED)

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO if output.approved else AgentLogLevel.WARNING,
            f"Moderation {'APPROVED' if output.approved else 'REJECTED'} "
            f"(risk={output.overall_risk_score:.1f})",
            context=json.dumps({
                "script_id": str(script.id),
                "approved": output.approved,
                "risk_score": output.overall_risk_score,
                "flags": output.flags.flagged_list(),
                "rejection_reasons": output.rejection_reasons,
            }),
            entity_id=str(script.id),
            execution_time=elapsed,
        )
        return output

    async def run_for_approved_scripts(
        self,
        niche: str = "technology",
        limit: int = 10,
    ) -> list[ModerationAgentOutput]:
        """Batch-moderate all APPROVED scripts before they reach the upload queue."""
        scripts = await self._script_repo.get_approved(limit=limit)
        results: list[ModerationAgentOutput] = []

        for script in scripts:
            try:
                output = await self.run_for_script(script, niche=niche)
                results.append(output)
            except Exception as exc:
                logger.error(
                    "Moderation batch failed for script",
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