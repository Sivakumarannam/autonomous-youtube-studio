import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.video_service import VideoService
from app.core.exceptions import NotFoundError
from app.database.models.video import VideoStatus


@pytest.fixture
def service(test_session):
    return VideoService(test_session)


@pytest.fixture
def script():
    s = MagicMock()
    s.id = uuid.uuid4()
    s.seo_title = "Docker vs Kubernetes"
    s.title = "Docker vs Kubernetes"
    s.script_type = "long"
    return s


@pytest.fixture
def video(script):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.script_id = script.id
    v.status = VideoStatus.COMPLETE
    v.video_path = "storage/videos/test.mp4"
    v.duration = 30.0
    v.file_size = 12345
    return v


class TestGenerateVideo:
    async def test_generate_video_creates_new(self, service, script, video):
        with (
            patch.object(
                service.script_repository,
                "get_by_id",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.video_repository,
                "get_by_script_id",
                AsyncMock(side_effect=[None, video]),
            ),
            patch.object(
                service.video_agent,
                "run_for_script",
                AsyncMock(),
            ) as mock_run,
        ):
            result = await service.generate_video(script.id)

        mock_run.assert_awaited_once()
        assert result == video

    async def test_generate_video_returns_existing(self, service, script, video):
        with (
            patch.object(
                service.script_repository,
                "get_by_id",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.video_repository,
                "get_by_script_id",
                AsyncMock(return_value=video),
            ),
            patch.object(
                service.video_agent,
                "run_for_script",
                AsyncMock(),
            ) as mock_run,
        ):
            result = await service.generate_video(script.id)

        mock_run.assert_not_awaited()
        assert result == video

    async def test_generate_video_regenerates_after_failure(self, service, script, video):
        failed_video = MagicMock()
        failed_video.status = VideoStatus.FAILED

        with (
            patch.object(
                service.script_repository,
                "get_by_id",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.video_repository,
                "get_by_script_id",
                AsyncMock(side_effect=[failed_video, video]),
            ),
            patch.object(
                service.video_repository,
                "delete_video",
                AsyncMock(),
            ) as mock_delete,
            patch.object(
                service.video_agent,
                "run_for_script",
                AsyncMock(),
            ) as mock_run,
        ):
            result = await service.generate_video(script.id)

        mock_delete.assert_awaited_once_with(failed_video)
        mock_run.assert_awaited_once()
        assert result == video

    async def test_generate_video_script_not_found(self, service):
        with patch.object(
            service.script_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await service.generate_video(uuid.uuid4())

    async def test_generate_video_missing_record_raises_runtime_error(self, service, script):
        with (
            patch.object(
                service.script_repository,
                "get_by_id",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.video_repository,
                "get_by_script_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                service.video_agent,
                "run_for_script",
                AsyncMock(),
            ),
        ):
            with pytest.raises(RuntimeError):
                await service.generate_video(script.id)


class TestRegenerateVideo:
    async def test_regenerate_deletes_existing_then_runs(self, service, script, video):
        with (
            patch.object(
                service.script_repository,
                "get_by_id",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.video_repository,
                "get_by_script_id",
                AsyncMock(side_effect=[video, video]),
            ),
            patch.object(
                service.video_repository,
                "delete_video",
                AsyncMock(),
            ) as mock_delete,
            patch.object(
                service.video_agent,
                "run_for_script",
                AsyncMock(),
            ) as mock_run,
        ):
            result = await service.regenerate_video(script.id)

        mock_delete.assert_awaited_once_with(video)
        mock_run.assert_awaited_once()
        assert result == video

    async def test_regenerate_script_not_found(self, service):
        with patch.object(
            service.script_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await service.regenerate_video(uuid.uuid4())


class TestGetVideo:
    async def test_get_video_success(self, service, video):
        with patch.object(
            service.video_repository,
            "get_or_raise",
            AsyncMock(return_value=video),
        ):
            result = await service.get_video(video.id)

        assert result == video

    async def test_get_video_not_found(self, service):
        with patch.object(
            service.video_repository,
            "get_or_raise",
            AsyncMock(side_effect=NotFoundError("Video", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.get_video(uuid.uuid4())


class TestGetByScript:
    async def test_get_by_script_success(self, service, script, video):
        with patch.object(
            service.video_repository,
            "get_by_script_id",
            AsyncMock(return_value=video),
        ):
            result = await service.get_by_script(script.id)

        assert result == video

    async def test_get_by_script_not_found(self, service):
        with patch.object(
            service.video_repository,
            "get_by_script_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await service.get_by_script(uuid.uuid4())


class TestListCompleted:
    async def test_list_completed(self, service, video):
        with patch.object(
            service.video_repository,
            "get_completed",
            AsyncMock(return_value=[video]),
        ):
            result = await service.list_completed(limit=10)

        assert result == [video]


class TestBatchGenerate:
    async def test_batch_generate_delegates_to_agent(self, service):
        with patch.object(
            service.video_agent,
            "run_for_approved_scripts",
            AsyncMock(return_value=["output-1", "output-2"]),
        ) as mock_batch:
            result = await service.batch_generate(limit=5)

        mock_batch.assert_awaited_once_with(limit=5)
        assert result == ["output-1", "output-2"]


class TestDeleteVideo:
    async def test_delete_success(self, service, video):
        with (
            patch.object(
                service.video_repository,
                "get_or_raise",
                AsyncMock(return_value=video),
            ),
            patch.object(
                service.video_repository,
                "delete_video",
                AsyncMock(),
            ) as mock_delete,
        ):
            await service.delete_video(video.id)

        mock_delete.assert_awaited_once_with(video)

    async def test_delete_not_found(self, service):
        with patch.object(
            service.video_repository,
            "get_or_raise",
            AsyncMock(side_effect=NotFoundError("Video", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.delete_video(uuid.uuid4())