"""Unit tests for /api/v1/topics endpoints."""
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

from tests.conftest import create_test_channel, create_test_topic


@pytest_asyncio.fixture
async def channel_data(test_session):
    ch = await create_test_channel(
        test_session,
        name=f"API Channel {uuid.uuid4().hex[:6]}",
        niche="technology",
    )
    return ch


class TestCreateTopic:
    async def test_create_topic_success(self, client: AsyncClient, channel_data, test_session):
        payload = {
            "channel_id": str(channel_data.id),
            "title": "Python Async Guide",
            "score": 90.0,
            "source": "manual",
            "content_type": "long",
        }
        response = await client.post("/api/v1/topics", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["title"] == "Python Async Guide"
        assert data["data"]["score"] == 90.0

    async def test_create_topic_duplicate_returns_422(self, client: AsyncClient, channel_data, test_session):
        payload = {
            "channel_id": str(channel_data.id),
            "title": "Duplicate Topic Test",
            "source": "manual",
        }
        await client.post("/api/v1/topics", json=payload)
        response = await client.post("/api/v1/topics", json=payload)
        assert response.status_code == 422

    async def test_create_topic_invalid_channel_returns_404(self, client: AsyncClient):
        payload = {
            "channel_id": str(uuid.uuid4()),
            "title": "Orphan Topic",
            "source": "manual",
        }
        response = await client.post("/api/v1/topics", json=payload)
        assert response.status_code == 404

    async def test_create_topic_missing_title_returns_422(self, client: AsyncClient, channel_data):
        payload = {"channel_id": str(channel_data.id), "source": "manual"}
        response = await client.post("/api/v1/topics", json=payload)
        assert response.status_code == 422


class TestListTopics:
    async def test_list_topics(self, client: AsyncClient, channel_data, test_session):
        await create_test_topic(test_session, channel_data.id, title=f"List Topic {uuid.uuid4().hex}")
        response = await client.get("/api/v1/topics")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert isinstance(data["data"], list)

    async def test_list_topics_pagination(self, client: AsyncClient, channel_data, test_session):
        for i in range(5):
            await create_test_topic(test_session, channel_data.id, title=f"Page {i} {uuid.uuid4().hex}")
        response = await client.get("/api/v1/topics?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 2
        assert data["limit"] == 2

    async def test_list_topics_by_channel(self, client: AsyncClient, channel_data, test_session):
        await create_test_topic(test_session, channel_data.id, title=f"Ch Topic {uuid.uuid4().hex}")
        response = await client.get(f"/api/v1/topics?channel_id={channel_data.id}")
        assert response.status_code == 200

    async def test_list_pending_topics(self, client: AsyncClient, channel_data, test_session):
        await create_test_topic(test_session, channel_data.id, title=f"Pending {uuid.uuid4().hex}")
        response = await client.get("/api/v1/topics/pending")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestGetTopic:
    async def test_get_topic_by_id(self, client: AsyncClient, channel_data, test_session):
        topic = await create_test_topic(test_session, channel_data.id, title=f"Get {uuid.uuid4().hex}")
        response = await client.get(f"/api/v1/topics/{topic.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == str(topic.id)

    async def test_get_topic_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/v1/topics/{uuid.uuid4()}")
        assert response.status_code == 404


class TestUpdateTopic:
    async def test_update_topic_score(self, client: AsyncClient, channel_data, test_session):
        topic = await create_test_topic(test_session, channel_data.id, title=f"Upd {uuid.uuid4().hex}")
        response = await client.patch(f"/api/v1/topics/{topic.id}", json={"score": 99.0})
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["score"] == 99.0

    async def test_approve_topic(self, client: AsyncClient, channel_data, test_session):
        topic = await create_test_topic(test_session, channel_data.id, title=f"Approve {uuid.uuid4().hex}")
        response = await client.post(f"/api/v1/topics/{topic.id}/approve")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "researching"

    async def test_reject_topic(self, client: AsyncClient, channel_data, test_session):
        topic = await create_test_topic(test_session, channel_data.id, title=f"Reject {uuid.uuid4().hex}")
        response = await client.post(f"/api/v1/topics/{topic.id}/reject")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "rejected"


class TestDeleteTopic:
    async def test_delete_topic(self, client: AsyncClient, channel_data, test_session):
        topic = await create_test_topic(test_session, channel_data.id, title=f"Del {uuid.uuid4().hex}")
        response = await client.delete(f"/api/v1/topics/{topic.id}")
        assert response.status_code == 200
        get_response = await client.get(f"/api/v1/topics/{topic.id}")
        assert get_response.status_code == 404

    async def test_delete_not_found(self, client: AsyncClient):
        response = await client.delete(f"/api/v1/topics/{uuid.uuid4()}")
        assert response.status_code == 404