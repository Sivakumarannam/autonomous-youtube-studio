"""Unit tests for TopicService."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.topic import TopicCreate, TopicUpdate
from app.api.services.topic_service import TopicService
from app.core.exceptions import NotFoundError, ValidationError
from app.database.models.topic import TopicSource, TopicStatus
from tests.conftest import create_test_channel, create_test_topic


@pytest_asyncio.fixture
async def channel(test_session):
    return await create_test_channel(test_session, name=f"svc-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def service(test_session: AsyncSession) -> TopicService:
    return TopicService(test_session)


class TestTopicServiceCreate:
    async def test_create_topic(self, test_session, channel, service):
        data = TopicCreate(
            channel_id=channel.id,
            title="Python FastAPI Tutorial",
            score=88.0,
            source=TopicSource.MANUAL,
            content_type="long",
        )
        topic = await service.create(data)
        assert topic.id is not None
        assert topic.title == "Python FastAPI Tutorial"
        assert topic.score == 88.0

    async def test_create_duplicate_raises(self, test_session, channel, service):
        data = TopicCreate(
            channel_id=channel.id,
            title="Duplicate Topic",
            source=TopicSource.MANUAL,
        )
        await service.create(data)
        with pytest.raises(ValidationError, match="already exists"):
            await service.create(data)

    async def test_create_invalid_channel_raises(self, test_session, service):
        data = TopicCreate(
            channel_id=uuid.uuid4(),
            title="No Channel Topic",
            source=TopicSource.MANUAL,
        )
        with pytest.raises(NotFoundError):
            await service.create(data)

    async def test_create_with_keywords(self, test_session, channel, service):
        data = TopicCreate(
            channel_id=channel.id,
            title="Keyword Test Topic",
            keywords=["python", "fastapi", "rest"],
            source=TopicSource.MANUAL,
        )
        topic = await service.create(data)
        assert topic.keywords is not None
        assert "python" in topic.keywords


class TestTopicServiceGet:
    async def test_get_by_id(self, test_session, channel, service):
        topic = await create_test_topic(test_session, channel.id, title=f"Get {uuid.uuid4().hex}")
        fetched = await service.get_by_id(topic.id)
        assert fetched.id == topic.id

    async def test_get_by_id_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_get_by_channel(self, test_session, channel, service):
        for i in range(3):
            await create_test_topic(test_session, channel.id, title=f"Ch Topic {i} {uuid.uuid4().hex}")
        topics, total = await service.get_by_channel(channel.id)
        assert len(topics) >= 3

    async def test_get_by_channel_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_channel(uuid.uuid4())

    async def test_get_all(self, test_session, channel, service):
        await create_test_topic(test_session, channel.id, title=f"All {uuid.uuid4().hex}")
        topics, total = await service.get_all()
        assert len(topics) >= 1
        assert total >= 1

    async def test_get_pending(self, test_session, channel, service):
        await create_test_topic(test_session, channel.id, title=f"Pending {uuid.uuid4().hex}")
        pending = await service.get_pending(channel_id=channel.id)
        assert len(pending) >= 1


class TestTopicServiceUpdate:
    async def test_update_topic(self, test_session, channel, service):
        topic = await create_test_topic(test_session, channel.id, title=f"Update {uuid.uuid4().hex}")
        updated = await service.update(topic.id, TopicUpdate(score=99.0))
        assert updated.score == 99.0

    async def test_update_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.update(uuid.uuid4(), TopicUpdate(score=50.0))

    async def test_set_status(self, test_session, channel, service):
        topic = await create_test_topic(test_session, channel.id, title=f"Status {uuid.uuid4().hex}")
        updated = await service.set_status(topic.id, TopicStatus.SCRIPTING)
        assert updated.status == TopicStatus.SCRIPTING

    async def test_set_status_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.set_status(uuid.uuid4(), TopicStatus.SCRIPTING)


class TestTopicServiceDelete:
    async def test_delete_topic(self, test_session, channel, service):
        topic = await create_test_topic(test_session, channel.id, title=f"Del {uuid.uuid4().hex}")
        await service.delete(topic.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(topic.id)

    async def test_delete_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.delete(uuid.uuid4())


class TestTopicServiceSaveGenerated:
    async def test_save_generated_topics(self, test_session, channel, service):
        generated = [
            {"topic": f"Gen Topic A {uuid.uuid4().hex}", "score": 95.0, "reason": "Trending", "keywords": ["a"]},
            {"topic": f"Gen Topic B {uuid.uuid4().hex}", "score": 88.0, "reason": "Popular", "keywords": ["b"]},
        ]
        saved = await service.save_generated_topics(
            channel_id=channel.id,
            generated=generated,
            source=TopicSource.GOOGLE_TRENDS,
            content_type="long",
        )
        assert len(saved) == 2

    async def test_save_generated_skips_duplicates(self, test_session, channel, service):
        title = f"Dup Gen {uuid.uuid4().hex}"
        generated = [{"topic": title, "score": 90.0, "reason": "X", "keywords": []}]
        await service.save_generated_topics(channel.id, generated, TopicSource.MANUAL, "long")
        # Second call with same title
        saved2 = await service.save_generated_topics(channel.id, generated, TopicSource.MANUAL, "long")
        assert len(saved2) == 0

    async def test_save_generated_skips_empty_titles(self, test_session, channel, service):
        generated = [{"topic": "", "score": 90.0, "reason": "Empty", "keywords": []}]
        saved = await service.save_generated_topics(channel.id, generated, TopicSource.MANUAL, "long")
        assert len(saved) == 0