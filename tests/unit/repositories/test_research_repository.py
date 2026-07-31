"""Unit tests for ResearchRepository."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel
from app.database.models.research import Research, ResearchStatus
from app.database.models.topic import Topic
from app.database.repositories.research_repository import ResearchRepository
from tests.conftest import create_test_channel, create_test_topic, create_test_research


@pytest_asyncio.fixture
async def channel(test_session: AsyncSession) -> Channel:
    return await create_test_channel(test_session, name=f"rc-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic(test_session: AsyncSession, channel: Channel) -> Topic:
    return await create_test_topic(test_session, channel.id, title=f"Research Topic {uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def repo(test_session: AsyncSession) -> ResearchRepository:
    return ResearchRepository(test_session)


class TestResearchRepositoryCreate:
    async def test_create_research(self, test_session, topic, repo):
        r = Research(
            topic_id=topic.id,
            summary="This is a test summary",
            key_facts='["fact 1", "fact 2"]',
            references='["https://example.com"]',
        )
        created = await repo.create(r)
        assert created.id is not None
        assert created.summary == "This is a test summary"
        assert created.status == ResearchStatus.PENDING

    async def test_upsert_creates_new(self, test_session, topic, repo):
        r = await repo.upsert_for_topic(
            topic_id=topic.id,
            summary="Upsert created",
            status=ResearchStatus.COMPLETE,
        )
        assert r.id is not None
        assert r.summary == "Upsert created"

    async def test_upsert_updates_existing(self, test_session, topic, repo):
        r1 = await repo.upsert_for_topic(topic_id=topic.id, summary="First")
        r2 = await repo.upsert_for_topic(topic_id=topic.id, summary="Updated")
        assert r1.id == r2.id
        assert r2.summary == "Updated"


class TestResearchRepositoryGet:
    async def test_get_by_id(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        fetched = await repo.get_by_id(r.id)
        assert fetched is not None
        assert fetched.id == r.id

    async def test_get_by_id_missing_returns_none(self, test_session, repo):
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_topic_id(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        fetched = await repo.get_by_topic_id(topic.id)
        assert fetched is not None
        assert fetched.id == r.id

    async def test_get_by_topic_id_missing(self, test_session, repo):
        result = await repo.get_by_topic_id(uuid.uuid4())
        assert result is None

    async def test_get_by_status(self, test_session, topic, repo):
        await create_test_research(test_session, topic.id, status=ResearchStatus.COMPLETE)
        complete = await repo.get_by_status(ResearchStatus.COMPLETE)
        assert len(complete) >= 1

    async def test_get_complete(self, test_session, topic, repo):
        await create_test_research(test_session, topic.id, status=ResearchStatus.COMPLETE)
        results = await repo.get_complete()
        assert all(r.status == ResearchStatus.COMPLETE for r in results)


class TestResearchRepositoryUpdate:
    async def test_set_status(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        updated = await repo.set_status(r.id, ResearchStatus.PROCESSING)
        assert updated is not None
        assert updated.status == ResearchStatus.PROCESSING

    async def test_set_status_missing_returns_none(self, test_session, repo):
        result = await repo.set_status(uuid.uuid4(), ResearchStatus.COMPLETE)
        assert result is None

    async def test_update_summary(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        updated = await repo.update(r, summary="New summary content")
        assert updated.summary == "New summary content"


class TestResearchRepositoryDelete:
    async def test_delete(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        await repo.delete(r)
        assert await repo.get_by_id(r.id) is None

    async def test_exists(self, test_session, topic, repo):
        r = await create_test_research(test_session, topic.id)
        assert await repo.exists(r.id) is True
        assert await repo.exists(uuid.uuid4()) is False