import uuid

import pytest

from app.database.models.script import (
    Script,
    ScriptStatus,
    ScriptType,
)
from app.database.models.voice import (
    Voice,
    VoiceProvider,
    VoiceStatus,
)
from app.database.repositories.voice_repository import VoiceRepository


@pytest.mark.asyncio
async def test_create_and_get_voice(test_session):
    repository = VoiceRepository(test_session)

    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Test script",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    voice = Voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK,
        status=VoiceStatus.COMPLETE,
        language="en",
        audio_path="storage/audio/test.mp3",
        duration=12.5,
        word_count=120,
        file_size=1024,
        sample_rate=22050,
        bitrate="64k",
    )

    created = await repository.create(voice)

    assert created.id is not None

    fetched = await repository.get_by_script_id(script.id)

    assert fetched is not None
    assert fetched.script_id == script.id
    assert fetched.audio_path.endswith(".mp3")


@pytest.mark.asyncio
async def test_get_completed(test_session):
    repository = VoiceRepository(test_session)

    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Repository Test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    voice = Voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK,
        status=VoiceStatus.COMPLETE,
        language="en",
        audio_path="voice.mp3",
        duration=15,
        word_count=150,
        file_size=2000,
        sample_rate=22050,
        bitrate="64k",
    )

    await repository.create(voice)

    voices = await repository.get_completed()

    assert len(voices) >= 1
    assert voices[0].status == VoiceStatus.COMPLETE


@pytest.mark.asyncio
async def test_update_voice(test_session):
    repository = VoiceRepository(test_session)

    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Update Test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    voice = Voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK,
        status=VoiceStatus.PENDING,
        language="en",
        duration=0,
        word_count=0,
        file_size=0,
        sample_rate=22050,
        bitrate="64k",
    )

    voice = await repository.create(voice)

    updated = await repository.update_voice(
        voice,
        status=VoiceStatus.COMPLETE,
        audio_path="new_audio.mp3",
        duration=25.8,
    )

    assert updated.status == VoiceStatus.COMPLETE
    assert updated.audio_path == "new_audio.mp3"
    assert updated.duration == 25.8


@pytest.mark.asyncio
async def test_delete_voice(test_session):
    repository = VoiceRepository(test_session)

    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Delete Test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    voice = Voice(
        script_id=script.id,
        provider=VoiceProvider.MOCK,
        status=VoiceStatus.COMPLETE,
        language="en",
        duration=10,
        word_count=100,
        file_size=1000,
        sample_rate=22050,
        bitrate="64k",
    )

    voice = await repository.create(voice)

    await repository.delete_voice(voice)

    result = await repository.get_by_script_id(script.id)

    assert result is None