"""Daily Automation Scheduler (Phase 6).

Completely separate background job from the existing Publish Scheduler
(app/scheduler/scheduler.py) — that scheduler decides WHEN (time of day) a
SCHEDULED upload actually fires; this scheduler decides WHICH DAYS a
channel gets new content generated at all.

On each tick (default hourly, AUTOMATION_CHECK_INTERVAL_MINUTES), for every
Channel with ChannelAutomation.automation_status == RUNNING:
  a. Compute "today" in the channel's timezone.
  b. Skip if last_run_date == today (already ran today).
  c. Skip if this channel already has a PipelineRun with status RUNNING
     (overlap protection — mirrors the existing max_instances=1 philosophy).
  d. Acquire the AUTOMATION_MAX_CONCURRENT_CHANNELS semaphore before
     proceeding; skip (retry next tick) if it can't acquire immediately.
  e. Increment cumulative_active_days by 1 for this processing day.
  f. Determine content plan (Shorts-only through day 15; Short + conditional
     Long from day 16 on, gated by long_video_interval_days).
  g. Topic selection: reuse an eligible existing Topic, else trigger the
     Topic Agent to generate new ones.
  h. Update last_run_date = today after creating this tick's run(s).
  i. Missed-day policy: at most ONE PipelineRun (plus at most one Long run)
     per channel per tick, regardless of how many days were missed. Never
     backfill. A warning is logged when > 1 day was missed.

Failure handling reuses the EXISTING Retry Manager unchanged:
  - Retryable technical failures (network, Ollama unavailable, timeouts) are
    handled by PipelineAgentService's own retry loop — this scheduler only
    triggers pipeline creation, it does not re-implement retry/backoff.
  - Permanent failures (quality gate rejection) mark that PipelineRun FAILED
    and the Topic REJECTED (app/agents/pipeline_agent/service.py); this
    scheduler's automation_status is never touched by a run's outcome. Only
    explicit user action (Pause/Delete) changes automation_status.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import BackgroundTasks

from app.api.services.pipeline_service import PipelineService
from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import _get_session_factory
from app.database.models.channel_automation import ChannelAutomation
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.repositories.channel_automation_repository import (
    ChannelAutomationRepository,
)
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.topic_repository import TopicRepository
from app.agents.topic_agent.service import TopicAgentService

logger = get_logger(__name__)


def _today_in_timezone(tz_name: str) -> date:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


class DailyAutomationScheduler:
    """Wraps its own AsyncIOScheduler instance — independent of VideoPublishScheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(
                minutes=settings.automation_check_interval_minutes
            ),
            id="daily_automation_tick",
            replace_existing=True,
            max_instances=1,  # prevent overlapping ticks
        )
        self._semaphore = asyncio.Semaphore(
            settings.automation_max_concurrent_channels
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info(
                "Daily automation scheduler started.",
                interval_minutes=settings.automation_check_interval_minutes,
                max_concurrent_channels=settings.automation_max_concurrent_channels,
            )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Daily automation scheduler stopped.")

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        session_factory = _get_session_factory()

        async with session_factory() as session:
            automation_repo = ChannelAutomationRepository(session)
            running = await automation_repo.get_running()

        logger.info("Automation tick: running channels found.", count=len(running))

        for automation in running:
            channel_id = automation.channel_id
            asyncio.create_task(self._process_channel(channel_id))

    async def _process_channel(self, channel_id: UUID) -> None:
        """Process a single channel's daily tick under the concurrency semaphore.

        The scheduler must not silently skip channels when the concurrency
        limit is reached. Instead, it waits for an available slot and then
        executes the channel tick so eligible channels are not dropped.
        """
        logger.info(
            "Automation tick: selected channel for processing.",
            channel_id=str(channel_id),
        )

        async with self._semaphore:
            logger.info(
                "Automation tick: acquired processing slot.",
                channel_id=str(channel_id),
            )
            try:
                await self._run_channel_tick(channel_id)
            except Exception as exc:
                logger.error(
                    "Automation tick: unhandled error processing channel.",
                    channel_id=str(channel_id),
                    error=str(exc),
                )

    async def _run_channel_tick(self, channel_id: UUID) -> None:
        session_factory = _get_session_factory()

        async with session_factory() as session:
            channel_repo = ChannelRepository(session)
            automation_repo = ChannelAutomationRepository(session)
            pipeline_repo = PipelineRunRepository(session)
            topic_repo = TopicRepository(session)

            channel = await channel_repo.get_by_id(channel_id)
            if channel is None or channel.is_archived:
                logger.warning(
                    "Automation tick: channel missing or archived, skipping.",
                    channel_id=str(channel_id),
                )
                return

            automation = await automation_repo.get_by_channel_id(channel_id)
            if automation is None:
                logger.info(
                    "Automation tick: no automation row found for channel, skipping.",
                    channel_id=str(channel_id),
                )
                return

            today = _today_in_timezone(channel.timezone)

            # (b) already ran today
            if automation.last_run_date == today:
                logger.info(
                    "Automation tick: already ran today, skipping.",
                    channel_id=str(channel_id),
                    today=str(today),
                )
                return

            # (c) overlap protection
            if await pipeline_repo.has_running_for_channel(channel_id):
                logger.info(
                    "Automation tick: a PipelineRun is already RUNNING for "
                    "this channel, skipping.",
                    channel_id=str(channel_id),
                )
                return

            # (i) missed-day policy — log a warning, never backfill.
            if automation.last_run_date is not None:
                missed_days = (today - automation.last_run_date).days - 1
                if missed_days > 0:
                    logger.warning(
                        "Automation tick: missed days detected — "
                        "creating at most one run, no backfill.",
                        channel_id=str(channel_id),
                        missed_days=missed_days,
                        last_run_date=str(automation.last_run_date),
                    )

            # (e) increment cumulative_active_days for this processing day
            new_cumulative_days = automation.cumulative_active_days + 1

            # (f) content plan
            create_long = False
            if new_cumulative_days > settings.automation_shorts_only_days:
                if automation.last_long_pipeline_date is None:
                    create_long = True
                else:
                    days_since_long = (
                        today - automation.last_long_pipeline_date
                    ).days
                    create_long = days_since_long >= automation.long_video_interval_days

            created_run_ids: list[UUID] = []

            short_topic = await self._select_topic(
                session, channel, topic_repo, content_type="short"
            )
            if short_topic is not None:
                run = await self._create_pipeline_run(
                    session, pipeline_repo, channel_id, short_topic.id, "short"
                )
                created_run_ids.append(run.id)
            else:
                logger.warning(
                    "Automation tick: no eligible/generatable Short topic, "
                    "skipping Short creation this tick.",
                    channel_id=str(channel_id),
                )

            if create_long:
                long_topic = await self._select_topic(
                    session, channel, topic_repo, content_type="long"
                )
                if long_topic is not None:
                    run = await self._create_pipeline_run(
                        session, pipeline_repo, channel_id, long_topic.id, "long"
                    )
                    created_run_ids.append(run.id)
                    automation = await automation_repo.update(
                        automation, last_long_pipeline_date=today
                    )
                else:
                    logger.warning(
                        "Automation tick: no eligible/generatable Long "
                        "topic, skipping Long creation this tick.",
                        channel_id=str(channel_id),
                    )

            # (h) update last_run_date + cumulative_active_days
            automation = await automation_repo.update(
                automation,
                last_run_date=today,
                cumulative_active_days=new_cumulative_days,
            )
            await session.commit()

            if created_run_ids:
                logger.info(
                    "Automation tick: pipeline start triggered.",
                    channel_id=str(channel_id),
                    cumulative_active_days=new_cumulative_days,
                    runs_created=len(created_run_ids),
                    created_long=create_long,
                    pipeline_run_ids=[str(run_id) for run_id in created_run_ids],
                )
            else:
                logger.warning(
                    "Automation tick: no pipeline runs created for eligible channel.",
                    channel_id=str(channel_id),
                    cumulative_active_days=new_cumulative_days,
                    created_long=create_long,
                )

    async def _select_topic(
        self,
        session,
        channel,
        topic_repo: TopicRepository,
        content_type: str,
    ):
        topic = await topic_repo.get_eligible_for_automation(channel.id)
        if topic is not None:
            return topic

        # No eligible topic found — trigger the existing Topic Agent to
        # generate new ones, then select from the freshly generated batch.
        try:
            topic_agent_service = TopicAgentService(session)
            generated = await topic_agent_service.run_for_channel(
                channel, count=5, content_type=content_type
            )
        except Exception as exc:
            logger.error(
                "Automation tick: Topic Agent failed to generate topics.",
                channel_id=str(channel.id),
                error=str(exc),
            )
            return None

        if not generated:
            return None
        return await topic_repo.get_eligible_for_automation(channel.id)

    async def _create_pipeline_run(
        self,
        session,
        pipeline_repo: PipelineRunRepository,
        channel_id: UUID,
        topic_id: UUID,
        script_type: str,
    ) -> PipelineRun:
        pipeline_service = PipelineService(session)
        background_tasks = BackgroundTasks()
        run = await pipeline_service.start(
            topic_id=topic_id,
            channel_id=channel_id,
            script_type=script_type,
            background_tasks=background_tasks,
        )

        run_id = run.id
        asyncio.create_task(_run_pipeline_in_background(run_id))

        logger.info(
            "Automation: PipelineService.start triggered.",
            pipeline_run_id=str(run_id),
            channel_id=str(channel_id),
            topic_id=str(topic_id),
            script_type=script_type,
        )
        return run


async def _run_pipeline_in_background(pipeline_run_id: UUID) -> None:
    """Run a PipelineRun in its own session, independent of the request/tick session."""
    from app.agents.pipeline_agent.service import PipelineAgentService

    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            pipeline_repo = PipelineRunRepository(session)
            run = await pipeline_repo.get_or_raise(pipeline_run_id)
            svc = PipelineAgentService(session)
            await svc.run(run)
        except Exception as exc:
            # Same failure mode as the manual-trigger path (see
            # app/api/services/pipeline_service.py): if the DB connection
            # itself died mid-render, PipelineAgentService.run()'s own error
            # handling can ALSO fail, leaving the run stuck at
            # status=running forever — which permanently blocks all future
            # automation for the channel with no timeout to recover. Use a
            # fresh session (the old one may be broken) to force a terminal
            # FAILED state no matter what went wrong upstream.
            logger.error(
                "Automation: pipeline background task raised outside service.run().",
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
                    "Automation: failed to mark pipeline run as FAILED after "
                    "crash — it may remain stuck at status=running.",
                    pipeline_run_id=str(pipeline_run_id),
                    error=str(recovery_exc),
                )


# Module-level singleton used by the FastAPI lifespan.
_automation_scheduler: DailyAutomationScheduler | None = None


def get_automation_scheduler() -> DailyAutomationScheduler:
    global _automation_scheduler
    if _automation_scheduler is None:
        _automation_scheduler = DailyAutomationScheduler()
    return _automation_scheduler
