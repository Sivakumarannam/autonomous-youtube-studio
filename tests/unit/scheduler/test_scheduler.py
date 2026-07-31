"""Unit tests for the Publish Scheduler (Stage 3).

APScheduler's clock/trigger is NOT used in tests — we call _publish_due_videos()
directly and mock the DB and upload agent. No sleeping required.

Patching notes:
  - scheduler.py imports UploadRepository, VideoRepository, UploadAgentService,
    and _get_session_factory at MODULE level, so patches must target
    'app.scheduler.scheduler.<Name>' to intercept them correctly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.video import Video, VideoStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload(upload_id=None, video_id=None, scheduled_at=None):
    vid_id = video_id or uuid.uuid4()
    return Upload(
        id=upload_id or uuid.uuid4(),
        video_id=vid_id,
        title="AI Trends 2026",
        description="Deep dive.",
        tags='["ai"]',
        privacy_status="public",
        status=UploadStatus.SCHEDULED,
        publish_status=PublishStatus.SCHEDULED,
        scheduled_at=scheduled_at or datetime.now(timezone.utc) - timedelta(minutes=1),
    )


def _make_video(video_id=None, script_id=None):
    return Video(
        id=video_id or uuid.uuid4(),
        script_id=script_id or uuid.uuid4(),
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
# Scheduler tick tests
# ---------------------------------------------------------------------------

class TestSchedulerTick:

    @pytest.mark.asyncio
    async def test_tick_publishes_due_uploads(self):
        """Due uploads are passed to UploadAgentService.run_upload_for_video."""
        from app.scheduler.scheduler import VideoPublishScheduler

        upload_id = uuid.uuid4()
        video_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, video_id=video_id)
        video = _make_video(video_id=video_id)

        published_upload = Upload(
            id=upload_id,
            video_id=video_id,
            status=UploadStatus.PUBLISHED,
            publish_status=PublishStatus.SCHEDULED,
            youtube_video_id="yt_abc123",
            youtube_url="https://youtube.com/watch?v=yt_abc123",
        )

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(return_value=published_upload)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

            agent.run_upload_for_video.assert_awaited_once_with(
                video=video, upload=upload, raise_on_error=True
            )

    @pytest.mark.asyncio
    async def test_tick_skips_when_no_due_uploads(self):
        """When no uploads are due, UploadAgentService is never instantiated."""
        from app.scheduler.scheduler import VideoPublishScheduler

        session = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository"),
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[])

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

            # When due list is empty the function returns early; the agent class
            # is never even instantiated.
            MockUploadAgent.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self):
        """A failure on the first upload must not prevent the second from running."""
        from app.scheduler.scheduler import VideoPublishScheduler

        upload1 = _make_upload()
        upload2 = _make_upload()
        video2 = _make_video()

        published = Upload(
            id=upload2.id,
            video_id=upload2.video_id,
            status=UploadStatus.PUBLISHED,
            publish_status=PublishStatus.SCHEDULED,
            youtube_video_id="yt_ok",
        )

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload1, upload2])
            upload_repo.mark_failed = AsyncMock()
            # get_or_raise returns upload1 first, then upload2
            upload_repo.get_or_raise = AsyncMock(side_effect=[upload1, upload2])

            video_repo = MockVideoRepo.return_value
            # upload1's video → None (triggers failure path); upload2's → valid video
            video_repo.get_by_id = AsyncMock(side_effect=[None, video2])

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(return_value=published)

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            await scheduler._publish_due_videos()

        # upload2 was still processed despite upload1 failing
        agent.run_upload_for_video.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_agent_exception_does_not_crash_tick(self):
        """If run_upload_for_video raises, the tick catches it and continues."""
        from app.scheduler.scheduler import VideoPublishScheduler

        upload = _make_upload()
        video = _make_video(video_id=upload.video_id)

        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        factory = _async_ctx(session)

        with (
            patch("app.scheduler.scheduler._get_session_factory", return_value=factory),
            patch("app.scheduler.scheduler.UploadRepository") as MockUploadRepo,
            patch("app.scheduler.scheduler.VideoRepository") as MockVideoRepo,
            patch("app.scheduler.scheduler.UploadAgentService") as MockUploadAgent,
        ):
            upload_repo = MockUploadRepo.return_value
            upload_repo.get_due_for_publish = AsyncMock(return_value=[upload])
            upload_repo.get_or_raise = AsyncMock(return_value=upload)
            upload_repo.mark_failed = AsyncMock()

            video_repo = MockVideoRepo.return_value
            video_repo.get_by_id = AsyncMock(return_value=video)

            agent = MockUploadAgent.return_value
            agent.run_upload_for_video = AsyncMock(
                side_effect=RuntimeError("YouTube API unavailable")
            )

            scheduler = VideoPublishScheduler.__new__(VideoPublishScheduler)
            # Must NOT raise
            await scheduler._publish_due_videos()

        session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_due_for_publish_excludes_already_published(self):
        """UploadRepository.get_due_for_publish filters out PUBLISHED/UPLOADING rows."""
        from app.database.repositories.upload_repository import UploadRepository
        from sqlalchemy.ext.asyncio import AsyncSession

        session = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = UploadRepository(session)
        due = await repo.get_due_for_publish()

        assert due == []
        session.execute.assert_awaited_once()


class TestSchedulerLifecycle:

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self):
        """Scheduler starts and shuts down cleanly without errors."""
        import asyncio
        from app.scheduler.scheduler import VideoPublishScheduler

        scheduler = VideoPublishScheduler()
        assert not scheduler._scheduler.running

        scheduler.start()
        assert scheduler._scheduler.running

        scheduler.shutdown()
        # Yield event loop so APScheduler can process the shutdown signal.
        await asyncio.sleep(0.05)
        assert not scheduler._scheduler.running

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        """Calling start() twice does not raise."""
        import asyncio
        from app.scheduler.scheduler import VideoPublishScheduler

        scheduler = VideoPublishScheduler()
        scheduler.start()
        scheduler.start()  # second call should be a no-op
        assert scheduler._scheduler.running
        scheduler.shutdown()
        await asyncio.sleep(0.05)