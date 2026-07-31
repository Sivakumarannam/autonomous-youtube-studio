import pytest

from app.integrations.tts.factory import TTSProviderFactory
from app.integrations.tts.edge_tts_provider import EdgeTTSProvider
from app.integrations.tts.elevenlabs_provider import ElevenLabsProvider


def test_tts_factory_returns_edge_provider():
    provider = TTSProviderFactory.create("edge")
    assert isinstance(provider, EdgeTTSProvider)


def test_tts_factory_returns_elevenlabs_provider():
    provider = TTSProviderFactory.create("elevenlabs")
    assert isinstance(provider, ElevenLabsProvider)


def test_tts_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        TTSProviderFactory.create("unknown")
