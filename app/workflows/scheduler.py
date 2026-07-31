"""
Celery Beat Scheduler.

Defines periodic tasks for autonomous content generation.
All tasks respect the AUTO_* environment flags so individual
stages can be enabled or disabled independently.

NOTE: Celery is an optional dependency — the main app uses APScheduler instead.
      This file is only needed if you want to run a separate Celery Beat worker.
      Install with: pip install celery[redis]
"""
from __future__ import annotations

try:
    from celery import Celery
    from celery.schedules import crontab
    _CELERY_AVAILABLE = True
except ImportError:  # celery not installed — APScheduler handles scheduling
    Celery = None  # type: ignore[assignment,misc]
    crontab = None  # type: ignore[assignment]
    _CELERY_AVAILABLE = False

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

if not _CELERY_AVAILABLE:
    logger.debug(
        "Celery not installed — CeleryBeatScheduler disabled. "
        "The app uses APScheduler by default; install celery[redis] only "
        "if you need distributed task workers."
    )

# ------------------------------------------------------------------ #
# Celery application (only created when celery is installed)          #
# ------------------------------------------------------------------ #

celery_app = None

if _CELERY_AVAILABLE:
    celery_app = Celery(
        "youtube_studio",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )

    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_routes={
            "app.workflows.scheduler.task_discover_topics": {"queue": "topics"},
            "app.workflows.scheduler.task_run_research": {"queue": "research"},
            "app.workflows.scheduler.task_generate_short_scripts": {"queue": "scripts"},
            "app.workflows.scheduler.task_generate_long_scripts": {"queue": "scripts"},
            "app.workflows.scheduler.task_health_check": {"queue": "default"},
        },
    )

    # ------------------------------------------------------------------ #
    # Beat schedule                                                        #
    # ------------------------------------------------------------------ #

    celery_app.conf.beat_schedule = {
        # Discover trending topics every day at 06:00 UTC
        "discover-topics-daily": {
            "task": "app.workflows.scheduler.task_discover_topics",
            "schedule": crontab(hour=6, minute=0),
            "kwargs": {"count": 10},
        },
        # Run research on pending topics every day at 07:00 UTC
        "research-topics-daily": {
            "task": "app.workflows.scheduler.task_run_research",
            "schedule": crontab(hour=7, minute=0),
            "kwargs": {"limit": 10, "niche": "technology"},
        },
        # Generate short scripts every day at 08:00 UTC
        "generate-short-scripts-daily": {
            "task": "app.workflows.scheduler.task_generate_short_scripts",
            "schedule": crontab(hour=8, minute=0),
            "kwargs": {"limit": 5},
        },
        # Generate long scripts every day at 09:00 UTC
        "generate-long-scripts-daily": {
            "task": "app.workflows.scheduler.task_generate_long_scripts",
            "schedule": crontab(hour=9, minute=0),
            "kwargs": {"limit": 3},
        },
        # Health check every hour
        "health-check-hourly": {
            "task": "app.workflows.scheduler.task_health_check",
            "schedule": crontab(minute=0),
        },
    }

    # ------------------------------------------------------------------ #
    # Task definitions                                                     #
    # ------------------------------------------------------------------ #

    @celery_app.task(
        name="app.workflows.scheduler.task_discover_topics",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )
    def task_discover_topics(self, count: int = 10) -> dict:
        """Discover trending topics for all active channels."""
        if not settings.auto_generate:
            logger.info("AUTO_GENERATE disabled — skipping topic discovery")
            return {"skipped": True, "reason": "AUTO_GENERATE=false"}

        import asyncio
        from app.database.connection import async_session_factory
        from app.workflows.topic_workflow import TopicDiscoveryWorkflow

        async def _run() -> dict:
            async with async_session_factory() as session:
                async with session.begin():
                    workflow = TopicDiscoveryWorkflow(session)
                    results = await workflow.run_for_all_active_channels(count=count)
                    return {
                        "channels_processed": len(results),
                        "total_saved": sum(r.topics_saved for r in results),
                        "total_skipped": sum(r.topics_skipped for r in results),
                    }

        try:
            return asyncio.get_event_loop().run_until_complete(_run())
        except Exception as exc:
            logger.error("task_discover_topics failed", error=str(exc))
            raise self.retry(exc=exc)


    @celery_app.task(
        name="app.workflows.scheduler.task_run_research",
        bind=True,
        max_retries=3,
        default_retry_delay=120,
    )
    def task_run_research(self, limit: int = 10, niche: str = "technology") -> dict:
        """Run research agent on pending topics."""
        if not settings.auto_generate:
            logger.info("AUTO_GENERATE disabled — skipping research")
            return {"skipped": True, "reason": "AUTO_GENERATE=false"}

        import asyncio
        from app.database.connection import async_session_factory
        from app.workflows.research_workflow import ResearchWorkflow

        async def _run() -> dict:
            async with async_session_factory() as session:
                async with session.begin():
                    workflow = ResearchWorkflow(session)
                    results = await workflow.run_pending_topics(niche=niche, limit=limit)
                    return {
                        "processed": len(results),
                        "succeeded": sum(1 for r in results if r.status == "complete"),
                        "failed": sum(1 for r in results if r.status == "failed"),
                    }

        try:
            return asyncio.get_event_loop().run_until_complete(_run())
        except Exception as exc:
            logger.error("task_run_research failed", error=str(exc))
            raise self.retry(exc=exc)


    @celery_app.task(
        name="app.workflows.scheduler.task_generate_short_scripts",
        bind=True,
        max_retries=3,
        default_retry_delay=120,
    )
    def task_generate_short_scripts(self, limit: int = 5, niche: str = "technology") -> dict:
        """Generate Shorts scripts for topics in SCRIPTING status."""
        if not settings.auto_generate:
            return {"skipped": True, "reason": "AUTO_GENERATE=false"}

        import asyncio
        from app.database.connection import async_session_factory
        from app.workflows.shorts_workflow import ShortsProductionWorkflow

        async def _run() -> dict:
            async with async_session_factory() as session:
                async with session.begin():
                    workflow = ShortsProductionWorkflow(session)
                    results = await workflow.run_scripting_topics(niche=niche, limit=limit)
                    return {
                        "processed": len(results),
                        "succeeded": sum(1 for r in results if r.status == "complete"),
                        "failed": sum(1 for r in results if r.status == "failed"),
                    }

        try:
            return asyncio.get_event_loop().run_until_complete(_run())
        except Exception as exc:
            logger.error("task_generate_short_scripts failed", error=str(exc))
            raise self.retry(exc=exc)


    @celery_app.task(
        name="app.workflows.scheduler.task_generate_long_scripts",
        bind=True,
        max_retries=3,
        default_retry_delay=120,
    )
    def task_generate_long_scripts(self, limit: int = 3, niche: str = "technology") -> dict:
        """Generate long-form scripts for topics in SCRIPTING status."""
        if not settings.auto_generate:
            return {"skipped": True, "reason": "AUTO_GENERATE=false"}

        import asyncio
        from app.database.connection import async_session_factory
        from app.workflows.long_video_workflow import LongVideoProductionWorkflow

        async def _run() -> dict:
            async with async_session_factory() as session:
                async with session.begin():
                    workflow = LongVideoProductionWorkflow(session)
                    results = await workflow.run_scripting_topics(niche=niche, limit=limit)
                    return {
                        "processed": len(results),
                        "succeeded": sum(1 for r in results if r.status == "complete"),
                        "failed": sum(1 for r in results if r.status == "failed"),
                    }

        try:
            return asyncio.get_event_loop().run_until_complete(_run())
        except Exception as exc:
            logger.error("task_generate_long_scripts failed", error=str(exc))
            raise self.retry(exc=exc)


    @celery_app.task(name="app.workflows.scheduler.task_health_check")
    def task_health_check() -> dict:
        """Periodic health check task."""
        import asyncio
        from app.database.connection import async_session_factory
        from sqlalchemy import text

        async def _check() -> dict:
            try:
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))
                return {"database": "ok"}
            except Exception as exc:
                return {"database": f"error: {exc}"}

        result = asyncio.get_event_loop().run_until_complete(_check())
        logger.info("Health check", **result)
        return result
