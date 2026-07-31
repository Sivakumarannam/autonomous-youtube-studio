from pathlib import Path
from typing import Union

from .local_storage import LocalStorage


class VideoStorage(LocalStorage):
    def __init__(self, base_path: Union[str, Path]):
        super().__init__(base_path)

    async def save_video(self, filename: str, data: bytes) -> Path:
        return await self.save_bytes(Path("video") / filename, data)

    async def get_video_path(self, filename: str) -> Path:
        return self.base_path / "video" / filename
