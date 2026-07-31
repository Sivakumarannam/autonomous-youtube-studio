"""Unit tests for ResearchService."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services.research_service import ResearchService
from app.core.exceptions import NotFoundError
from app.database.models.research import ResearchStatus
from tests.conftest import create_test_channel, create_test_topic, create_test_research


@pytest_asyncio.fixture
async def channel(test_session):
    return await create_test_channel(test_session, name=f"rsvc-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic(test_session, channel):
    return await create_test_topic(test_session, channel.id, title=f"RS Topic {uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def service(test_session: AsyncSession) -> ResearchService:
    return ResearchService(test_session)


class TestResearchServiceGet:
    async def test_get_by_id(self, test_session, topic, service):
        r = await create_test_research(test_session, topic.id)
        fetched = await service.get_by_id(r.id)
        assert fetched.id == r.id

    async def test_get_by_id_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_get_by_topic_id(self, test_session, topic, service):
        r = await create_test_research(test_session, topic.id)
        fetched = await service.get_by_topic_id(topic.id)
        assert fetched is not None
        assert fetched.id == r.id

    async def test_get_by_topic_id_invalid_topic(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_topic_id(uuid.uuid4())

    async def test_get_by_topic_id_no_research(self, test_session, topic, service):
        result = await service.get_by_topic_id(topic.id)
        assert result is None

    async def test_get_all(self, test_session, topic, service):
        await create_test_research(test_session, topic.id)
        results, total = await service.get_all()
        assert len(results) >= 1
        assert total >= 1


class TestResearchServiceCreateOrUpdate:
    async def test_create_or_update_creates(self, test_session, topic, service):
        r = await service.create_or_update(
            topic_id=topic.id,
            summary="Test summary",
            key_facts='["fact 1"]',
            references='["https://test.com"]',
        )
        assert r.id is not None
        assert r.summary == "Test summary"
        assert r.status == ResearchStatus.COMPLETE

    async def test_create_or_update_updates(self, test_session, topic, service):
        r1 = await service.create_or_update(topic_id=topic.id, summary="First")
        r2 = await service.create_or_update(topic_id=topic.id, summary="Updated")
        assert r1.id == r2.id
        assert r2.summary == "Updated"

    async def test_create_or_update_invalid_topic(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.create_or_update(topic_id=uuid.uuid4(), summary="No topic")


class TestResearchServiceSetStatus:
    async def test_set_status(self, test_session, topic, service):
        r = await create_test_research(test_session, topic.id)
        updated = await service.set_status(r.id, ResearchStatus.PROCESSING)
        assert updated.status == ResearchStatus.PROCESSING

    async def test_set_status_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.set_status(uuid.uuid4(), ResearchStatus.COMPLETE)