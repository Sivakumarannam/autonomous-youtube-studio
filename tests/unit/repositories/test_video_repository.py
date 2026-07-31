import uuid

import pytest

from app.database.models.script import (
    Script,
    ScriptStatus,
    ScriptType,
)
from app.database.models.video import (
    Video,
    VideoStatus,
)
from app.database.repositories.video_repository import VideoRepository


async def _make_script(test_session) -> Script:
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Video repository test script",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    return script


@pytest.mark.asyncio
async def test_create_and_get_by_script_id(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = Video(
        script_id=script.id,
        status=VideoStatus.PENDING,
        resolution="1280x720",
    )

    created = await repository.create(video)

    assert created.id is not None

    fetched = await repository.get_by_script_id(script.id)

    assert fetched is not None
    assert fetched.script_id == script.id
    assert fetched.status == VideoStatus.PENDING


@pytest.mark.asyncio
async def test_get_or_raise_missing_video_raises(test_session):
    from app.core.exceptions import NotFoundError

    repository = VideoRepository(test_session)

    with pytest.raises(NotFoundError):
        await repository.get_or_raise(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_pending_and_generating(test_session):
    repository = VideoRepository(test_session)

    pending_script = await _make_script(test_session)
    generating_script = await _make_script(test_session)

    pending_video = await repository.create(
        Video(
            script_id=pending_script.id,
            status=VideoStatus.PENDING,
            resolution="1280x720",
        )
    )
    generating_video = await repository.create(
        Video(
            script_id=generating_script.id,
            status=VideoStatus.GENERATING,
            resolution="1280x720",
        )
    )

    pending = await repository.get_pending()
    generating = await repository.get_generating()

    assert any(v.id == pending_video.id for v in pending)
    assert any(v.id == generating_video.id for v in generating)


@pytest.mark.asyncio
async def test_get_completed(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = await repository.create(
        Video(
            script_id=script.id,
            status=VideoStatus.COMPLETE,
            resolution="1280x720",
            video_path="storage/videos/test.mp4",
            duration=42.0,
            file_size=2048,
        )
    )

    completed = await repository.get_completed()

    assert any(v.id == video.id for v in completed)
    assert completed[0].status == VideoStatus.COMPLETE


@pytest.mark.asyncio
async def test_mark_generating(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = await repository.create(
        Video(
            script_id=script.id,
            status=VideoStatus.PENDING,
            resolution="1280x720",
        )
    )

    updated = await repository.mark_generating(video)

    assert updated.status == VideoStatus.GENERATING


@pytest.mark.asyncio
async def test_mark_complete(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = await repository.create(
        Video(
            script_id=script.id,
            status=VideoStatus.GENERATING,
            resolution="1280x720",
        )
    )

    updated = await repository.mark_complete(
        video,
        video_path="storage/videos/done.mp4",
        duration=12.5,
        file_size=99999,
    )

    assert updated.status == VideoStatus.COMPLETE
    assert updated.video_path == "storage/videos/done.mp4"
    assert updated.duration == 12.5
    assert updated.file_size == 99999
    assert updated.error_message is None


@pytest.mark.asyncio
async def test_mark_failed(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = await repository.create(
        Video(
            script_id=script.id,
            status=VideoStatus.GENERATING,
            resolution="1280x720",
        )
    )

    updated = await repository.mark_failed(
        video,
        error_message="Rendering dependency unavailable",
    )

    assert updated.status == VideoStatus.FAILED
    assert updated.error_message == "Rendering dependency unavailable"


@pytest.mark.asyncio
async def test_delete_video(test_session):
    repository = VideoRepository(test_session)
    script = await _make_script(test_session)

    video = await repository.create(
        Video(
            script_id=script.id,
            status=VideoStatus.COMPLETE,
            resolution="1280x720",
        )
    )

    await repository.delete_video(video)

    result = await repository.get_by_script_id(script.id)

    assert result is None