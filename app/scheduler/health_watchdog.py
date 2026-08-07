"""Periodic DB health check — high-alert if the app cannot reach the database."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.core.logging import get_logger
from app.database.connection import _get_session_factory
from app.notifications.high_alert import high_alert

logger = get_logger(__name__)

_CONSECUTIVE_FAILS_BEFORE_ALERT = 2


class HealthWatchdog:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._fail_streak = 0
        self._scheduler.add_job(
            self._check,
            trigger=IntervalTrigger(minutes=2),
            id="health_watchdog",
            replace_existing=True,
            max_instances=1,
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Health watchdog started (interval=2m)")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Health watchdog stopped")

    async def _check(self) -> None:
        try:
            factory = _get_session_factory()
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            self._fail_streak = 0
        except Exception as exc:
            self._fail_streak += 1
            logger.error(
                "Health watchdog: DB check failed",
                streak=self._fail_streak,
                error=str(exc),
            )
            if self._fail_streak >= _CONSECUTIVE_FAILS_BEFORE_ALERT:
                await high_alert(
                    title="HIGH ALERT — Database unreachable",
                    body=(
                        f"DB health check failed {self._fail_streak} times in a row. "
                        f"Last error: {str(exc)[:300]}"
                    ),
                    key="db_unreachable",
                    extra={"streak": self._fail_streak},
                    cooldown_s=600,
                )


_watchdog: HealthWatchdog | None = None


def get_health_watchdog() -> HealthWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = HealthWatchdog()
    return _watchdog
