"""Unit tests for /api/v1/scripts endpoints."""
import uuid
import pytest
from httpx import AsyncClient

from app.database.models.script import Script, ScriptStatus, ScriptType
from tests.conftest import create_test_channel, create_test_topic, create_test_research


@pytest.fixture
async def channel_and_topic(test_session):
    ch = await create_test_channel(test_session, name=f"SC API {uuid.uuid4().hex[:6]}")
    topic = await create_test_topic(test_session, ch.id, title=f"Script API Topic {uuid.uuid4().hex[:6]}")
    return ch, topic


async def _make_script(session, topic, channel, **kwargs) -> Script:
    script = Script(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=kwargs.get("script_type", ScriptType.LONG),
        content=kwargs.get("content", "Test script content for the video"),
        word_count=kwargs.get("word_count", 100),
        estimated_duration=kwargs.get("estimated_duration", 480),
        status=kwargs.get("status", ScriptStatus.DRAFT),
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


class TestListScripts:
    async def test_list_scripts(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        await _make_script(test_session, topic, ch)
        response = await client.get("/api/v1/scripts")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_list_by_channel(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        await _make_script(test_session, topic, ch)
        response = await client.get(f"/api/v1/scripts?channel_id={ch.id}")
        assert response.status_code == 200

    async def test_list_by_type_long(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        await _make_script(test_session, topic, ch, script_type=ScriptType.LONG)
        response = await client.get("/api/v1/scripts?script_type=long")
        assert response.status_code == 200

    async def test_list_by_status_draft(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        await _make_script(test_session, topic, ch, status=ScriptStatus.DRAFT)
        response = await client.get("/api/v1/scripts?status=draft")
        assert response.status_code == 200

    async def test_list_pagination(self, client: AsyncClient):
        response = await client.get("/api/v1/scripts?limit=3&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 3


class TestGetScript:
    async def test_get_by_id(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        script = await _make_script(test_session, topic, ch)
        response = await client.get(f"/api/v1/scripts/{script.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == str(script.id)

    async def test_get_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/v1/scripts/{uuid.uuid4()}")
        assert response.status_code == 404


class TestUpdateScript:
    async def test_update_seo_title(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        script = await _make_script(test_session, topic, ch)
        response = await client.patch(
            f"/api/v1/scripts/{script.id}",
            json={"seo_title": "Updated SEO Title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["seo_title"] == "Updated SEO Title"

    async def test_approve_script(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        script = await _make_script(test_session, topic, ch)
        response = await client.post(f"/api/v1/scripts/{script.id}/approve")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "approved"

    async def test_reject_script(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        script = await _make_script(test_session, topic, ch)
        response = await client.post(f"/api/v1/scripts/{script.id}/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "rejected"

    async def test_update_not_found(self, client: AsyncClient):
        response = await client.patch(f"/api/v1/scripts/{uuid.uuid4()}", json={"seo_title": "X"})
        assert response.status_code == 404


class TestDeleteScript:
    async def test_delete_script(self, client: AsyncClient, channel_and_topic, test_session):
        ch, topic = channel_and_topic
        script = await _make_script(test_session, topic, ch)
        response = await client.delete(f"/api/v1/scripts/{script.id}")
        assert response.status_code == 200
        get_response = await client.get(f"/api/v1/scripts/{script.id}")
        assert get_response.status_code == 404

    async def test_delete_not_found(self, client: AsyncClient):
        response = await client.delete(f"/api/v1/scripts/{uuid.uuid4()}")
        assert response.status_code == 404


class TestGenerateScripts:
    async def test_generate_short_script(self, client: AsyncClient, channel_and_topic, test_session):
        """POST /api/v1/scripts/short generates via mock LLM."""
        ch, topic = channel_and_topic
        await create_test_research(test_session, topic.id)
        payload = {
            "topic_id": str(topic.id),
            "channel_id": str(ch.id),
            "script_type": "short",
        }
        response = await client.post("/api/v1/scripts/short", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["script_type"] == "short"
        assert data["data"]["content"] is not None

    async def test_generate_long_script(self, client: AsyncClient, channel_and_topic, test_session):
        """POST /api/v1/scripts/long generates via mock LLM."""
        ch, topic = channel_and_topic
        await create_test_research(test_session, topic.id)
        payload = {
            "topic_id": str(topic.id),
            "channel_id": str(ch.id),
            "script_type": "long",
        }
        response = await client.post("/api/v1/scripts/long", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["script_type"] == "long"

    async def test_generate_short_invalid_topic(self, client: AsyncClient, channel_and_topic):
        ch, _ = channel_and_topic
        payload = {
            "topic_id": str(uuid.uuid4()),
            "channel_id": str(ch.id),
            "script_type": "short",
        }
        response = await client.post("/api/v1/scripts/short", json=payload)
        assert response.status_code == 404