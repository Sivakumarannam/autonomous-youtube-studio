"""Pipeline API Service.

Thin layer between the route and PipelineAgentService.  Handles:
  - Input validation (topic/channel existence, channel_id consistency)
  - PipelineRun creation
  - Background task dispatch
  - Status / list queries
"""
from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.topic_repository import TopicRepository
from app.monitoring.metrics import PIPELINE_RUNS_TOTAL
from app.websocket.manager import broadcast_safe

logger = get_logger(__name__)


class PipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._pipeline_repo = PipelineRunRepository(session)
        self._topic_repo = TopicRepository(session)
        self._channel_repo = ChannelRepository(session)

    # ------------------------------------------------------------------
    # Start a pipeline run
    # ------------------------------------------------------------------

    async def start(
        self,
        topic_id: UUID,
        channel_id: UUID,
        script_type: str,
        background_tasks: BackgroundTasks,
    ) -> PipelineRun:
        """Create a PipelineRun, enqueue the background worker, return immediately."""
        # Validate topic and channel exist.
        topic = await self._topic_repo.get_by_id(topic_id)
        if topic is None:
            raise NotFoundError("Topic", topic_id)

        channel = await self._channel_repo.get_by_id(channel_id)
        if channel is None:
            raise NotFoundError("Channel", channel_id)

        # channel_id must match the topic's channel.
        if topic.channel_id != channel_id:
            raise ValidationError(
                f"channel_id {channel_id} does not match topic.channel_id "
                f"{topic.channel_id}."
            )

        from app.core.config import settings as app_settings
        run = PipelineRun(
            topic_id=topic_id,
            channel_id=channel_id,
            script_type=script_type,
            status=PipelineStatus.PENDING,
            max_retries=app_settings.retry_max_retries,
        )
        self._session.add(run)
        
        # Explicitly COMMIT here instead of just flushing. 
        # This guarantees the row exists in the DB before the background task 
        # spins up in a separate session and tries to fetch it.
        await self._session.commit()
        await self._session.refresh(run)

        # Capture the ID now; the background task will re-fetch the run from
        # its own session after the request session has committed.
        run_id = run.id
        background_tasks.add_task(_run_pipeline_background, run_id)

        logger.info(
            "Pipeline run queued.",
            pipeline_run_id=str(run_id),
            topic_id=str(topic_id),
            script_type=script_type,
        )
        PIPELINE_RUNS_TOTAL.labels(status=run.status.value).inc()
        await broadcast_safe(
            {
                "type": "pipeline_run",
                "event": "created",
                "id": str(run.id),
                "status": run.status.value,
                "current_stage": run.current_stage,
            }
        )
        return run

    # ------------------------------------------------------------------
    # Delete (dashboard-only — never touches YouTube)
    # ------------------------------------------------------------------

    async def delete_run(self, run_id: UUID) -> None:
        """Remove a PipelineRun row from the dashboard only.

        Deliberately does NOT touch YouTube and does NOT delete the
        Script/Video/Upload rows it may reference — if a video from this
        run was actually published, it stays exactly as-is on YouTube
        and in the Uploads queue. This only clears the pipeline-run
        tracking row itself, e.g. to tidy up a failed/duplicate entry.
        """
        run = await self._pipeline_repo.get_or_raise(run_id)
        await self._pipeline_repo.delete(run)
        logger.info("Pipeline run deleted (dashboard only).", pipeline_run_id=str(run_id))

    # ------------------------------------------------------------------
    # Retry / self-heal a failed or stuck run
    # ------------------------------------------------------------------

    async def retry_run(
        self, run_id: UUID, background_tasks: BackgroundTasks
    ) -> PipelineRun:
        """Self-heal a FAILED (or stuck RUNNING) PipelineRun.

        This does not attempt to resume mid-stage — the pipeline doesn't
        support that. Instead it marks the old row FAILED (if it was
        stuck RUNNING) so it stops showing as active, and starts a brand
        new PipelineRun for the same topic/channel/script_type, reusing
        the exact same start() path as a normal "Run Pipeline" click.
        """
        old_run = await self._pipeline_repo.get_or_raise(run_id)

        if old_run.status == PipelineStatus.RUNNING:
            await self._pipeline_repo.update(
                old_run,
                status=PipelineStatus.FAILED,
                failed_stage=old_run.current_stage or "unknown",
                error_message="Manually reset from the dashboard (stuck run).",
            )
            logger.info(
                "Stuck pipeline run marked FAILED before retry.",
                pipeline_run_id=str(run_id),
            )

        new_run = await self.start(
            topic_id=old_run.topic_id,
            channel_id=old_run.channel_id,
            script_type=old_run.script_type,
            background_tasks=background_tasks,
        )
        logger.info(
            "Self-heal: new pipeline run queued to replace failed/stuck run.",
            old_pipeline_run_id=str(run_id),
            new_pipeline_run_id=str(new_run.id),
        )
        return new_run

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, run_id: UUID) -> PipelineRun:
        return await self._pipeline_repo.get_or_raise(run_id)

    async def list_runs(
        self,
        status: PipelineStatus | None = None,
        topic_id: UUID | None = None,
        limit: int = 20,
    ) -> list[PipelineRun]:
        if topic_id is not None:
            return list(
                await self._pipeline_repo.get_by_topic_id(topic_id, limit=limit)
            )
        if status is not None:
            return list(
                await self._pipeline_repo.get_by_status(status, limit=limit)
            )
        return list(await self._pipeline_repo.get_latest(limit=limit))


