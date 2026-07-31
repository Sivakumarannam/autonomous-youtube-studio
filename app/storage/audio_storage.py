from pathlib import Path
from typing import Union

from .local_storage import LocalStorage


class AudioStorage(LocalStorage):
    def __init__(self, base_path: Union[str, Path]):
        super().__init__(base_path)

    async def save_audio(self, filename: str, data: bytes) -> Path:
        return await self.save_bytes(Path("audio") / filename, data)

    async def get_audio_path(self, filename: str) -> Path:
        return self.base_path / "audio" / filename
