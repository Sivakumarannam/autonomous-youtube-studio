from typing import Literal

from .edge_tts_provider import EdgeTTSProvider
from .elevenlabs_provider import ElevenLabsProvider

TTS_PROVIDER = Literal["edge", "elevenlabs"]


class TTSProviderFactory:
    _providers = {
        "edge": EdgeTTSProvider,
        "elevenlabs": ElevenLabsProvider,
    }

    @classmethod
    def create(cls, provider_name: str, **kwargs):
        provider_name = provider_name.lower()
        provider_cls = cls._providers.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unsupported TTS provider: {provider_name}")
        return provider_cls(**kwargs)
