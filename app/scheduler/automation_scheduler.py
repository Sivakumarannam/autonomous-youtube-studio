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
     Under LOW_RAM_MODE: Long is deferred so Short and Long never share a tick.
  g. Topic selection: reuse an eligible existing Topic, else trigger the
     Topic Agent to generate new ones.
  h. Update last_run_date = today after creating this tick's run(s).
  i. Missed-day policy: at most ONE PipelineRun (plus at most one Long run)
     per channel per tick, regardless of how many days were missed. Never
     backfill. A warning is logged when > 1 day was missed.

Also: global single-VM guard — if ANY pipeline is RUNNING, the whole tick
skips starting new work (protects 1 GB Oracle + swap from concurrent encodes).

Failure handling reuses the EXISTING Retry Manager unchanged.
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

    async def _tick(self) -> None:
        session_factory = _get_session_factory()

        await self._reset_stuck_pipeline_runs(session_factory)

        if await self._any_pipeline_running(session_factory):
            logger.info(
                "Automation tick skipped — a pipeline run is already RUNNING "
                "(global single-VM guard)."
            )
            return

        async with session_factory() as session:
            automation_repo = ChannelAutomationRepository(session)
            running = await automation_repo.get_running()

        logger.info("Automation tick: running channels found.", count=len(running))

        for automation in running:
            channel_id = automation.channel_id
            asyncio.create_task(self._process_channel(channel_id))

    async def _any_pipeline_running(self, session_factory) -> bool:
        """True if any PipelineRun is currently RUNNING (all channels)."""
        from sqlalchemy import select as _select, func as _func

        try:
            async with session_factory() as session:
                n = await session.scalar(
                    _select(_func.count())
                    .select_from(PipelineRun)
                    .where(PipelineRun.status == PipelineStatus.RUNNING)
                )
                return bool(n and n > 0)
        except Exception as exc:
            logger.warning(
                "Automation tick: could not check global RUNNING pipelines.",
                error=str(exc),
            )
            return False

    async def _reset_stuck_pipeline_runs(self, session_factory) -> None:
        """Find PipelineRuns stuck in RUNNING for > 2 hours and force them to FAILED."""
        from sqlalchemy import select as _select, and_ as _and_

        STUCK_THRESHOLD_HOURS = 2
        try:
            async with session_factory() as session:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=STUCK_THRESHOLD_HOURS)
                result = await session.execute(
                    _select(PipelineRun).where(
                        _and_(
                            PipelineRun.status == PipelineStatus.RUNNING,
                            PipelineRun.updated_at < cutoff,
                        )
                    )
                )
                stuck = result.scalars().all()
                if not stuck:
                    return

                for run in stuck:
                    run.status = PipelineStatus.FAILED
                    run.failed_stage = run.current_stage or "unknown"
                    run.current_stage = None
                    run.error_message = (
                        f"Watchdog: forcibly terminated after being stuck in "
                        f"status=running for >{STUCK_THRESHOLD_HOURS}h "
                        f"(updated_at={run.updated_at.isoformat() if run.updated_at else 'unknown'})."
                    )

                await session.commit()
                logger.warning(
                    "Automation watchdog: reset stuck RUNNING pipeline run(s).",
                    count=len(stuck),
                    pipeline_run_ids=[str(r.id) for r in stuck],
                    stuck_threshold_hours=STUCK_THRESHOLD_HOURS,
                )
                try:
                    from app.notifications.service import notify as _notify
                    for run in stuck:
                        await _notify(
                            title="⚠️ Stuck Pipeline Run Reset by Watchdog",
                            body=(
                                f"Pipeline run {str(run.id)[:8]}… was stuck in "
                                f"RUNNING for >{STUCK_THRESHOLD_HOURS}h and has "
                                f"been force-failed so the channel can continue."
                            ),
                            level="warning",
                            extra={"🆔 Run ID": str(run.id), "📌 Stage": run.failed_stage or "unknown"},
                        )
                except Exception:
                    pass

        except Exception as exc:
            logger.error(
                "Automation watchdog: failed to reset stuck pipeline runs.",
                error=str(exc),
            )

    async def _process_channel(self, channel_id: UUID) -> None:
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

            if automation.last_run_date == today:
                logger.info(
                    "Automation tick: already ran today, skipping.",
                    channel_id=str(channel_id),
                    today=str(today),
                )
                return

            if await pipeline_repo.has_running_for_channel(channel_id):
                logger.info(
                    "Automation tick: a PipelineRun is already RUNNING for "
                    "this channel, skipping.",
                    channel_id=str(channel_id),
                )
                return

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

            # LOW_RAM (1 GB VM): never start Short + Long in the same tick.
            # Prefer Short today; Long waits for a later eligible day.
            if settings.low_ram_mode and create_long:
                logger.info(
                    "LOW_RAM: deferring Long to a later day (one content type per tick)",
                    channel_id=str(channel_id),
                    cumulative_active_days=new_cumulative_days,
                )
                create_long = False

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


_automation_scheduler: DailyAutomationScheduler | None = None


def get_automation_scheduler() -> DailyAutomationScheduler:
    global _automation_scheduler
    if _automation_scheduler is None:
        _automation_scheduler = DailyAutomationScheduler()
    return _automation_scheduler
