import pytest
from pathlib import Path

from app.integrations.tts.elevenlabs_provider import ElevenLabsProvider


@pytest.mark.asyncio
async def test_elevenlabs_provider_generates_file(tmp_path):
    provider = ElevenLabsProvider()
    output = tmp_path / "speech.wav"
    result = await provider.synthesize_speech("test synthesis", str(output))

    assert Path(result).exists()
    assert output.stat().st_size > 0
