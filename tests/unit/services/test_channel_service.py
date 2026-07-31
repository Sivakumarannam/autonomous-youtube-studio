"""Unit tests for ChannelService."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.channel import ChannelCreate, ChannelUpdate
from app.api.services.channel_service import ChannelService
from app.core.exceptions import NotFoundError, ValidationError
from app.database.models.channel import ChannelStatus, ContentType, AspectRatio
from tests.conftest import create_test_channel


def _unique_name(prefix: str = "svc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def service(test_session: AsyncSession) -> ChannelService:
    return ChannelService(test_session)


# ──────────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelServiceCreate:
    async def test_create_channel_success(self, test_session, service):
        data = ChannelCreate(name=_unique_name(), niche="technology")
        channel = await service.create(data)
        assert channel.id is not None
        assert channel.niche == "technology"

    async def test_create_channel_stores_all_fields(self, test_session, service):
        name = _unique_name("full")
        data = ChannelCreate(
            name=name,
            description="Full channel description",
            niche="devops",
            language="de",
            content_type=ContentType.SHORTS,
            aspect_ratio=AspectRatio.SHORTS,
            target_duration=30,
            upload_schedule="hourly",
            youtube_channel_id="UC_test_channel_id",
        )
        channel = await service.create(data)
        assert channel.name == name
        assert channel.description == "Full channel description"
        assert channel.niche == "devops"
        assert channel.language == "de"
        assert channel.content_type == ContentType.SHORTS
        assert channel.youtube_channel_id == "UC_test_channel_id"

    async def test_create_channel_default_status_is_active(self, test_session, service):
        channel = await service.create(ChannelCreate(name=_unique_name(), niche="tech"))
        assert channel.status == ChannelStatus.ACTIVE

    async def test_create_duplicate_name_raises_validation_error(self, test_session, service):
        name = _unique_name("dup")
        await service.create(ChannelCreate(name=name, niche="tech"))
        with pytest.raises(ValidationError, match="already exists"):
            await service.create(ChannelCreate(name=name, niche="other"))

    async def test_create_different_niches_same_name_raises(self, test_session, service):
        name = _unique_name("dupniche")
        await service.create(ChannelCreate(name=name, niche="python"))
        with pytest.raises(ValidationError):
            await service.create(ChannelCreate(name=name, niche="devops"))


# ──────────────────────────────────────────────────────────────────────────────
# Get
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelServiceGet:
    async def test_get_by_id_found(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("get"))
        fetched = await service.get_by_id(ch.id)
        assert fetched.id == ch.id

    async def test_get_by_id_not_found(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_get_all_returns_channels(self, test_session, service):
        await create_test_channel(test_session, name=_unique_name("all1"))
        await create_test_channel(test_session, name=_unique_name("all2"))
        channels, total = await service.get_all()
        assert len(channels) >= 2
        assert total >= 2

    async def test_get_all_pagination_limit(self, test_session, service):
        for i in range(5):
            await create_test_channel(test_session, name=_unique_name(f"pg{i}"))
        channels, _ = await service.get_all(limit=2)
        assert len(channels) <= 2

    async def test_get_all_pagination_offset(self, test_session, service):
        for i in range(4):
            await create_test_channel(test_session, name=_unique_name(f"off{i}"))
        channels_p1, _ = await service.get_all(limit=2, offset=0)
        channels_p2, _ = await service.get_all(limit=2, offset=2)
        ids_p1 = {c.id for c in channels_p1}
        ids_p2 = {c.id for c in channels_p2}
        assert ids_p1.isdisjoint(ids_p2)

    async def test_get_active_returns_only_active(self, test_session, service):
        active_ch = await create_test_channel(test_session, name=_unique_name("act"))
        paused_ch = await create_test_channel(test_session, name=_unique_name("pau"))
        await service.set_status(paused_ch.id, ChannelStatus.PAUSED)

        active_list = await service.get_active()
        active_ids = [c.id for c in active_list]
        assert active_ch.id in active_ids
        assert paused_ch.id not in active_ids


# ──────────────────────────────────────────────────────────────────────────────
# Update
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelServiceUpdate:
    async def test_update_niche(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("upd"))
        updated = await service.update(ch.id, ChannelUpdate(niche="cybersecurity"))
        assert updated.niche == "cybersecurity"

    async def test_update_language(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("lang"))
        updated = await service.update(ch.id, ChannelUpdate(language="es"))
        assert updated.language == "es"

    async def test_update_target_duration(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("dur"))
        updated = await service.update(ch.id, ChannelUpdate(target_duration=300))
        assert updated.target_duration == 300

    async def test_update_name_to_new_unique_name(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("rn"))
        new_name = _unique_name("renamed")
        updated = await service.update(ch.id, ChannelUpdate(name=new_name))
        assert updated.name == new_name

    async def test_update_name_to_existing_name_raises(self, test_session, service):
        ch1 = await create_test_channel(test_session, name=_unique_name("n1"))
        ch2 = await create_test_channel(test_session, name=_unique_name("n2"))
        with pytest.raises(ValidationError, match="already taken"):
            await service.update(ch2.id, ChannelUpdate(name=ch1.name))

    async def test_update_name_to_own_name_is_allowed(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("self"))
        # Updating to the same name should not raise
        updated = await service.update(ch.id, ChannelUpdate(name=ch.name))
        assert updated.name == ch.name

    async def test_update_not_found_raises(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.update(uuid.uuid4(), ChannelUpdate(niche="tech"))

    async def test_update_empty_body_changes_nothing(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("noop"))
        original_niche = ch.niche
        updated = await service.update(ch.id, ChannelUpdate())
        assert updated.niche == original_niche


# ──────────────────────────────────────────────────────────────────────────────
# Status management
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelServiceStatus:
    async def test_set_status_paused(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("sp"))
        updated = await service.set_status(ch.id, ChannelStatus.PAUSED)
        assert updated.status == ChannelStatus.PAUSED

    async def test_set_status_active(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("sa"))
        await service.set_status(ch.id, ChannelStatus.PAUSED)
        updated = await service.set_status(ch.id, ChannelStatus.ACTIVE)
        assert updated.status == ChannelStatus.ACTIVE

    async def test_set_status_inactive(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("si"))
        updated = await service.set_status(ch.id, ChannelStatus.INACTIVE)
        assert updated.status == ChannelStatus.INACTIVE

    async def test_set_status_not_found_raises(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.set_status(uuid.uuid4(), ChannelStatus.PAUSED)


# ──────────────────────────────────────────────────────────────────────────────
# Delete
# ──────────────────────────────────────────────────────────────────────────────

class TestChannelServiceDelete:
    async def test_delete_channel(self, test_session, service):
        ch = await create_test_channel(test_session, name=_unique_name("del"))
        await service.delete(ch.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(ch.id)

    async def test_delete_not_found_raises(self, test_session, service):
        with pytest.raises(NotFoundError):
            await service.delete(uuid.uuid4())

    async def test_delete_then_create_same_name_works(self, test_session, service):
        """After deletion the name should be reusable."""
        name = _unique_name("reuse")
        ch = await service.create(ChannelCreate(name=name, niche="tech"))
        await service.delete(ch.id)
        new_ch = await service.create(ChannelCreate(name=name, niche="tech"))
        assert new_ch.id != ch.id
        assert new_ch.name == name