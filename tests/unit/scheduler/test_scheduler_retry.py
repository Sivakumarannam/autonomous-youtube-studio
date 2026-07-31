"""Tests for VideoPublishScheduler — Retry Manager (Surface B).

All asyncio.sleep calls are mocked (no real sleeping).
All DB and upload-agent interactions are mocked.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.video import Video, VideoStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload(
    upload_id: uuid.UUID | None = None,
    video_id: uuid.UUID | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
    youtube_video_id: str | None = None,
    status: UploadStatus = UploadStatus.SCHEDULED,
) -> Upload:
    vid_id = video_id or uuid.uuid4()
    return Upload(
        id=upload_id or uuid.uuid4(),
        video_id=vid_id,
        title="AI Trends 2026",
        description="Deep dive.",
        tags='["ai"]',
        privacy_status="public",
        status=status,
        publish_status=PublishStatus.SCHEDULED,
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        retry_count=retry_count,
        max_retries=max_retries,
        youtube_video_id=youtube_video_id,
    )


def _make_video(video_id: uuid.UUID | None = None) -> Video:
    return Video(
        id=video_id or uuid.uuid4(),
        script_id=uuid.uuid4(),
        status=VideoStatus.COMPLETE,
        video_path="/tmp/video.mp4",
        duration=300.0,
        file_size=1024 * 1024,
    )


def _async_ctx(mock_session: AsyncMock):
    """Wrap a mock session so it can be used as `async with factory() as s:`."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=ctx)
    return factory


# ---------------------------------------------------------------------------
# Surface B — Scheduler retry behaviour
# ---------------------------------------------------------------------------

