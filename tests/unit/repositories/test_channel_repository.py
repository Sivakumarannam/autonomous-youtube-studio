"""Unit tests for ChannelRepository."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel, ChannelStatus, ContentType, AspectRatio
from app.database.repositories.channel_repository import ChannelRepository
from tests.conftest import create_test_channel


@pytest_asyncio.fixture
async def repo(test_session: AsyncSession) -> ChannelRepository:
    return ChannelRepository(test_session)


def _unique_name(prefix: str = "ch") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ──────────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelRepositoryCreate:
    async def test_create_channel(self, test_session, repo):
        ch = Channel(name=_unique_name(), niche="technology")
        created = await repo.create(ch)
        assert created.id is not None
        assert created.status == ChannelStatus.ACTIVE

    async def test_create_channel_sets_defaults(self, test_session, repo):
        ch = Channel(name=_unique_name(), niche="python")
        created = await repo.create(ch)
        assert created.language == "en"
        assert created.target_duration == 600
        assert created.upload_schedule == "daily"

    async def test_create_channel_with_all_fields(self, test_session, repo):
        name = _unique_name("full")
        ch = Channel(
            name=name,
            description="A full-featured channel",
            niche="devops",
            language="fr",
            content_type=ContentType.SHORTS,
            aspect_ratio=AspectRatio.SHORTS,
            target_duration=30,
            upload_schedule="hourly",
            youtube_channel_id="UC123456",
            status=ChannelStatus.ACTIVE,
        )
        created = await repo.create(ch)
        assert created.name == name
        assert created.niche == "devops"
        assert created.language == "fr"
        assert created.content_type == ContentType.SHORTS
        assert created.youtube_channel_id == "UC123456"

    async def test_create_multiple_channels(self, test_session, repo):
        for i in range(3):
            await repo.create(Channel(name=_unique_name(f"multi{i}"), niche="tech"))
        total = await repo.count()
        assert total >= 3


# ──────────────────────────────────────────────────────────────────────────────
# Get
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelRepositoryGet:
    async def test_get_by_id(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name())
        fetched = await repo.get_by_id(ch.id)
        assert fetched is not None
        assert fetched.id == ch.id

    async def test_get_by_id_missing_returns_none(self, test_session, repo):
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_id_or_raise_missing(self, test_session, repo):
        from app.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await repo.get_by_id_or_raise(uuid.uuid4())

    async def test_get_by_name_found(self, test_session, repo):
        name = _unique_name("named")
        await create_test_channel(test_session, name=name)
        found = await repo.get_by_name(name)
        assert found is not None
        assert found.name == name

    async def test_get_by_name_not_found(self, test_session, repo):
        result = await repo.get_by_name("absolutely-does-not-exist-xyz-123")
        assert result is None

    async def test_get_active_returns_only_active(self, test_session, repo):
        active = await create_test_channel(test_session, name=_unique_name("act"))
        paused = await create_test_channel(test_session, name=_unique_name("pau"))
        await repo.update(paused, status=ChannelStatus.PAUSED)

        active_channels = await repo.get_active()
        ids = [c.id for c in active_channels]
        assert active.id in ids
        assert paused.id not in ids

    async def test_get_active_excludes_inactive(self, test_session, repo):
        inactive = await create_test_channel(test_session, name=_unique_name("inact"))
        await repo.update(inactive, status=ChannelStatus.INACTIVE)

        active_channels = await repo.get_active()
        ids = [c.id for c in active_channels]
        assert inactive.id not in ids

    async def test_get_all(self, test_session, repo):
        await create_test_channel(test_session, name=_unique_name("all1"))
        await create_test_channel(test_session, name=_unique_name("all2"))
        channels = await repo.get_all(limit=100)
        assert len(channels) >= 2

    async def test_get_all_with_limit(self, test_session, repo):
        for i in range(5):
            await create_test_channel(test_session, name=_unique_name(f"lim{i}"))
        channels = await repo.get_all(limit=2)
        assert len(channels) <= 2

    async def test_get_by_youtube_id(self, test_session, repo):
        yt_id = f"UC{uuid.uuid4().hex[:10]}"
        ch = Channel(name=_unique_name("yt"), niche="tech", youtube_channel_id=yt_id)
        await repo.create(ch)
        found = await repo.get_by_youtube_id(yt_id)
        assert found is not None
        assert found.youtube_channel_id == yt_id

    async def test_get_by_youtube_id_not_found(self, test_session, repo):
        result = await repo.get_by_youtube_id("UC_nonexistent_channel_id")
        assert result is None

    async def test_get_by_niche(self, test_session, repo):
        ch = Channel(name=_unique_name("niche"), niche="machine-learning-ai")
        await repo.create(ch)
        results = await repo.get_by_niche("machine-learning")
        assert any(c.niche == "machine-learning-ai" for c in results)

    async def test_get_by_niche_case_insensitive(self, test_session, repo):
        ch = Channel(name=_unique_name("case"), niche="Python-Development")
        await repo.create(ch)
        results = await repo.get_by_niche("python")
        assert any(c.id == ch.id for c in results)


# ──────────────────────────────────────────────────────────────────────────────
# Update
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelRepositoryUpdate:
    async def test_update_name(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("upd"))
        new_name = _unique_name("new")
        updated = await repo.update(ch, name=new_name)
        assert updated.name == new_name

    async def test_update_niche(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("nch"))
        updated = await repo.update(ch, niche="cybersecurity")
        assert updated.niche == "cybersecurity"

    async def test_update_language(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("lng"))
        updated = await repo.update(ch, language="de")
        assert updated.language == "de"

    async def test_update_youtube_channel_id(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("uchid"))
        yt_id = f"UC{uuid.uuid4().hex[:10]}"
        updated = await repo.update(ch, youtube_channel_id=yt_id)
        assert updated.youtube_channel_id == yt_id

    async def test_set_status_paused(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("pause"))
        updated = await repo.set_status(ch.id, ChannelStatus.PAUSED)
        assert updated is not None
        assert updated.status == ChannelStatus.PAUSED

    async def test_set_status_active(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("react"))
        await repo.update(ch, status=ChannelStatus.PAUSED)
        updated = await repo.set_status(ch.id, ChannelStatus.ACTIVE)
        assert updated is not None
        assert updated.status == ChannelStatus.ACTIVE

    async def test_set_status_missing_id_returns_none(self, test_session, repo):
        result = await repo.set_status(uuid.uuid4(), ChannelStatus.PAUSED)
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Delete
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelRepositoryDelete:
    async def test_delete_channel(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("del"))
        await repo.delete(ch)
        assert await repo.get_by_id(ch.id) is None

    async def test_delete_by_id(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("delid"))
        deleted = await repo.delete_by_id(ch.id)
        assert deleted is True
        assert await repo.get_by_id(ch.id) is None

    async def test_delete_by_id_missing_returns_false(self, test_session, repo):
        deleted = await repo.delete_by_id(uuid.uuid4())
        assert deleted is False


# ──────────────────────────────────────────────────────────────────────────────
# Exists / Count
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelRepositoryExistsCount:
    async def test_exists_true(self, test_session, repo):
        ch = await create_test_channel(test_session, name=_unique_name("ex"))
        assert await repo.exists(ch.id) is True

    async def test_exists_false(self, test_session, repo):
        assert await repo.exists(uuid.uuid4()) is False

    async def test_count_increases_on_create(self, test_session, repo):
        before = await repo.count()
        await create_test_channel(test_session, name=_unique_name("cnt1"))
        await create_test_channel(test_session, name=_unique_name("cnt2"))
        after = await repo.count()
        assert after == before + 2