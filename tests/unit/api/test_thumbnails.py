"""Unit tests for /api/v1/thumbnails endpoints."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient

from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.thumbnail import Thumbnail, ThumbnailStatus
from app.agents.thumbnail_agent.models import ThumbnailAgentOutput, ThumbnailDesign
from tests.conftest import create_test_channel, create_test_topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_script(session, topic, channel, **kwargs) -> Script:
    script = Script(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=kwargs.get("script_type", ScriptType.LONG),
        content=kwargs.get("content", "Test script content for thumbnail tests"),
        word_count=kwargs.get("word_count", 120),
        estimated_duration=kwargs.get("estimated_duration", 480),
        status=kwargs.get("status", ScriptStatus.APPROVED),
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script



async def _make_thumbnail(session, script_id: uuid.UUID, **kwargs) -> Thumbnail:
    thumbnail = Thumbnail(
        script_id=script_id,
        concept=kwargs.get("concept", "Bold tech thumbnail with glowing circuit board"),
        file_path=kwargs.get("file_path", "/thumbnails/test.png"),
        status=kwargs.get("status", ThumbnailStatus.COMPLETE),
    )
    session.add(thumbnail)
    await session.flush()
    await session.refresh(thumbnail)
    return thumbnail


def _mock_agent_output() -> ThumbnailAgentOutput:
    return ThumbnailAgentOutput(
        concept="Bold tech thumbnail with glowing circuit board",
        design=ThumbnailDesign(
            background_color="#1A1A2E",
            accent_color="#E94560",
            text_color="#FFFFFF",
            layout="split",
            subject="circuit board",
            background_style="gradient",
        ),
        title_text="TOP 10 AI TOOLS",
        subtitle_text="You need to know",
        emoji="🤖",
        file_path="/thumbnails/generated.png",
        ctr_score=82.5,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def channel_and_topic(test_session):
    ch = await create_test_channel(test_session, name=f"Thumb Channel {uuid.uuid4().hex[:6]}")
    topic = await create_test_topic(test_session, ch.id, title=f"Thumb Topic {uuid.uuid4().hex[:6]}")
    return ch, topic


@pytest_asyncio.fixture
async def script(test_session, channel_and_topic):
    ch, topic = channel_and_topic
    script = await _make_script(test_session, topic, ch)
    return script


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class TestGenerateThumbnail:
    async def test_generate_success(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        agent_output = _mock_agent_output()

        with patch(
            "app.api.services.thumbnail_service.ThumbnailAgentService.run_for_script",
            new_callable=AsyncMock,
        ) as mock_run:
            # Simulate the agent creating the thumbnail row in the DB
            async def _side_effect(script, **kwargs):
                thumbnail = Thumbnail(
                    script_id=script.id,
                    concept=agent_output.concept,
                    file_path=agent_output.file_path,
                    status=ThumbnailStatus.COMPLETE,
                )
                test_session.add(thumbnail)
                await test_session.flush()
                return agent_output

            mock_run.side_effect = _side_effect

            response = await client.post(
                "/api/v1/thumbnails/generate",
                json={
                    "script_id": str(script.id),
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["script_id"] == str(script.id)
        assert data["concept"] == agent_output.concept
        assert data["status"] == ThumbnailStatus.COMPLETE.value
        assert data["file_path"] == "/thumbnails/generated.png"

        mock_run.assert_awaited_once()

    async def test_generate_script_not_found(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/thumbnails/generate",
            json={
                "script_id": str(uuid.uuid4()),
            },
        )

        assert response.status_code == 404

    async def test_generate_missing_fields(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/thumbnails/generate",
            json={},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /script/{script_id}
# ---------------------------------------------------------------------------

class TestGetThumbnailByScript:
    async def test_get_by_script_success(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.get(f"/api/v1/thumbnails/script/{script.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(thumbnail.id)
        assert data["script_id"] == str(script.id)

    async def test_get_by_script_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/v1/thumbnails/script/{uuid.uuid4()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /{thumbnail_id}
# ---------------------------------------------------------------------------

class TestGetThumbnail:
    async def test_get_by_id_success(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.get(f"/api/v1/thumbnails/{thumbnail.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(thumbnail.id)
        assert data["status"] == ThumbnailStatus.COMPLETE.value

    async def test_get_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/v1/thumbnails/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_get_returns_correct_fields(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(
            test_session,
            script.id,
            concept="Custom concept",
            file_path="/thumbnails/custom.png",
        )

        response = await client.get(f"/api/v1/thumbnails/{thumbnail.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["concept"] == "Custom concept"
        assert data["file_path"] == "/thumbnails/custom.png"


# ---------------------------------------------------------------------------
# PUT /{thumbnail_id}
# ---------------------------------------------------------------------------

class TestUpdateThumbnail:
    async def test_update_concept(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.put(
            f"/api/v1/thumbnails/{thumbnail.id}",
            json={"concept": "Updated concept description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["concept"] == "Updated concept description"

    async def test_update_file_path(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.put(
            f"/api/v1/thumbnails/{thumbnail.id}",
            json={"file_path": "/thumbnails/updated.png"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_path"] == "/thumbnails/updated.png"

    async def test_update_status(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(
            test_session, script.id, status=ThumbnailStatus.GENERATING
        )

        response = await client.put(
            f"/api/v1/thumbnails/{thumbnail.id}",
            json={"status": ThumbnailStatus.COMPLETE.value},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ThumbnailStatus.COMPLETE.value

    async def test_update_multiple_fields(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.put(
            f"/api/v1/thumbnails/{thumbnail.id}",
            json={
                "concept": "New concept",
                "file_path": "/new/path.png",
                "status": ThumbnailStatus.COMPLETE.value,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["concept"] == "New concept"
        assert data["file_path"] == "/new/path.png"

    async def test_update_not_found(self, client: AsyncClient):
        response = await client.put(
            f"/api/v1/thumbnails/{uuid.uuid4()}",
            json={"concept": "Does not matter"},
        )
        assert response.status_code == 404

    async def test_update_invalid_status(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.put(
            f"/api/v1/thumbnails/{thumbnail.id}",
            json={"status": "invalid_status"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /{thumbnail_id}
# ---------------------------------------------------------------------------

class TestDeleteThumbnail:
    async def test_delete_success(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)

        response = await client.delete(f"/api/v1/thumbnails/{thumbnail.id}")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

    async def test_delete_not_found(self, client: AsyncClient):
        response = await client.delete(f"/api/v1/thumbnails/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_deleted_thumbnail_returns_404(
        self,
        client: AsyncClient,
        script,
        test_session,
    ):
        thumbnail = await _make_thumbnail(test_session, script.id)
        thumbnail_id = thumbnail.id

        await client.delete(f"/api/v1/thumbnails/{thumbnail_id}")

        response = await client.get(f"/api/v1/thumbnails/{thumbnail_id}")
        assert response.status_code == 404