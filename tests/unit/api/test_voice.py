import uuid

import pytest
from httpx import AsyncClient

from app.database.models.script import (
    Script,
    ScriptStatus,
    ScriptType,
)
from app.database.models.voice import VoiceProvider


@pytest.mark.asyncio
async def test_generate_voice_endpoint(
    client: AsyncClient,
    test_session,
):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="API voice generation test",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    response = await client.post(
        "/api/v1/voice/generate",
        json={
            "script_id": str(script.id),
            "provider": VoiceProvider.MOCK.value,
            "language": "en",
            "speed": 1.0,
            "pitch": 0.0,
            "volume": 1.0,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["success"] is True
    assert body["voice"]["script_id"] == str(script.id)


@pytest.mark.asyncio
async def test_get_voice_by_script_endpoint(
    client: AsyncClient,
    test_session,
):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Lookup voice",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    await client.post(
        "/api/v1/voice/generate",
        json={
            "script_id": str(script.id),
            "provider": VoiceProvider.MOCK.value,
            "language": "en",
        },
    )

    response = await client.get(
        f"/api/v1/voice/script/{script.id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["script_id"] == str(script.id)


@pytest.mark.asyncio
async def test_list_completed_voices(
    client: AsyncClient,
):
    response = await client.get(
        "/api/v1/voice/?limit=10"
    )

    assert response.status_code == 200

    body = response.json()

    assert "items" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_regenerate_voice_endpoint(
    client: AsyncClient,
    test_session,
):
    script = Script(
        id=uuid.uuid4(),
        topic_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        script_type=ScriptType.LONG,
        content="Regenerate voice",
        status=ScriptStatus.APPROVED,
    )

    test_session.add(script)
    await test_session.commit()

    await client.post(
        "/api/v1/voice/generate",
        json={
            "script_id": str(script.id),
            "provider": VoiceProvider.MOCK.value,
        },
    )

    response = await client.post(
        f"/api/v1/voice/{script.id}/regenerate"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True


@pytest.mark.asyncio
async def test_delete_voice_endpoint(
    client: AsyncClient,
    test_session,
):
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

    create = await client.post(
        "/api/v1/voice/generate",
        json={
            "script_id": str(script.id),
            "provider": VoiceProvider.MOCK.value,
        },
    )

    voice_id = create.json()["voice"]["id"]

    response = await client.delete(
        f"/api/v1/voice/{voice_id}"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True


@pytest.mark.asyncio
async def test_generate_voice_invalid_script(
    client: AsyncClient,
):
    response = await client.post(
        "/api/v1/voice/generate",
        json={
            "script_id": str(uuid.uuid4()),
            "provider": VoiceProvider.MOCK.value,
        },
    )

    assert response.status_code == 404