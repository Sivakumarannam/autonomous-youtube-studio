import asyncio
from pathlib import Path

import pytest

from app.integrations.tts.edge_tts_provider import EdgeTTSProvider


@pytest.mark.asyncio
async def test_edge_tts_provider_generates_file(tmp_path):
    provider = EdgeTTSProvider()
    output = tmp_path / "speech.wav"
    result = await provider.synthesize_speech("hello world", str(output))

    assert Path(result).exists()
    assert output.stat().st_size > 0
