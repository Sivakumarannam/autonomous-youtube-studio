"""Unit tests for /api/v1/research endpoints."""
import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_channel, create_test_topic, create_test_research


@pytest.fixture
async def channel_and_topic(test_session):
    ch = await create_test_channel(test_session, name=f"RC {uuid.uuid4().hex[:6]}")
    topic = await create_test_topic(test_session, ch.id, title=f"Research Test {uuid.uuid4().hex[:6]}")
    return ch, topic


class TestListResearch:
    async def test_list_research(self, client: AsyncClient, channel_and_topic, test_session):
        _, topic = channel_and_topic
        await create_test_research(test_session, topic.id)
        response = await client.get("/api/v1/research")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_list_research_pagination(self, client: AsyncClient):
        response = await client.get("/api/v1/research?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5


class TestGetResearch:
    async def test_get_by_id(self, client: AsyncClient, channel_and_topic, test_session):
        _, topic = channel_and_topic
        r = await create_test_research(test_session, topic.id)
        response = await client.get(f"/api/v1/research/{r.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == str(r.id)

    async def test_get_by_id_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/v1/research/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_get_by_topic_id(self, client: AsyncClient, channel_and_topic, test_session):
        _, topic = channel_and_topic
        r = await create_test_research(test_session, topic.id)
        response = await client.get(f"/api/v1/research/topic/{topic.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["topic_id"] == str(topic.id)

    async def test_get_by_topic_id_no_research_returns_404(self, client: AsyncClient, channel_and_topic, test_session):
        ch = await create_test_channel(test_session, name=f"NoR {uuid.uuid4().hex[:6]}")
        topic2 = await create_test_topic(test_session, ch.id, title=f"No Research {uuid.uuid4().hex[:6]}")
        response = await client.get(f"/api/v1/research/topic/{topic2.id}")
        assert response.status_code == 404

    async def test_get_by_topic_id_invalid_topic(self, client: AsyncClient):
        response = await client.get(f"/api/v1/research/topic/{uuid.uuid4()}")
        assert response.status_code == 404


class TestRunResearch:
    async def test_run_research_uses_mock_llm(self, client: AsyncClient, channel_and_topic, test_session):
        """POST /api/v1/research triggers the ResearchAgent (mock LLM)."""
        _, topic = channel_and_topic
        payload = {"topic_id": str(topic.id)}
        response = await client.post("/api/v1/research", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["topic_id"] == str(topic.id)
        assert data["data"]["summary"] is not None

    async def test_run_research_invalid_topic(self, client: AsyncClient):
        payload = {"topic_id": str(uuid.uuid4())}
        response = await client.post("/api/v1/research", json=payload)
        assert response.status_code == 404