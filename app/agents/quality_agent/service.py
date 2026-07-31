import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.quality_agent.agent import QualityAgent
from app.agents.quality_agent.models import QualityAgentOutput
from app.core.config import settings
from app.core.exceptions import QualityError
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.quality_report import QualityReport, QualityStatus
from app.database.models.script import Script, ScriptStatus
from app.database.repositories.quality_report_repository import QualityReportRepository
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class QualityAgentService:
    """
    Orchestrates the Quality Agent with DB persistence.

    On pass  → saves QualityReport(passed=True), advances Script to APPROVED.
    On fail  → saves QualityReport(passed=False), sets Script to REJECTED.
    Raises QualityError if caller wants to halt the pipeline on failure.
    """

    AGENT_NAME = "QualityAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._script_repo = ScriptRepository(session)
        self._topic_repo = TopicRepository(session)
        self._quality_repo = QualityReportRepository(session)

    async def run_for_script(
        self,
        script: Script,
        niche: str = "technology",
        raise_on_failure: bool = False,
    ) -> QualityAgentOutput:
        start = time.monotonic()
        # Use .value so we get "short"/"long" instead of "ScriptType.SHORT"
        # (Python 3.11+ str-enum str() behaviour changed)
        agent = QualityAgent(llm_provider=get_llm_provider(), script_type=script.script_type.value)

        topic = await self._topic_repo.get_by_id(script.topic_id)
        topic_title = topic.title if topic else ""

        try:
            output = await agent.run(script=script, topic_title=topic_title, niche=niche)
        except Exception as exc:
            await self._log(
                AgentLogLevel.ERROR,
                f"Quality evaluation failed: {exc}",
                entity_id=str(script.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # Persist QualityReport
        report = QualityReport(
            script_id=script.id,
            grammar_score=output.scores.grammar_score,
            fact_consistency_score=output.scores.fact_consistency_score,
            engagement_score=output.scores.engagement_score,
            retention_score=output.scores.retention_score,
            seo_score=output.scores.seo_score,
            uniqueness_score=output.scores.uniqueness_score,
            readability_score=output.scores.readability_score,
            overall_score=output.overall_score,
            passed=output.passed,
            status=QualityStatus.PASSED if output.passed else QualityStatus.FAILED,
            feedback=output.feedback,
        )
        self._session.add(report)
        await self._session.flush()

        # Update Script quality_score and status
        new_status = ScriptStatus.APPROVED if output.passed else ScriptStatus.REJECTED
        await self._script_repo.update(
            script,
            quality_score=output.overall_score,
            status=new_status,
        )

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO if output.passed else AgentLogLevel.WARNING,
            f"Quality {'PASSED' if output.passed else 'FAILED'} — score={output.overall_score:.1f}",
            context=json.dumps({
                "script_id": str(script.id),
                "overall_score": output.overall_score,
                "passed": output.passed,
            }),
            entity_id=str(script.id),
            execution_time=elapsed,
        )

        if raise_on_failure and not output.passed:
            # Use the correct threshold for the script type so short scripts
            # are evaluated at 55 (quality_min_score_short) not 70 (quality_min_score).
            from app.database.models.script import ScriptType
            threshold = (
                settings.quality_min_score_short
                if script.script_type == ScriptType.SHORT
                else settings.quality_min_score
            )
            raise QualityError(output.overall_score, threshold)

        return output

    async def run_for_draft_scripts(
        self,
        niche: str = "technology",
        limit: int = 10,
    ) -> list[QualityAgentOutput]:
        """Batch-evaluate all DRAFT scripts that have no passing quality report."""
        scripts = await self._script_repo.get_drafts(limit=limit)
        results: list[QualityAgentOutput] = []

        for script in scripts:
            already_passed = await self._quality_repo.script_has_passed(script.id)
            if already_passed:
                continue
            try:
                output = await self.run_for_script(script, niche=niche)
                results.append(output)
            except Exception as exc:
                logger.error(
                    "Quality batch failed for script",
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