# ---------------------------------------------------------------------------
# Background task — runs in its own DB session after the request completes
# ---------------------------------------------------------------------------

async def _run_pipeline_background(pipeline_run_id: UUID) -> None:
    """Background task: own session, commits per stage for observable progress."""
    from app.database.connection import _get_session_factory
    from app.agents.pipeline_agent.service import PipelineAgentService
    from app.database.repositories.pipeline_run_repository import PipelineRunRepository

    session_factory = _get_session_factory()

    async with session_factory() as session:
        try:
            pipeline_repo = PipelineRunRepository(session)
            run = await pipeline_repo.get_or_raise(pipeline_run_id)
            svc = PipelineAgentService(session)
            await svc.run(run)
        except Exception as exc:
            # PipelineAgentService.run() already handles and logs unexpected
            # errors internally — but if the failure was caused by the DB
            # connection itself dying mid-run (e.g. a long render outlasting
            # a stale/suspended DB connection), that internal handling can
            # ALSO fail, leaving the run stuck at status=running forever
            # with nothing to show for it. That silently blocks all future
            # automation for the channel (see has_running_for_channel()),
            # with no timeout to recover. So: log it, then use a brand new
            # session (the old one may be broken) to force the run to a
            # terminal FAILED state no matter what went wrong upstream.
            logger.error(
                "Pipeline background task raised outside service.run().",
                pipeline_run_id=str(pipeline_run_id),
                error=str(exc),
            )
            try:
                async with session_factory() as recovery_session:
                    recovery_repo = PipelineRunRepository(recovery_session)
                    run = await recovery_repo.get_or_raise(pipeline_run_id)
                    if run.status == PipelineStatus.RUNNING:
                        await recovery_repo.update(
                            run,
                            status=PipelineStatus.FAILED,
                            failed_stage=run.current_stage or "unknown",
                            error_message=f"Background task crashed: {exc}"[:2000],
                            current_stage=None,
                        )
                        await recovery_session.commit()
            except Exception as recovery_exc:
                logger.error(
                    "Failed to mark pipeline run as FAILED after crash — "
                    "it may remain stuck at status=running.",
                    pipeline_run_id=str(pipeline_run_id),
                    error=str(recovery_exc),
                )