class TestSchedulerRetry:

    @pytest.mark.asyncio
    async def test_retryable_error_triggers_retry_then_succeeds(self):
        """A retryable exception causes one retry, which succeeds."""
        import httpx
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, video_id=video_id)
        video = _make_video(video_id=video_id)

        published_upload = _make_upload(
            upload_id=upload_id, video_id=video_id,
            status=UploadStatus.PUBLISHED,
        )
        published_upload.youtube_video_id = "yt_ok"

        # Sessions: tick-read, attempt-1, retry-meta, attempt-2
        session_read = AsyncMock()
        session_read.commit = AsyncMock()
        session_attempt1 = AsyncMock()
        session_attempt1.commit = AsyncMock()
        session_attempt1.rollback = AsyncMock()
        session_retry_meta = AsyncMock()
        session_retry_meta.commit = AsyncMock()
        session_retry_meta.rollback = AsyncMock()
        session_attempt2 = AsyncMock()
        session_attempt2.commit = AsyncMock()
        session_attempt2.rollback = AsyncMock()

        sessions = [
            session_read,
            session_attempt1,
            session_retry_meta,
            session_attempt2,
        ]
        session_idx = {"i": 0}

        def make_ctx():
            s = sessions[session_idx["i"]] if session_idx["i"] < len(sessions) else AsyncMock()
            session_idx["i"] += 1
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=s)
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        factory = MagicMock(side_effect=make_ctx)

        agent_call_count = {"n": 0}

        async def fake_run_upload(video, upload, raise_on_error=False):
            agent_call_count["n"] += 1
            if agent_call_count["n"] == 1:
                raise httpx.TimeoutException("upstream timeout")
            return published_upload

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
            patch("app.scheduler.scheduler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.update = AsyncMock(return_value=upload)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(side_effect=fake_run_upload)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        assert agent_call_count["n"] == 2
        mock_sleep.assert_awaited_once()
        # First retry delay: base(60) * 2^0 = 60 s
        assert mock_sleep.call_args[0][0] == 60

    @pytest.mark.asyncio
    async def test_retryable_error_exhausts_retries_marks_failed(self):
        """When max_retries is reached the upload is marked permanently FAILED."""
        import httpx
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        video = _make_video(video_id=video_id)

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        agent_calls = {"n": 0}

        async def always_timeout(video, upload, raise_on_error=False):
            agent_calls["n"] += 1
            raise httpx.ConnectError("refused")

        # get_or_raise is called:
        #   attempt 1 re-fetch          → retry_count=0
        #   mini-session after attempt 1 → retry_count=0 (before update to 1)
        #   attempt 2 re-fetch          → retry_count=1 (after commit)
        #   mini-session after attempt 2 → retry_count=1 (before update to 2)
        #   attempt 3 re-fetch          → retry_count=2 (after commit)
        #   fail mini-session           → retry_count=2
        side_effects = [
            _make_upload(upload_id=upload_id, video_id=video_id, max_retries=2, retry_count=rc)
            for rc in [0, 0, 1, 1, 2, 2]
        ]

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
            patch("app.scheduler.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(
                return_value=[_make_upload(upload_id=upload_id, video_id=video_id, max_retries=2)]
            )
            upload_repo.get_or_raise = AsyncMock(side_effect=side_effects)
            upload_repo.update = AsyncMock(side_effect=lambda u, **kw: u)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(side_effect=always_timeout)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        # max_retries=2 → initial + 2 retries = 3 total calls
        assert agent_calls["n"] == 3
        upload_repo.mark_failed.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately_no_retry(self):
        """A 403 Forbidden from YouTube must not be retried."""
        import httpx
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, video_id=video_id)
        video = _make_video(video_id=video_id)

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        resp = MagicMock()
        resp.status_code = 403
        forbidden = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=resp)

        agent_calls = {"n": 0}

        async def raises_forbidden(video, upload, raise_on_error=False):
            agent_calls["n"] += 1
            raise forbidden

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
            patch("app.scheduler.scheduler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.update = AsyncMock(return_value=upload)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(side_effect=raises_forbidden)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        assert agent_calls["n"] == 1
        mock_sleep.assert_not_awaited()
        upload_repo.mark_failed.assert_awaited()

    @pytest.mark.asyncio
    async def test_idempotency_youtube_video_id_already_set(self):
        """If youtube_video_id is set, upload is marked PUBLISHED without a new attempt."""
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        # Simulate YouTube accepted but we lost the response
        upload = _make_upload(
            upload_id=upload_id,
            video_id=video_id,
            youtube_video_id="yt_already_there",
        )

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository"),
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.update = AsyncMock(return_value=upload)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        # Agent must never be called
        MockUploadAgent.assert_not_called()
        # Upload was promoted to PUBLISHED via update()
        update_calls = upload_repo.update.call_args_list
        statuses = [c.kwargs.get("status") for c in update_calls]
        assert UploadStatus.PUBLISHED in statuses

    @pytest.mark.asyncio
    async def test_idempotency_status_already_published(self):
        """If status is already PUBLISHED, the upload is handled via idempotency guard."""
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id, video_id=video_id, status=UploadStatus.PUBLISHED
        )

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository"),
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.update = AsyncMock(return_value=upload)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        MockUploadAgent.assert_not_called()

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Scheduler backoff doubles each attempt: 60 s, 120 s."""
        import httpx
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        video = _make_video(video_id=video_id)

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        call_n = {"n": 0}
        sleep_delays: list[float] = []

        # get_or_raise call sequence:
        #   attempt 1 re-fetch          → retry_count=0  → delay = 60*2^0 = 60 s
        #   mini-session after attempt 1 → retry_count=0 (commits retry_count=1)
        #   attempt 2 re-fetch          → retry_count=1  → delay = 60*2^1 = 120 s
        #   mini-session after attempt 2 → retry_count=1 (commits retry_count=2)
        #   attempt 3 re-fetch          → retry_count=2  (succeeds — no sleep)
        get_or_raise_returns = [
            _make_upload(upload_id=upload_id, video_id=video_id, max_retries=3, retry_count=rc)
            for rc in [0, 0, 1, 1, 2]
        ]
        # Make the 3rd agent call return a published upload
        success_upload = _make_upload(
            upload_id=upload_id, video_id=video_id,
            status=UploadStatus.PUBLISHED, retry_count=2,
        )
        success_upload.youtube_video_id = "yt_final"

        async def fake_run(video, upload, raise_on_error=False):
            call_n["n"] += 1
            if call_n["n"] <= 2:
                raise httpx.TimeoutException("timeout")
            return success_upload

        async def fake_sleep(delay: float) -> None:
            sleep_delays.append(delay)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
            patch("app.scheduler.scheduler.asyncio.sleep", side_effect=fake_sleep),
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(
                return_value=[_make_upload(upload_id=upload_id, video_id=video_id, max_retries=3)]
            )
            upload_repo.get_or_raise = AsyncMock(side_effect=get_or_raise_returns)
            upload_repo.update = AsyncMock(side_effect=lambda u, **kw: u)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(side_effect=fake_run)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        assert sleep_delays == [60, 120]

    @pytest.mark.asyncio
    async def test_retry_count_independent_per_upload(self):
        """retry_count on one Upload must not affect another Upload's retry_count."""
        upload_a = _make_upload()
        upload_b = _make_upload()

        upload_a.retry_count = 2
        assert upload_b.retry_count == 0

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_other_uploads(self):
        """A permanent failure on one upload must not prevent the next from running."""
        import httpx
        from app.scheduler.scheduler import VideoPublishScheduler

        upload1 = _make_upload(max_retries=0)  # no retries allowed
        upload2 = _make_upload()
        video2 = _make_video(video_id=upload2.video_id)

        published2 = _make_upload(
            upload_id=upload2.id, video_id=upload2.video_id,
            status=UploadStatus.PUBLISHED,
        )
        published2.youtube_video_id = "yt_second"

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        call_n = {"n": 0}

        async def side_effect_run(video, upload, raise_on_error=False):
            call_n["n"] += 1
            if call_n["n"] == 1:
                raise httpx.ConnectError("refused")
            return published2

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
            patch("app.scheduler.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload1, upload2])
            upload_repo.get_or_raise = AsyncMock(side_effect=[upload1, upload1, upload2])
            upload_repo.update = AsyncMock(side_effect=lambda u, **kw: u)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(side_effect=[video2, video2])

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(side_effect=side_effect_run)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        # upload2 was still processed
        assert call_n["n"] == 2
