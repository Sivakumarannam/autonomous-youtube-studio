import json
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.thumbnail_agent.agent import ThumbnailAgent
from app.agents.thumbnail_agent.models import ThumbnailAgentOutput
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script
from app.database.models.thumbnail import Thumbnail, ThumbnailStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.topic_repository import TopicRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class ThumbnailAgentService:
    """
    Orchestrates the Thumbnail Agent with DB persistence.

    For each script it:
      1. Generates the thumbnail concept via LLM
      2. Renders a PNG placeholder via Pillow
      3. Persists a Thumbnail record linked to the script
      4. Logs execution
    """

    AGENT_NAME = "ThumbnailAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._script_repo = ScriptRepository(session)
        self._topic_repo = TopicRepository(session)

    async def run_for_script(
        self,
        script: Script,
        niche: str = "technology",
    ) -> ThumbnailAgentOutput:
        start = time.monotonic()
        agent = ThumbnailAgent(llm_provider=get_llm_provider())

        topic = await self._topic_repo.get_by_id(script.topic_id)
        topic_title = topic.title if topic else script.seo_title or "YouTube Video"

        # Mark thumbnail as generating
        thumbnail = Thumbnail(
            script_id=script.id,
            status=ThumbnailStatus.GENERATING,
            concept="Generating...",
        )
        self._session.add(thumbnail)
        await self._session.flush()

        try:
            output = await agent.run(
                script=script,
                topic_title=topic_title,
                niche=niche,
            )
            # Generate a second variant with an alternate color scheme for A/B comparison.
            # Variant A (primary) keeps the original design; Variant B swaps to a contrasting palette.
            try:
                import copy
                from pathlib import Path
                output_b = copy.deepcopy(output)
                # Flip to a high-contrast alternate scheme
                if output_b.design.background_color.lower() in ("#0d1117", "#1a1a2e", "#0f0f0f"):
                    output_b.design.background_color = "#CC0000"   # bold red
                    output_b.design.accent_color = "#FFD700"        # gold
                    output_b.design.text_color = "#FFFFFF"
                else:
                    output_b.design.background_color = "#0D1117"   # dark
                    output_b.design.accent_color = "#00C6FF"        # cyan
                    output_b.design.text_color = "#FFFFFF"
                # Render variant B to a separate file
                b_path = agent._render_thumbnail(
                    script_id=str(script.id) + "_b",
                    script_type=str(script.script_type),
                    output=output_b,
                )
                logger.info("Thumbnail variant B rendered", path=b_path, script_id=str(script.id))
            except Exception as _b_exc:
                logger.warning("Thumbnail variant B failed (non-fatal)", error=str(_b_exc))
        except Exception as exc:
            await self._session.execute(
                __import__("sqlalchemy", fromlist=["update"]).update(Thumbnail)
                .where(Thumbnail.id == thumbnail.id)
                .values(status=ThumbnailStatus.FAILED)
            )
            await self._log(
                AgentLogLevel.ERROR,
                f"Thumbnail generation failed: {exc}",
                entity_id=str(script.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # Update thumbnail record with results
        thumbnail.concept = output.concept
        thumbnail.file_path = output.file_path
        thumbnail.status = ThumbnailStatus.COMPLETE
        self._session.add(thumbnail)
        await self._session.flush()

        elapsed = time.monotonic() - start
        await self._log(
            AgentLogLevel.INFO,
            f"Thumbnail generated (CTR score={output.ctr_score:.1f})",
            context=json.dumps({
                "script_id": str(script.id),
                "thumbnail_id": str(thumbnail.id),
                "file_path": output.file_path,
                "ctr_score": output.ctr_score,
            }),
            entity_id=str(script.id),
            execution_time=elapsed,
        )
        return output

    async def run_for_approved_scripts(
        self,
        niche: str = "technology",
        limit: int = 5,
    ) -> list[ThumbnailAgentOutput]:
        """Batch-generate thumbnails for approved scripts."""

        scripts = await self._script_repo.get_approved(limit=limit)
        results: list[ThumbnailAgentOutput] = []

        for script in scripts:
            try:
                output = await self.run_for_script(script=script,niche=niche,)
                results.append(output)
            except Exception as exc:
                logger.error(
                    "Thumbnail batch failed",
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