import uuid

import pytest

from app.api.services.voice_service import VoiceService
from app.database.models.script import (
    Script,
    ScriptStatus,
    ScriptType,
)
from app.database.models.voice import (
    VoiceProvider,
)


@pytest.mark.asyncio
async def test_generate_voice(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="This is a voice generation test.",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    voice = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
        language="en",
    )

    assert voice is not None
    assert voice.script_id == script.id
    assert voice.provider == VoiceProvider.MOCK


@pytest.mark.asyncio
async def test_generate_voice_returns_existing(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Existing voice test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    first = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    second = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    assert first.id == second.id


@pytest.mark.asyncio
async def test_regenerate_voice(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Regenerate voice test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    original = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    regenerated = await service.regenerate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    assert regenerated is not None
    assert regenerated.script_id == script.id
    assert regenerated.id != original.id


@pytest.mark.asyncio
async def test_get_voice(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Get voice test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    voice = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    fetched = await service.get_voice(voice.id)

    assert fetched.id == voice.id


@pytest.mark.asyncio
async def test_get_by_script(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Script lookup",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    voice = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    fetched = await service.get_by_script(script.id)

    assert fetched.id == voice.id


@pytest.mark.asyncio
async def test_list_completed(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Completed voice",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    voices = await service.list_completed()

    assert len(voices) >= 1


@pytest.mark.asyncio
async def test_delete_voice(test_session):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Delete voice",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    service = VoiceService(test_session)

    voice = await service.generate_voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK.value,
    )

    await service.delete_voice(voice.id)

    with pytest.raises(Exception):
        await service.get_voice(voice.id)