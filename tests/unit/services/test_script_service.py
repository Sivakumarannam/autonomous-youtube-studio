"""Unit tests for ScriptService."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.script import ScriptUpdate
from app.api.services.script_service import ScriptService
from app.core.exceptions import NotFoundError
from app.database.models.script import Script, ScriptStatus, ScriptType
from tests.conftest import create_test_channel, create_test_topic


async def _make_script(session, topic, channel, **kwargs) -> Script:
    script = Script(
        topic_id=topic.id,
        channel_id=channel.id,
        script_type=kwargs.get("script_type", ScriptType.LONG),
        content=kwargs.get("content", "Script content here"),
        word_count=kwargs.get("word_count", 100),
        estimated_duration=kwargs.get("estimated_duration", 480),
        status=kwargs.get("status", ScriptStatus.DRAFT),
    )
    session.add(script)
    await session.flush()
    await session.refresh(script)
    return script


@pytest_asyncio.fixture
async def channel(test_session):
    return await create_test_channel(test_session, name=f"ssvc-{uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def topic(test_session, channel):
    return await create_test_topic(test_session, channel.id, title=f"Script SVC Topic {uuid.uuid4().hex[:6]}")


@pytest_asyncio.fixture
async def service(test_session: AsyncSession) -> ScriptService:
    return ScriptService(test_session)


class TestScriptServiceGet:
    async def test_get_by_id(self, test_session, topic, channel, service):
        script = await _make_script(test_session, topic, channel)
        fetched = await service.get_by_id(script.id)
        assert fetched.id == script.id

    async def test_get_by_id_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_get_by_channel(self, test_session, topic, channel, service):
        await _make_script(test_session, topic, channel)
        scripts, total = await service.get_by_channel(channel.id)
        assert len(scripts) >= 1

    async def test_get_by_channel_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_channel(uuid.uuid4())

    async def test_get_by_channel_filtered_type(self, test_session, topic, channel, service):
        await _make_script(test_session, topic, channel, script_type=ScriptType.LONG)
        await _make_script(test_session, topic, channel, script_type=ScriptType.SHORT)
        scripts, _ = await service.get_by_channel(channel.id, script_type=ScriptType.LONG)
        assert all(s.script_type == ScriptType.LONG for s in scripts)

    async def test_get_by_topic(self, test_session, topic, channel, service):
        await _make_script(test_session, topic, channel)
        scripts = await service.get_by_topic(topic.id)
        assert len(scripts) >= 1

    async def test_get_all(self, test_session, topic, channel, service):
        await _make_script(test_session, topic, channel)
        scripts, total = await service.get_all()
        assert len(scripts) >= 1

    async def test_get_all_filtered_status(self, test_session, topic, channel, service):
        await _make_script(test_session, topic, channel, status=ScriptStatus.APPROVED)
        scripts, _ = await service.get_all(status=ScriptStatus.APPROVED)
        assert all(s.status == ScriptStatus.APPROVED for s in scripts)


class TestScriptServiceUpdate:
    async def test_update_script(self, test_session, topic, channel, service):
        script = await _make_script(test_session, topic, channel)
        updated = await service.update(script.id, ScriptUpdate(seo_title="New SEO Title"))
        assert updated.seo_title == "New SEO Title"

    async def test_update_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.update(uuid.uuid4(), ScriptUpdate(seo_title="X"))

    async def test_set_status_approved(self, test_session, topic, channel, service):
        script = await _make_script(test_session, topic, channel)
        updated = await service.set_status(script.id, ScriptStatus.APPROVED)
        assert updated.status == ScriptStatus.APPROVED

    async def test_set_status_rejected(self, test_session, topic, channel, service):
        script = await _make_script(test_session, topic, channel)
        updated = await service.set_status(script.id, ScriptStatus.REJECTED)
        assert updated.status == ScriptStatus.REJECTED

    async def test_set_status_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.set_status(uuid.uuid4(), ScriptStatus.APPROVED)


class TestScriptServiceDelete:
    async def test_delete_script(self, test_session, topic, channel, service):
        script = await _make_script(test_session, topic, channel)
        await service.delete(script.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(script.id)

    async def test_delete_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.delete(uuid.uuid4())