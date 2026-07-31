"""
tests/unit/scheduler/test_automation_scheduler.py

Four verification scenarios for the Daily Automation Scheduler (Phase 6).
All tests are fully mocked — no real Ollama/YouTube calls, no real sleep(),
no SQLite/greenlet native libraries required.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models.channel_automation import AutomationStatus, ChannelAutomation
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.models.topic import Topic, TopicStatus
from app.scheduler.automation_scheduler import DailyAutomationScheduler


# ---------------------------------------------------------------------------
# Shared constants / helpers
# ---------------------------------------------------------------------------

TODAY = date(2026, 7, 6)


def _make_scheduler() -> DailyAutomationScheduler:
    """Instantiate DailyAutomationScheduler without starting APScheduler."""
    s = DailyAutomationScheduler.__new__(DailyAutomationScheduler)
    s._semaphore = asyncio.Semaphore(1)
    return s


def _mock_channel(channel_id=None):
    ch = MagicMock()
    ch.id = channel_id or uuid.uuid4()
    ch.timezone = "UTC"
    ch.is_archived = False
    ch.niche = "technology"
    return ch


def _mock_automation(
    channel_id,
    *,
    active_days: int = 0,
    last_run: date | None = None,
    last_long: date | None = None,
    interval: int = 2,
):
    auto = MagicMock(spec=ChannelAutomation)
    auto.channel_id = channel_id
    auto.cumulative_active_days = active_days
    auto.last_run_date = last_run
    auto.last_long_pipeline_date = last_long
    auto.long_video_interval_days = interval
    auto.automation_status = AutomationStatus.RUNNING
    return auto


def _mock_topic():
    t = MagicMock(spec=Topic)
    t.id = uuid.uuid4()
    return t


async def _run_tick_mocked(
    sched: DailyAutomationScheduler,
    channel,
    automation,
    *,
    short_topic=None,
    long_topic=None,
    has_running: bool = False,
) -> list[dict]:
    """
    Drive _run_channel_tick with all DB/repo interactions mocked.

    Returns a list of dicts — one entry per PipelineRun that would have been
    created: {"channel_id", "topic_id", "script_type"}.
    """
    channel_id = channel.id
    session = AsyncMock()
    session.commit = AsyncMock()

    # Async context-manager mock for `async with session_factory() as session`
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)

    # Mock repo instances (ClassName(session) → mock instance)
    channel_repo = AsyncMock()
    channel_repo.get_by_id = AsyncMock(return_value=channel)

    automation_repo = AsyncMock()
    automation_repo.get_by_channel_id = AsyncMock(return_value=automation)
    automation_repo.update = AsyncMock(return_value=automation)

    pipeline_repo = AsyncMock()
    pipeline_repo.has_running_for_channel = AsyncMock(return_value=has_running)

    # topic_repo.get_eligible_for_automation: first call → short_topic, second → long_topic
    _call_no = [0]

    async def _get_eligible(ch_id):
        _call_no[0] += 1
        return short_topic if _call_no[0] == 1 else long_topic

    topic_repo = AsyncMock()
    topic_repo.get_eligible_for_automation = AsyncMock(side_effect=_get_eligible)

    created: list[dict] = []

    async def _fake_create_run(sess, prepo, ch_id, topic_id, script_type):
        r = MagicMock(spec=PipelineRun)
        r.id = uuid.uuid4()
        r.script_type = script_type
        created.append(
            {"channel_id": ch_id, "topic_id": topic_id, "script_type": script_type}
        )
        return r

    with (
        patch("app.scheduler.automation_scheduler._get_session_factory", return_value=factory),
        patch("app.scheduler.automation_scheduler.ChannelRepository", return_value=channel_repo),
        patch("app.scheduler.automation_scheduler.ChannelAutomationRepository", return_value=automation_repo),
        patch("app.scheduler.automation_scheduler.PipelineRunRepository", return_value=pipeline_repo),
        patch("app.scheduler.automation_scheduler.TopicRepository", return_value=topic_repo),
        patch.object(sched, "_create_pipeline_run", side_effect=_fake_create_run),
        patch("app.scheduler.automation_scheduler._today_in_timezone", return_value=TODAY),
    ):
        await sched._run_channel_tick(channel_id)

    return created


@pytest.mark.asyncio
async def test_process_channel_waits_for_semaphore_before_running():
    """Channels should not be dropped when the semaphore is busy; they should wait and run."""
    sched = _make_scheduler()
    sched._semaphore = asyncio.Semaphore(0)

    called = asyncio.Event()

    async def _fake_run(channel_id):
        called.set()

    with patch.object(sched, "_run_channel_tick", side_effect=_fake_run):
        task = asyncio.create_task(sched._process_channel(uuid.uuid4()))

        await asyncio.sleep(0)
        sched._semaphore.release()

        await asyncio.wait_for(called.wait(), timeout=1)
        await task

    assert called.is_set()


# ---------------------------------------------------------------------------
# Scenario 1 — Day 1–15: only ONE Short PipelineRun per tick, no Long
# ---------------------------------------------------------------------------

class TestDay1To15ShortOnly:
    """cumulative_active_days <= 15 (i.e. new_days <= 15) → Short only."""

    @pytest.mark.asyncio
    async def test_only_short_created_mid_range(self):
        """Day 5 → new_cumulative_days = 6 (well inside Shorts-only window)."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(ch.id, active_days=5)
        short_topic = _mock_topic()

        runs = await _run_tick_mocked(sched, ch, auto, short_topic=short_topic)

        assert len(runs) == 1, f"Expected 1 run, got {len(runs)}: {runs}"
        assert runs[0]["script_type"] == "short"

    @pytest.mark.asyncio
    async def test_only_short_created_at_boundary(self):
        """Day 14 → new_cumulative_days = 15; 15 > 15 is False → still Shorts-only."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(ch.id, active_days=14)
        short_topic = _mock_topic()

        runs = await _run_tick_mocked(sched, ch, auto, short_topic=short_topic)

        assert len(runs) == 1
        assert runs[0]["script_type"] == "short"

    @pytest.mark.asyncio
    async def test_no_long_run_in_shorts_only_window(self):
        """Confirm Long is not created regardless of last_long_pipeline_date."""
        sched = _make_scheduler()
        ch = _mock_channel()
        # last_long is None (would normally trigger Long on day 16+)
        auto = _mock_automation(ch.id, active_days=3, last_long=None)
        short_topic = _mock_topic()
        long_topic = _mock_topic()

        runs = await _run_tick_mocked(
            sched, ch, auto, short_topic=short_topic, long_topic=long_topic
        )

        script_types = [r["script_type"] for r in runs]
        assert "long" not in script_types, (
            f"Long must not be created in Shorts-only window. Got: {script_types}"
        )


# ---------------------------------------------------------------------------
# Scenario 2 — Day 16+: Short always; Long only when due
# ---------------------------------------------------------------------------

class TestDay16Plus:
    """cumulative_active_days >= 15 (i.e. new_days > 15)."""

    @pytest.mark.asyncio
    async def test_short_and_long_when_long_never_run(self):
        """Day 16 (active_days=15 → new=16), last_long=None → Long is due."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(ch.id, active_days=15, last_long=None, interval=2)
        short_topic = _mock_topic()
        long_topic = _mock_topic()

        runs = await _run_tick_mocked(
            sched, ch, auto, short_topic=short_topic, long_topic=long_topic
        )

        assert len(runs) == 2, f"Expected Short + Long, got {len(runs)}: {runs}"
        types = {r["script_type"] for r in runs}
        assert types == {"short", "long"}

    @pytest.mark.asyncio
    async def test_short_and_long_when_interval_elapsed(self):
        """Long was 3 days ago, interval=2 → days_since(3) >= interval(2) → due."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id, active_days=20, last_long=TODAY - timedelta(days=3), interval=2
        )
        short_topic = _mock_topic()
        long_topic = _mock_topic()

        runs = await _run_tick_mocked(
            sched, ch, auto, short_topic=short_topic, long_topic=long_topic
        )

        types = {r["script_type"] for r in runs}
        assert "short" in types, "Short must always be created on day 16+"
        assert "long" in types, "Long must be created when interval has elapsed"

    @pytest.mark.asyncio
    async def test_only_short_when_long_not_yet_due(self):
        """Long was 1 day ago, interval=2 → days_since(1) < interval(2) → NOT due."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id, active_days=20, last_long=TODAY - timedelta(days=1), interval=2
        )
        short_topic = _mock_topic()
        long_topic = _mock_topic()

        runs = await _run_tick_mocked(
            sched, ch, auto, short_topic=short_topic, long_topic=long_topic
        )

        assert len(runs) == 1, (
            f"Expected only Short (Long not due), got {len(runs)}: {runs}"
        )
        assert runs[0]["script_type"] == "short"

    @pytest.mark.asyncio
    async def test_short_always_created_on_day_16_plus(self):
        """Short is created on EVERY tick past day 15, regardless of Long status."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id, active_days=30, last_long=TODAY - timedelta(days=1), interval=2
        )
        short_topic = _mock_topic()

        runs = await _run_tick_mocked(sched, ch, auto, short_topic=short_topic)

        assert len(runs) == 1
        assert runs[0]["script_type"] == "short"


# ---------------------------------------------------------------------------
# Scenario 3 — Missed-days policy: at most ONE run per tick, never backfill
# ---------------------------------------------------------------------------

class TestMissedDaysPolicy:
    @pytest.mark.asyncio
    async def test_at_most_one_short_when_days_missed(self):
        """5-day gap: scheduler creates exactly 1 Short, not 5."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id, active_days=10, last_run=TODAY - timedelta(days=5)
        )
        short_topic = _mock_topic()

        runs = await _run_tick_mocked(sched, ch, auto, short_topic=short_topic)

        assert len(runs) == 1, (
            f"Missed-day policy: expected 1 run (no backfill), got {len(runs)}"
        )
        assert runs[0]["script_type"] == "short"

    @pytest.mark.asyncio
    async def test_missed_days_warning_is_logged(self):
        """A warning mentioning missed days must be emitted when gap > 0."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id, active_days=10, last_run=TODAY - timedelta(days=5)
        )
        short_topic = _mock_topic()

        import app.scheduler.automation_scheduler as _sched_mod

        with patch.object(_sched_mod.logger, "warning") as mock_warn:
            await _run_tick_mocked(sched, ch, auto, short_topic=short_topic)

        assert mock_warn.called, "logger.warning must be called when missed_days > 0"
        first_msg = mock_warn.call_args_list[0][0][0]
        assert "missed" in first_msg.lower(), (
            f"Warning message should mention 'missed'. Got: {first_msg!r}"
        )

    @pytest.mark.asyncio
    async def test_no_backfill_even_on_long_video_day(self):
        """5 days missed on a day when Long is also due: at most Short + Long (2 runs)."""
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(
            ch.id,
            active_days=16,
            last_run=TODAY - timedelta(days=5),
            last_long=TODAY - timedelta(days=5),
            interval=2,
        )
        short_topic = _mock_topic()
        long_topic = _mock_topic()

        runs = await _run_tick_mocked(
            sched, ch, auto, short_topic=short_topic, long_topic=long_topic
        )

        assert len(runs) <= 2, (
            f"Missed-day policy: at most Short + Long per tick, got {len(runs)}: {runs}"
        )


# ---------------------------------------------------------------------------
# Scenario 4 — Quality Gate failure handling (fully mocked)
# ---------------------------------------------------------------------------

class TestQualityGateFailure:
    """
    All DB interactions are mocked — no SQLite/greenlet native libraries needed.
    We verify behaviour at the service-object and scheduler level.
    """

    @staticmethod
    def _make_pipeline_mocks(topic_id, run_id):
        """
        Return (session, script, topic, run, pipeline_repo, topic_repo) mocks
        wired so PipelineAgentService._execute_stages can run its quality-gate
        failure path without any real DB.
        """
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        script = MagicMock()
        script.id = uuid.uuid4()
        script.seo_tags = None

        topic = MagicMock()
        topic.id = topic_id
        topic.content_type = "technology"

        run = MagicMock(spec=PipelineRun)
        run.id = run_id
        run.topic_id = topic_id
        run.script_type = "short"
        run.status = PipelineStatus.PENDING
        run.max_retries = 0
        run.retry_count = 0
        run.current_stage = None
        run.upload_id = None

        pipeline_repo = AsyncMock()
        pipeline_repo.update = AsyncMock(return_value=run)

        topic_repo = AsyncMock()
        topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
        topic_repo.update = AsyncMock(return_value=topic)

        return session, script, topic, run, pipeline_repo, topic_repo

    # ---- (a) topic REJECTED -----------------------------------------------

    @pytest.mark.asyncio
    async def test_topic_marked_rejected_after_quality_failure(self):
        """(a) topic_repo.update is called with status=REJECTED when quality fails."""
        from app.agents.pipeline_agent.service import PipelineAgentService

        topic_id = uuid.uuid4()
        run_id = uuid.uuid4()
        session, script, topic, run, pipeline_repo, topic_repo = (
            self._make_pipeline_mocks(topic_id, run_id)
        )

        svc = PipelineAgentService(session)

        with (
            patch.object(svc, "_generate_script", AsyncMock(return_value=script)),
            patch.object(svc, "_run_quality_gate", AsyncMock(return_value=False)),
            patch.object(svc, "_log", AsyncMock()),
            patch("app.agents.pipeline_agent.service.PipelineRunRepository",
                  return_value=pipeline_repo),
            patch("app.agents.pipeline_agent.service.TopicRepository",
                  return_value=topic_repo),
        ):
            await svc.run(run)

        rejected_calls = [
            c for c in topic_repo.update.call_args_list
            if c.kwargs.get("status") == TopicStatus.REJECTED
        ]
        assert rejected_calls, (
            "topic_repo.update(topic, status=REJECTED) was never called after "
            f"quality gate failure.\nAll update calls: {topic_repo.update.call_args_list}"
        )

    # ---- (b) automation_status unchanged -----------------------------------

    @pytest.mark.asyncio
    async def test_automation_status_unchanged_after_quality_failure(self):
        """(b) PipelineAgentService never touches ChannelAutomationRepository."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        import app.database.repositories.channel_automation_repository as _ca_mod

        topic_id = uuid.uuid4()
        run_id = uuid.uuid4()
        session, script, topic, run, pipeline_repo, topic_repo = (
            self._make_pipeline_mocks(topic_id, run_id)
        )

        svc = PipelineAgentService(session)
        mock_ca_cls = MagicMock()

        with (
            patch.object(svc, "_generate_script", AsyncMock(return_value=script)),
            patch.object(svc, "_run_quality_gate", AsyncMock(return_value=False)),
            patch.object(svc, "_log", AsyncMock()),
            patch("app.agents.pipeline_agent.service.PipelineRunRepository",
                  return_value=pipeline_repo),
            patch("app.agents.pipeline_agent.service.TopicRepository",
                  return_value=topic_repo),
            patch.object(_ca_mod, "ChannelAutomationRepository", mock_ca_cls),
        ):
            await svc.run(run)

        assert not mock_ca_cls.called, (
            "PipelineAgentService must never instantiate ChannelAutomationRepository. "
            "automation_status must only change via explicit user action (Pause/Delete)."
        )

    # ---- (c) next tick picks a different topic ----------------------------

    @pytest.mark.asyncio
    async def test_next_tick_selects_different_topic_after_rejection(self):
        """
        (c) After topic_a is REJECTED, the next scheduler tick's call to
        get_eligible_for_automation returns topic_b (not topic_a).

        Verified by wiring get_eligible_for_automation to simulate the SQL
        exclusion (.notin_([REJECTED, FAILED, PUBLISHED])) and confirming
        the scheduler picks topic_b for the Short run.
        """
        sched = _make_scheduler()
        ch = _mock_channel()
        auto = _mock_automation(ch.id, active_days=3)

        topic_a = _mock_topic()   # simulated as already REJECTED
        topic_b = _mock_topic()   # the alternative eligible topic

        # Simulate get_eligible_for_automation excluding REJECTED topic_a
        async def _eligible_no_rejected(ch_id):
            return topic_b  # topic_a filtered out by .notin_([REJECTED, ...])

        channel_id = ch.id
        session = AsyncMock()
        session.commit = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        channel_repo = AsyncMock()
        channel_repo.get_by_id = AsyncMock(return_value=ch)
        automation_repo = AsyncMock()
        automation_repo.get_by_channel_id = AsyncMock(return_value=auto)
        automation_repo.update = AsyncMock(return_value=auto)
        pipeline_repo = AsyncMock()
        pipeline_repo.has_running_for_channel = AsyncMock(return_value=False)
        topic_repo = AsyncMock()
        topic_repo.get_eligible_for_automation = AsyncMock(
            side_effect=_eligible_no_rejected
        )

        created: list[dict] = []

        async def _fake_create(sess, prepo, ch_id, topic_id, script_type):
            r = MagicMock(spec=PipelineRun)
            r.id = uuid.uuid4()
            created.append({"topic_id": topic_id, "script_type": script_type})
            return r

        with (
            patch("app.scheduler.automation_scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.automation_scheduler.ChannelRepository", return_value=channel_repo),
            patch("app.scheduler.automation_scheduler.ChannelAutomationRepository", return_value=automation_repo),
            patch("app.scheduler.automation_scheduler.PipelineRunRepository", return_value=pipeline_repo),
            patch("app.scheduler.automation_scheduler.TopicRepository", return_value=topic_repo),
            patch.object(sched, "_create_pipeline_run", side_effect=_fake_create),
            patch("app.scheduler.automation_scheduler._today_in_timezone", return_value=TODAY),
        ):
            await sched._run_channel_tick(channel_id)

        assert len(created) == 1, f"Expected 1 run, got {created}"
        assert created[0]["topic_id"] == topic_b.id, (
            f"Expected topic_b ({topic_b.id}). Got {created[0]['topic_id']}. "
            "REJECTED topic_a must be excluded from automation selection."
        )
        assert created[0]["topic_id"] != topic_a.id, (
            "REJECTED topic_a must not be selected for the next tick."
        )
