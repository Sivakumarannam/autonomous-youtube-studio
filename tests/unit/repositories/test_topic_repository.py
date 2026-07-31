"""Unit tests for TopicRepository."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel
from app.database.models.topic import Topic, TopicSource, TopicStatus
from app.database.repositories.topic_repository import TopicRepository
from tests.conftest import create_test_channel, create_test_topic


@pytest_asyncio.fixture
async def channel(test_session: AsyncSession) -> Channel:
    return await create_test_channel(test_session, name=f"ch-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic_repo(test_session: AsyncSession) -> TopicRepository:
    return TopicRepository(test_session)


class TestTopicRepositoryCreate:
    async def test_create_topic(self, test_session, channel, topic_repo):
        topic = Topic(
            channel_id=channel.id,
            title="Docker vs Kubernetes",
            score=95.0,
            reason="High search volume",
            source=TopicSource.GOOGLE_TRENDS,
        )
        created = await topic_repo.create(topic)
        assert created.id is not None
        assert created.title == "Docker vs Kubernetes"
        assert created.score == 95.0
        assert created.status == TopicStatus.PENDING

    async def test_create_multiple_topics(self, test_session, channel, topic_repo):
        for i in range(3):
            t = Topic(channel_id=channel.id, title=f"Topic {i}", score=float(80 + i))
            await topic_repo.create(t)
        all_topics = await topic_repo.get_by_channel(channel.id, limit=10)
        assert len(all_topics) == 3


class TestTopicRepositoryGet:
    async def test_get_by_id(self, test_session, channel, topic_repo):
        topic = await create_test_topic(test_session, channel.id, title="Get By ID Test")
        fetched = await topic_repo.get_by_id(topic.id)
        assert fetched is not None
        assert fetched.id == topic.id

    async def test_get_by_id_missing_returns_none(self, test_session, topic_repo):
        result = await topic_repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_id_or_raise_missing(self, test_session, topic_repo):
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await topic_repo.get_by_id_or_raise(uuid.uuid4())

    async def test_get_by_channel(self, test_session, channel, topic_repo):
        for i in range(4):
            await create_test_topic(test_session, channel.id, title=f"Channel Topic {i}")
        topics = await topic_repo.get_by_channel(channel.id, limit=10)
        assert len(topics) == 4

    async def test_get_by_channel_limit(self, test_session, channel, topic_repo):
        for i in range(5):
            await create_test_topic(test_session, channel.id, title=f"Limit Topic {i}")
        topics = await topic_repo.get_by_channel(channel.id, limit=2)
        assert len(topics) == 2

    async def test_get_pending(self, test_session, channel, topic_repo):
        await create_test_topic(test_session, channel.id, title="Pending 1")
        await create_test_topic(test_session, channel.id, title="Pending 2")
        t3 = await create_test_topic(test_session, channel.id, title="Not Pending")
        await topic_repo.update(t3, status=TopicStatus.RESEARCHING)

        pending = await topic_repo.get_pending(channel_id=channel.id)
        titles = [t.title for t in pending]
        assert "Pending 1" in titles
        assert "Pending 2" in titles
        assert "Not Pending" not in titles

    async def test_get_by_status(self, test_session, channel, topic_repo):
        t = await create_test_topic(test_session, channel.id, title="Status Test")
        await topic_repo.update(t, status=TopicStatus.SCRIPTING)
        scripting = await topic_repo.get_by_status(TopicStatus.SCRIPTING, channel_id=channel.id)
        assert any(s.id == t.id for s in scripting)

    async def test_get_top_scored(self, test_session, channel, topic_repo):
        await create_test_topic(test_session, channel.id, title="Low Score", score=30.0)
        await create_test_topic(test_session, channel.id, title="High Score", score=99.0)
        await create_test_topic(test_session, channel.id, title="Mid Score", score=60.0)
        top = await topic_repo.get_top_scored(channel.id, limit=2)
        assert top[0].score >= top[1].score


class TestTopicRepositoryUpdate:
    async def test_set_status(self, test_session, channel, topic_repo):
        topic = await create_test_topic(test_session, channel.id, title="Status Update")
        updated = await topic_repo.set_status(topic.id, TopicStatus.SCRIPTING)
        assert updated is not None
        assert updated.status == TopicStatus.SCRIPTING

    async def test_set_status_missing_returns_none(self, test_session, topic_repo):
        result = await topic_repo.set_status(uuid.uuid4(), TopicStatus.SCRIPTING)
        assert result is None

    async def test_update_score(self, test_session, channel, topic_repo):
        topic = await create_test_topic(test_session, channel.id, title="Score Update")
        updated = await topic_repo.update(topic, score=99.0)
        assert updated.score == 99.0


class TestTopicRepositoryDedup:
    async def test_title_exists_true(self, test_session, channel, topic_repo):
        await create_test_topic(test_session, channel.id, title="Duplicate Title")
        exists = await topic_repo.title_exists("Duplicate Title", channel.id)
        assert exists is True

    async def test_title_exists_false(self, test_session, channel, topic_repo):
        exists = await topic_repo.title_exists("This Does Not Exist", channel.id)
        assert exists is False

    async def test_title_exists_different_channel(self, test_session, topic_repo):
        ch1 = await create_test_channel(test_session, name=f"ch1-{uuid.uuid4().hex[:4]}")
        ch2 = await create_test_channel(test_session, name=f"ch2-{uuid.uuid4().hex[:4]}")
        await create_test_topic(test_session, ch1.id, title="Same Title Different Channel")
        # Different channel — should not exist
        exists = await topic_repo.title_exists("Same Title Different Channel", ch2.id)
        assert exists is False


class TestTopicRepositoryCount:
    async def test_count(self, test_session, channel, topic_repo):
        before = await topic_repo.count()
        await create_test_topic(test_session, channel.id, title=f"Count {uuid.uuid4().hex}")
        await create_test_topic(test_session, channel.id, title=f"Count {uuid.uuid4().hex}")
        after = await topic_repo.count()
        assert after == before + 2

    async def test_delete_by_id(self, test_session, channel, topic_repo):
        topic = await create_test_topic(test_session, channel.id, title="Delete Me")
        deleted = await topic_repo.delete_by_id(topic.id)
        assert deleted is True
        assert await topic_repo.get_by_id(topic.id) is None