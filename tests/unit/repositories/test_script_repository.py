"""Unit tests for ScriptRepository."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.topic import Topic
from app.database.repositories.script_repository import ScriptRepository
from tests.conftest import create_test_channel, create_test_topic


async def _make_script(session, topic: Topic, channel: Channel, **kwargs) -> Script:
    script = Script(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=kwargs.get("script_type", ScriptType.LONG),
        content=kwargs.get("content", "Test script content for YouTube video"),
        word_count=kwargs.get("word_count", 10),
        estimated_duration=kwargs.get("estimated_duration", 60),
        status=kwargs.get("status", ScriptStatus.DRAFT),
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


@pytest_asyncio.fixture
async def channel(test_session: AsyncSession) -> Channel:
    return await create_test_channel(test_session, name=f"sc-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic(test_session: AsyncSession, channel: Channel) -> Topic:
    return await create_test_topic(test_session, channel.id, title=f"Script Topic {uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def repo(test_session: AsyncSession) -> ScriptRepository:
    return ScriptRepository(test_session)


class TestScriptRepositoryCreate:
    async def test_create_long_script(self, test_session, topic, channel, repo):
        script = Script(
            topic_id=topic.id,
            channel_id=channel.id,
            script_type=ScriptType.LONG,
            content="This is a long-form script about Docker and Kubernetes",
            word_count=10,
            estimated_duration=480,
        )
        created = await repo.create(script)
        assert created.id is not None
        assert created.script_type == ScriptType.LONG
        assert created.status == ScriptStatus.DRAFT

    async def test_create_short_script(self, test_session, topic, channel, repo):
        script = Script(
            topic_id=topic.id,
            channel_id=channel.id,
            script_type=ScriptType.SHORT,
            content="Hook body CTA",
            word_count=3,
            estimated_duration=30,
        )
        created = await repo.create(script)
        assert created.script_type == ScriptType.SHORT


class TestScriptRepositoryGet:
    async def test_get_by_id(self, test_session, topic, channel, repo):
        script = await _make_script(test_session, topic, channel)
        fetched = await repo.get_by_id(script.id)
        assert fetched is not None
        assert fetched.id == script.id

    async def test_get_by_id_missing(self, test_session, repo):
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_get_by_id_or_raise_missing(self, test_session, repo):
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await repo.get_by_id_or_raise(uuid.uuid4())

    async def test_get_by_topic_id(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        await _make_script(test_session, topic, channel, script_type=ScriptType.SHORT)
        scripts = await repo.get_by_topic_id(topic.id)
        assert len(scripts) == 2

    async def test_get_by_channel(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel)
        await _make_script(test_session, topic, channel, script_type=ScriptType.SHORT)
        scripts = await repo.get_by_channel(channel.id)
        assert len(scripts) >= 2

    async def test_get_by_channel_filtered_type(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        await _make_script(test_session, topic, channel, script_type=ScriptType.SHORT)
        long_only = await repo.get_by_channel(channel.id, script_type=ScriptType.LONG)
        assert all(s.script_type == ScriptType.LONG for s in long_only)

    async def test_get_by_status(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, status=ScriptStatus.APPROVED)
        approved = await repo.get_by_status(ScriptStatus.APPROVED)
        assert all(s.status == ScriptStatus.APPROVED for s in approved)

    async def test_get_approved(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, status=ScriptStatus.APPROVED)
        results = await repo.get_approved()
        assert len(results) >= 1

    async def test_get_drafts(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, status=ScriptStatus.DRAFT)
        drafts = await repo.get_drafts()
        assert len(drafts) >= 1

    async def test_get_for_topic_and_type(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        found = await repo.get_for_topic_and_type(topic.id, ScriptType.LONG)
        assert found is not None
        assert found.script_type == ScriptType.LONG

    async def test_get_for_topic_and_type_missing(self, test_session, topic, repo):
        found = await repo.get_for_topic_and_type(topic.id, ScriptType.SHORT)
        assert found is None


class TestScriptRepositoryUpdate:
    async def test_set_status_approved(self, test_session, topic, channel, repo):
        script = await _make_script(test_session, topic, channel)
        updated = await repo.set_status(script.id, ScriptStatus.APPROVED)
        assert updated is not None
        assert updated.status == ScriptStatus.APPROVED

    async def test_set_status_missing(self, test_session, repo):
        result = await repo.set_status(uuid.uuid4(), ScriptStatus.APPROVED)
        assert result is None

    async def test_update_content(self, test_session, topic, channel, repo):
        script = await _make_script(test_session, topic, channel)
        updated = await repo.update(script, content="Updated content", word_count=2)
        assert updated.content == "Updated content"
        assert updated.word_count == 2


class TestScriptRepositoryCount:
    async def test_count_by_channel_and_type(self, test_session, topic, channel, repo):
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        count = await repo.count_by_channel_and_type(channel.id, ScriptType.LONG)
        assert count >= 2

    async def test_delete(self, test_session, topic, channel, repo):
        script = await _make_script(test_session, topic, channel)
        await repo.delete(script)
        assert await repo.get_by_id(script.id) is None