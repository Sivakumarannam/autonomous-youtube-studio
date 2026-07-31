import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.upload import Upload, UploadStatus
from app.database.models.video import Video, VideoStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_script(session) -> Script:
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Upload API test script",
        status=ScriptStatus.APPROVED,
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


async def _make_video(
    session,
    script_id: uuid.UUID,
    status: VideoStatus = VideoStatus.COMPLETE,
) -> Video:
    video = Video(
        id=uuid.uuid4(),
        script_id=script_id,
        status=status,
        resolution="1280x720",
        video_path="storage/videos/test.mp4",
        duration=15.0,
        file_size=4096,
    )
    session.add(video)
    await session.flush()
    await session.refresh(video)
    return video


async def _make_upload(
    session,
    video_id: uuid.UUID,
    status: UploadStatus = UploadStatus.PUBLISHED,
) -> Upload:
    upload = Upload(
        id=uuid.uuid4(),
        video_id=video_id,
        status=status,
        title="Test Title",
        description="Test Description",
        tags=json.dumps(["test", "video"]),
        privacy_status="private",
        youtube_video_id="abc123" if status == UploadStatus.PUBLISHED else None,
        youtube_url=(
            "https://youtube.com/watch?v=abc123"
            if status == UploadStatus.PUBLISHED
            else None
        ),
    )
    session.add(upload)
    await session.flush()
    await session.refresh(upload)
    return upload


def _fake_run_upload(upload_result: Upload):
    """Stand-in for UploadAgentService.run_upload_for_video — returns a ready Upload."""
    async def _run(self, video, upload, settings=None):
        return upload_result
    return _run


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_upload_video_not_found(client: AsyncClient):
    response = await client.post(
        "/api/v1/uploads/",
        json={"video_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_upload_video_not_complete(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id, status=VideoStatus.GENERATING)
    await test_session.commit()

    response = await client.post(
        "/api/v1/uploads/",
        json={"video_id": str(video.id)},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trigger_upload_success(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    published_upload = await _make_upload(test_session, video.id)
    await test_session.commit()

    with patch(
        "app.agents.upload_agent.service.UploadAgentService.run_upload_for_video",
        new=_fake_run_upload(published_upload),
    ):
        response = await client.post(
            "/api/v1/uploads/",
            json={
                "video_id": str(video.id),
                "title": "My Video",
                "description": "Great content",
                "tags": ["tech", "ai"],
                "privacy_status": "private",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["upload"]["video_id"] == str(video.id)
    assert body["upload"]["status"] == UploadStatus.PUBLISHED.value


@pytest.mark.asyncio
async def test_trigger_upload_already_published_returns_existing(
    client: AsyncClient, test_session
):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    existing = await _make_upload(test_session, video.id, status=UploadStatus.PUBLISHED)
    await test_session.commit()

    # No patch needed — service returns existing without calling agent
    response = await client.post(
        "/api/v1/uploads/",
        json={"video_id": str(video.id)},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["upload"]["status"] == UploadStatus.PUBLISHED.value
    assert body["upload"]["youtube_video_id"] == "abc123"


@pytest.mark.asyncio
async def test_trigger_upload_already_uploading_returns_422(
    client: AsyncClient, test_session
):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await _make_upload(test_session, video.id, status=UploadStatus.UPLOADING)
    await test_session.commit()

    response = await client.post(
        "/api/v1/uploads/",
        json={"video_id": str(video.id)},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/uploads/{upload_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_upload_by_id(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/uploads/{upload.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(upload.id)
    assert body["video_id"] == str(video.id)


@pytest.mark.asyncio
async def test_get_upload_by_id_not_found(client: AsyncClient):
    response = await client.get(f"/api/v1/uploads/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/uploads/video/{video_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_upload_by_video(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/uploads/video/{video.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["video_id"] == str(video.id)
    assert body["id"] == str(upload.id)


@pytest.mark.asyncio
async def test_get_upload_by_video_not_found(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await test_session.commit()

    response = await client.get(f"/api/v1/uploads/video/{video.id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/uploads/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_uploads_empty(client: AsyncClient):
    response = await client.get("/api/v1/uploads/")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_uploads_with_status_filter(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    await _make_upload(test_session, video.id, status=UploadStatus.PUBLISHED)
    await test_session.commit()

    response = await client.get("/api/v1/uploads/?status=published&limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert all(item["status"] == "published" for item in body["items"])


@pytest.mark.asyncio
async def test_list_uploads_pagination(client: AsyncClient):
    response = await client.get("/api/v1/uploads/?limit=5&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body


# ---------------------------------------------------------------------------
# DELETE /api/v1/uploads/{upload_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_upload(client: AsyncClient, test_session):
    script = await _make_script(test_session)
    video = await _make_video(test_session, script.id)
    upload = await _make_upload(test_session, video.id)
    await test_session.commit()

    response = await client.delete(f"/api/v1/uploads/{upload.id}")
    assert response.status_code == 200
    assert response.json()["success"] is True

    gone = await client.get(f"/api/v1/uploads/{upload.id}")
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_delete_upload_not_found(client: AsyncClient):
    response = await client.delete(f"/api/v1/uploads/{uuid.uuid4()}")
    assert response.status_code == 404
