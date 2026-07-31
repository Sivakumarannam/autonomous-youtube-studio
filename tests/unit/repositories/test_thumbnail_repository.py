# tests/unit/repositories/test_thumbnail_repository.py

import uuid

import pytest

from app.core.exceptions import NotFoundError
from app.database.models.thumbnail import ThumbnailStatus
from app.database.repositories.thumbnail_repository import ThumbnailRepository
from tests.conftest import (
    create_test_channel,
    create_test_topic,
    create_test_script,
)


@pytest.fixture
async def repository(test_session):
    return ThumbnailRepository(test_session)


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


class TestCreateThumbnail:
    async def test_create_thumbnail(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
            concept="Test Concept",
            file_path="/tmp/test.png",
            status=ThumbnailStatus.COMPLETE,
        )

        assert thumbnail.id is not None
        assert thumbnail.script_id == script.id
        assert thumbnail.concept == "Test Concept"
        assert thumbnail.file_path == "/tmp/test.png"
        assert thumbnail.status == ThumbnailStatus.COMPLETE

    async def test_create_thumbnail_defaults(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        assert thumbnail.id is not None
        assert thumbnail.script_id == script.id


class TestGetByScriptId:
    async def test_get_by_script_id(self, repository, script):
        created = await repository.create_thumbnail(
            script_id=script.id,
            concept="Thumbnail",
        )

        thumbnail = await repository.get_by_script_id(script.id)

        assert thumbnail is not None
        assert thumbnail.id == created.id

    async def test_get_by_script_id_not_found(self, repository):
        thumbnail = await repository.get_by_script_id(uuid.uuid4())

        assert thumbnail is None


class TestGetOrRaise:
    async def test_get_or_raise(self, repository, script):
        created = await repository.create_thumbnail(
            script_id=script.id,
        )

        thumbnail = await repository.get_or_raise(created.id)

        assert thumbnail.id == created.id

    async def test_get_or_raise_not_found(self, repository):
        with pytest.raises(NotFoundError):
            await repository.get_or_raise(uuid.uuid4())


class TestUpdateThumbnail:
    async def test_update_concept(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        updated = await repository.update_thumbnail(
            thumbnail,
            concept="Updated Concept",
        )

        assert updated.concept == "Updated Concept"

    async def test_update_file_path(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        updated = await repository.update_thumbnail(
            thumbnail,
            file_path="/tmp/new.png",
        )

        assert updated.file_path == "/tmp/new.png"

    async def test_update_status(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        updated = await repository.update_thumbnail(
            thumbnail,
            status=ThumbnailStatus.COMPLETE,
        )

        assert updated.status == ThumbnailStatus.COMPLETE

    async def test_update_multiple_fields(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        updated = await repository.update_thumbnail(
            thumbnail,
            concept="New",
            file_path="/tmp/new.png",
            status=ThumbnailStatus.COMPLETE,
        )

        assert updated.concept == "New"
        assert updated.file_path == "/tmp/new.png"
        assert updated.status == ThumbnailStatus.COMPLETE


class TestDeleteThumbnail:
    async def test_delete_thumbnail(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        await repository.delete_thumbnail(thumbnail)

        result = await repository.get_by_script_id(script.id)

        assert result is None

    async def test_delete_then_get_or_raise(self, repository, script):
        thumbnail = await repository.create_thumbnail(
            script_id=script.id,
        )

        await repository.delete_thumbnail(thumbnail)

        with pytest.raises(NotFoundError):
            await repository.get_or_raise(thumbnail.id)