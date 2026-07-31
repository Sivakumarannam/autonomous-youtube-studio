import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database.models.script import (
    Script,
    ScriptStatus,
    ScriptType,
)
from app.database.models.video import Video, VideoStatus


async def _make_script(test_session, **overrides) -> Script:
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=overrides.get("script_type", ScriptType.LONG),
        content=overrides.get("content", "API video generation test"),
        status=overrides.get("status", ScriptStatus.APPROVED),
    )

    test_session.add(script)
    await test_session.commit()

    return script


def _fake_run_for_script(test_session):
    """
    Stand-in for VideoAgentService.run_for_script that writes a
    completed Video row directly, without invoking Pillow/moviepy/ffmpeg.
    Keeps these API tests fast and dependency-free, matching how
    test_thumbnail_service.py mocks the agent layer.
    """

    async def _run(self, script, topic_title="", description="", script_type="long"):
        video = Video(
            script_id=script.id,
            status=VideoStatus.COMPLETE,
            resolution="1280x720",
            video_path=f"storage/videos/{script.id}.mp4",
            duration=15.0,
            file_size=4096,
        )
        test_session.add(video)
        await test_session.commit()
        return None

    return _run


@pytest.mark.asyncio
async def test_generate_video_endpoint(client: AsyncClient, test_session):
    script = await _make_script(test_session)

    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new=_fake_run_for_script(test_session),
    ):
        response = await client.post(
            "/api/v1/videos/generate",
            json={"script_id": str(script.id)},
        )

    print("DEBUG RESPONSE:", response.status_code, response.json())

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["video"]["script_id"] == str(script.id)
    assert body["video"]["status"] == VideoStatus.COMPLETE.value


@pytest.mark.asyncio
async def test_generate_video_invalid_script(client: AsyncClient):
    response = await client.post(
        "/api/v1/videos/generate",
        json={"script_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_video_by_script_endpoint(client: AsyncClient, test_session):
    script = await _make_script(test_session)

    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new=_fake_run_for_script(test_session),
    ):
        await client.post(
            "/api/v1/videos/generate",
            json={"script_id": str(script.id)},
        )

    response = await client.get(f"/api/v1/videos/script/{script.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["script_id"] == str(script.id)


@pytest.mark.asyncio
async def test_list_completed_videos(client: AsyncClient):
    response = await client.get("/api/v1/videos/?limit=10")

    assert response.status_code == 200

    body = response.json()

    assert "items" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_regenerate_video_endpoint(client: AsyncClient, test_session):
    script = await _make_script(test_session)

    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new=_fake_run_for_script(test_session),
    ):
        await client.post(
            "/api/v1/videos/generate",
            json={"script_id": str(script.id)},
        )

        response = await client.post(
            f"/api/v1/videos/{script.id}/regenerate",
        )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["video"]["script_id"] == str(script.id)


@pytest.mark.asyncio
async def test_batch_generate_videos_endpoint(client: AsyncClient):
    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_approved_scripts",
        AsyncMock(return_value=[]),
    ):
        response = await client.post("/api/v1/videos/batch?limit=3")

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["generated_count"] == 0


@pytest.mark.asyncio
async def test_delete_video_endpoint(client: AsyncClient, test_session):
    script = await _make_script(test_session)

    with patch(
        "app.agents.video_agent.service.VideoAgentService.run_for_script",
        new=_fake_run_for_script(test_session),
    ):
        create = await client.post(
            "/api/v1/videos/generate",
            json={"script_id": str(script.id)},
        )

    video_id = create.json()["video"]["id"]

    response = await client.delete(f"/api/v1/videos/{video_id}")

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True