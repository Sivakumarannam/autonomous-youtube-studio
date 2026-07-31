# tests/unit/services/test_thumbnail_service.py

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.thumbnail_service import ThumbnailAPIService
from app.core.exceptions import NotFoundError
from app.database.models.thumbnail import ThumbnailStatus
from tests.conftest import (
    create_test_channel,
    create_test_topic,
    create_test_script,
)


@pytest.fixture
async def service(test_session):
    return ThumbnailAPIService(test_session)


@pytest.fixture
async def script(test_session, create_test_script):
    channel = await create_test_channel(test_session)
    topic = await create_test_topic(test_session, channel.id)

    script = await create_test_script(
        test_session,
        topic.id,
        channel.id,
    )

    return script


@pytest.fixture
def thumbnail(script):
    thumb = MagicMock()
    thumb.id = uuid.uuid4()
    thumb.script_id = script.id
    thumb.concept = "Thumbnail Concept"
    thumb.file_path = "/tmp/thumb.png"
    thumb.status = ThumbnailStatus.COMPLETE
    return thumb


class TestGenerate:

    async def test_generate_success(self, service, script, thumbnail):
        with (
            patch.object(
                service.script_repo,
                "get_by_id_or_raise",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.agent_service,
                "run_for_script",
                AsyncMock(),
            ),
            patch.object(
                service.thumbnail_repo,
                "get_by_script_id",
                AsyncMock(return_value=thumbnail),
            ),
        ):
            result = await service.generate(script.id)

        assert result == thumbnail

    async def test_generate_thumbnail_not_found(self, service, script):
        with (
            patch.object(
                service.script_repo,
                "get_by_id_or_raise",
                AsyncMock(return_value=script),
            ),
            patch.object(
                service.agent_service,
                "run_for_script",
                AsyncMock(),
            ),
            patch.object(
                service.thumbnail_repo,
                "get_by_script_id",
                AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(NotFoundError):
                await service.generate(script.id)

    async def test_generate_script_not_found(self, service):
        with patch.object(
            service.script_repo,
            "get_by_id_or_raise",
            AsyncMock(side_effect=NotFoundError("Script", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.generate(uuid.uuid4())


class TestGet:

    async def test_get_success(self, service, thumbnail):
        with patch.object(
            service.thumbnail_repo,
            "get_or_raise",
            AsyncMock(return_value=thumbnail),
        ):
            result = await service.get(thumbnail.id)

        assert result == thumbnail

    async def test_get_not_found(self, service):
        with patch.object(
            service.thumbnail_repo,
            "get_or_raise",
            AsyncMock(side_effect=NotFoundError("Thumbnail", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.get(uuid.uuid4())


class TestGetByScript:

    async def test_get_by_script_success(self, service, script, thumbnail):
        with patch.object(
            service.thumbnail_repo,
            "get_by_script_id",
            AsyncMock(return_value=thumbnail),
        ):
            result = await service.get_by_script(script.id)

        assert result == thumbnail

    async def test_get_by_script_not_found(self, service):
        with patch.object(
            service.thumbnail_repo,
            "get_by_script_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await service.get_by_script(uuid.uuid4())


class TestUpdate:

    async def test_update_concept(self, service, thumbnail):
        with (
            patch.object(
                service.thumbnail_repo,
                "get_or_raise",
                AsyncMock(return_value=thumbnail),
            ),
            patch.object(
                service.thumbnail_repo,
                "update_thumbnail",
                AsyncMock(return_value=thumbnail),
            ) as mock_update,
        ):
            await service.update(
                thumbnail.id,
                concept="Updated",
            )

        mock_update.assert_awaited_once()

    async def test_update_file_path(self, service, thumbnail):
        with (
            patch.object(
                service.thumbnail_repo,
                "get_or_raise",
                AsyncMock(return_value=thumbnail),
            ),
            patch.object(
                service.thumbnail_repo,
                "update_thumbnail",
                AsyncMock(return_value=thumbnail),
            ) as mock_update,
        ):
            await service.update(
                thumbnail.id,
                file_path="/tmp/new.png",
            )

        mock_update.assert_awaited_once()

    async def test_update_status(self, service, thumbnail):
        with (
            patch.object(
                service.thumbnail_repo,
                "get_or_raise",
                AsyncMock(return_value=thumbnail),
            ),
            patch.object(
                service.thumbnail_repo,
                "update_thumbnail",
                AsyncMock(return_value=thumbnail),
            ) as mock_update,
        ):
            await service.update(
                thumbnail.id,
                status=ThumbnailStatus.COMPLETE,
            )

        mock_update.assert_awaited_once()

    async def test_update_no_changes(self, service, thumbnail):
        with (
            patch.object(
                service.thumbnail_repo,
                "get_or_raise",
                AsyncMock(return_value=thumbnail),
            ),
            patch.object(
                service.thumbnail_repo,
                "update_thumbnail",
                AsyncMock(return_value=thumbnail),
            ) as mock_update,
        ):
            result = await service.update(thumbnail.id)

        mock_update.assert_not_called()
        assert result == thumbnail

    async def test_update_not_found(self, service):
        with patch.object(
            service.thumbnail_repo,
            "get_or_raise",
            AsyncMock(side_effect=NotFoundError("Thumbnail", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.update(uuid.uuid4())


class TestDelete:

    async def test_delete_success(self, service, thumbnail):
        with (
            patch.object(
                service.thumbnail_repo,
                "get_or_raise",
                AsyncMock(return_value=thumbnail),
            ),
            patch.object(
                service.thumbnail_repo,
                "delete_thumbnail",
                AsyncMock(),
            ) as mock_delete,
        ):
            result = await service.delete(thumbnail.id)

        mock_delete.assert_awaited_once_with(thumbnail)
        assert result["message"] == "Thumbnail deleted successfully."

    async def test_delete_not_found(self, service):
        with patch.object(
            service.thumbnail_repo,
            "get_or_raise",
            AsyncMock(side_effect=NotFoundError("Thumbnail", uuid.uuid4())),
        ):
            with pytest.raises(NotFoundError):
                await service.delete(uuid.uuid4())