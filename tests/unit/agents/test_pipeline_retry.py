"""Tests for PipelineAgentService — Retry Manager (Surface A).

All asyncio.sleep calls are mocked so no real sleeping occurs.
All agent layer calls are mocked so no LLM / video rendering happens.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.video import Video, VideoStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(
    retry_count: int = 0,
    max_retries: int = 3,
) -> PipelineRun:
    topic_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    run = PipelineRun(
        id=uuid.uuid4(),
        topic_id=topic_id,
        channel_id=channel_id,
        script_type="short",
        status=PipelineStatus.PENDING,
        retry_count=retry_count,
        max_retries=max_retries,
    )
    return run


def _make_upload(video_id: uuid.UUID | None = None) -> Upload:
    return Upload(
        id=uuid.uuid4(),
        video_id=video_id or uuid.uuid4(),
        status=UploadStatus.SCHEDULED,
        publish_status=PublishStatus.DRAFT,
    )


def _make_video() -> Video:
    return Video(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        status=VideoStatus.COMPLETE,
        video_path="/tmp/video.mp4",
        duration=60.0,
        file_size=1024,
    )


# ---------------------------------------------------------------------------
# is_retryable_error classification
# ---------------------------------------------------------------------------

class TestIsRetryableError:
    """Unit-test the classification helper in isolation."""

    def test_timeout_is_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        exc = httpx.TimeoutException("timed out")
        assert is_retryable_error(exc) is True

    def test_network_error_is_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        exc = httpx.ConnectError("connection refused")
        assert is_retryable_error(exc) is True

    def test_429_is_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        resp = MagicMock()
        resp.status_code = 429
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=resp)
        assert is_retryable_error(exc) is True

    def test_503_is_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        resp = MagicMock()
        resp.status_code = 503
        exc = httpx.HTTPStatusError("service unavailable", request=MagicMock(), response=resp)
        assert is_retryable_error(exc) is True

    def test_500_is_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        resp = MagicMock()
        resp.status_code = 500
        exc = httpx.HTTPStatusError("server error", request=MagicMock(), response=resp)
        assert is_retryable_error(exc) is True

    def test_401_is_not_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        resp = MagicMock()
        resp.status_code = 401
        exc = httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=resp)
        assert is_retryable_error(exc) is False

    def test_403_is_not_retryable(self):
        import httpx
        from app.utils.retry import is_retryable_error
        resp = MagicMock()
        resp.status_code = 403
        exc = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=resp)
        assert is_retryable_error(exc) is False

    def test_quality_error_is_not_retryable(self):
        from app.utils.retry import is_retryable_error
        from app.core.exceptions import QualityError
        exc = QualityError(score=50.0, threshold=85.0)
        assert is_retryable_error(exc) is False

    def test_not_found_error_is_not_retryable(self):
        from app.utils.retry import is_retryable_error
        from app.core.exceptions import NotFoundError
        exc = NotFoundError("Script")
        assert is_retryable_error(exc) is False

    def test_generic_exception_is_not_retryable(self):
        from app.utils.retry import is_retryable_error
        assert is_retryable_error(ValueError("bad value")) is False
        assert is_retryable_error(RuntimeError("boom")) is False


# ---------------------------------------------------------------------------
# Surface A — PipelineAgentService retry behaviour
# ---------------------------------------------------------------------------

class TestPipelineRetry:

    def _make_session(self) -> AsyncMock:
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_retryable_error_triggers_retry_then_succeeds(self):
        """A transient error on first attempt should result in one retry that succeeds."""
        import httpx
        from app.agents.pipeline_agent.service import PipelineAgentService

        session = self._make_session()
        run = _make_run()
        script = MagicMock(id=uuid.uuid4(), seo_tags="[]", seo_title="Title",
                           seo_description="Desc")
        video = _make_video()
        upload = _make_upload(video_id=video.id)

        updated_run = MagicMock()
        updated_run.id = run.id
        updated_run.retry_count = 0
        updated_run.max_retries = 3
        updated_run.upload_id = None
        updated_run.current_stage = "script"

        # First call to _execute_stages raises a retryable error;
        # second call succeeds.
        call_count = {"n": 0}

        async def fake_execute(pipeline_repo, pipeline_run, start):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise httpx.TimeoutException("upstream timeout")
            # second call: success — do nothing

        svc = PipelineAgentService(session)

        with (
            patch.object(svc, "_execute_stages", side_effect=fake_execute),
            patch("app.agents.pipeline_agent.service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.update = AsyncMock(return_value=run)

            await svc.run(run)

        assert call_count["n"] == 2
        mock_sleep.assert_awaited_once()
        # Sleep should be base_backoff * 2^0 = 30 s (default)
        sleep_delay = mock_sleep.call_args[0][0]
        assert sleep_delay == 30

    @pytest.mark.asyncio
    async def test_retryable_error_exhausts_all_retries_then_fails(self):
        """When all retries are exhausted the run must be marked FAILED, not retried again."""
        import httpx
        from app.agents.pipeline_agent.service import PipelineAgentService

        session = self._make_session()
        run = _make_run(max_retries=2)
        run.retry_count = 0

        attempt = {"n": 0}

        async def always_fails(pipeline_repo, pipeline_run, start):
            attempt["n"] += 1
            raise httpx.NetworkError("connection reset")

        svc = PipelineAgentService(session)

        with (
            patch.object(svc, "_execute_stages", side_effect=always_fails),
            patch("app.agents.pipeline_agent.service.asyncio.sleep", new_callable=AsyncMock),
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockRepo,
        ):
            repo = MockRepo.return_value

            # Return a mock that reflects the retry_count actually written,
            # so the loop's retries_left check stays accurate.
            async def updating(obj, **kwargs):
                m = MagicMock()
                m.retry_count = kwargs.get("retry_count", getattr(obj, "retry_count", 0))
                m.max_retries = 2
                m.upload_id = None
                m.current_stage = "script"
                m.id = run.id
                return m

            repo.update = AsyncMock(side_effect=updating)

            await svc.run(run)

        # max_retries=2 → attempts: initial + 2 retries = 3 total
        assert attempt["n"] == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(self):
        """A NotFoundError must cause immediate FAILED without any retry."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        from app.core.exceptions import NotFoundError

        session = self._make_session()
        run = _make_run()

        attempt = {"n": 0}

        async def raises_not_found(pipeline_repo, pipeline_run, start):
            attempt["n"] += 1
            raise NotFoundError("Topic")

        svc = PipelineAgentService(session)

        with (
            patch.object(svc, "_execute_stages", side_effect=raises_not_found),
            patch("app.agents.pipeline_agent.service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.update = AsyncMock(return_value=run)

            await svc.run(run)

        assert attempt["n"] == 1
        mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Backoff doubles each attempt: 30 s, 60 s, 120 s."""
        import httpx
        from app.agents.pipeline_agent.service import PipelineAgentService

        session = self._make_session()
        run = _make_run(max_retries=3)

        call_num = {"n": 0}

        async def fails_three_times(pipeline_repo, pipeline_run, start):
            call_num["n"] += 1
            if call_num["n"] <= 3:
                raise httpx.TimeoutException("timeout")
            # 4th call succeeds

        svc = PipelineAgentService(session)

        sleep_calls: list[float] = []

        async def capture_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        counter = {"retry": 0}

        async def updating(obj, **kwargs):
            if "retry_count" in kwargs:
                counter["retry"] = kwargs["retry_count"]
            m = MagicMock()
            m.retry_count = counter["retry"]
            m.max_retries = 3
            m.upload_id = None
            m.current_stage = "script"
            m.id = run.id
            return m

        with (
            patch.object(svc, "_execute_stages", side_effect=fails_three_times),
            patch("app.agents.pipeline_agent.service.asyncio.sleep", side_effect=capture_sleep),
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockRepo,
        ):
            repo = MockRepo.return_value
            repo.update = AsyncMock(side_effect=updating)

            await svc.run(run)

        assert sleep_calls == [30, 60, 120]

    @pytest.mark.asyncio
    async def test_retry_count_starts_at_zero_for_new_run(self):
        """A freshly created PipelineRun must have retry_count=0."""
        run = _make_run()
        assert run.retry_count == 0

    @pytest.mark.asyncio
    async def test_upload_id_idempotency_on_retry(self):
        """If upload_id is already set, _execute_stages must reuse it (no duplicate)."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        from app.database.models.pipeline_run import PipelineStatus

        session = self._make_session()

        existing_upload_id = uuid.uuid4()
        video_id = uuid.uuid4()

        run = _make_run()
        run.upload_id = existing_upload_id
        run.script_id = uuid.uuid4()
        run.video_id = video_id

        script = MagicMock(id=run.script_id, seo_tags="[]", seo_title="T",
                           seo_description="D")
        video = MagicMock(id=video_id, status=VideoStatus.COMPLETE,
                          error_message=None)
        existing_upload = MagicMock(
            id=existing_upload_id,
            status=UploadStatus.SCHEDULED,
            publish_status=PublishStatus.SCHEDULED,
        )

        topic = MagicMock(content_type="tech", title="T", description="D")

        svc = PipelineAgentService(session)

        # ADDED: patch.object(svc, "_run_seo_gate", return_value=True) to the mock context
        with (
            patch.object(svc, "_generate_script", return_value=script),
            patch.object(svc, "_run_quality_gate", return_value=True),
            patch.object(svc, "_run_seo_gate", return_value=True),  # <-- Fixed here
            patch.object(svc, "_render_video", return_value=None),
            patch.object(svc, "_log", return_value=None),
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPipelineRepo,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTopicRepo,
            patch("app.agents.pipeline_agent.service.VideoRepository") as MockVideoRepo,
            patch("app.agents.pipeline_agent.service.UploadRepository") as MockUploadRepo,
        ):
            pipeline_repo = MockPipelineRepo.return_value
            pipeline_repo.update = AsyncMock(return_value=run)

            topic_repo = MockTopicRepo.return_value
            topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_script_id = AsyncMock(return_value=video)

            upload_repo = MockUploadRepo.return_value
            # get_or_raise returns the existing upload (idempotency)
            upload_repo.get_or_raise = AsyncMock(return_value=existing_upload)
            upload_repo.update = AsyncMock(return_value=existing_upload)

            await svc.run(run)

            # Session.add should NOT have been called with a new Upload object
            # because the existing upload_id was reused.
            new_upload_adds = [
                c for c in session.add.call_args_list
                if isinstance(c.args[0], Upload)
            ]
            assert len(new_upload_adds) == 0

            # The existing upload was fetched via get_or_raise
            upload_repo.get_or_raise.assert_awaited_once_with(existing_upload_id)


# ---------------------------------------------------------------------------
# Retry state isolation
# ---------------------------------------------------------------------------

class TestRetryStateIsolation:

    def test_two_runs_have_independent_retry_counts(self):
        """retry_count on one run must not affect another run's retry_count."""
        run_a = _make_run()
        run_b = _make_run()

        run_a.retry_count = 2
        assert run_b.retry_count == 0

    def test_max_retries_independent_per_row(self):
        run_a = _make_run(max_retries=5)
        run_b = _make_run(max_retries=1)
        assert run_a.max_retries == 5
        assert run_b.max_retries == 1