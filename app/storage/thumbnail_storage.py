from pathlib import Path
from typing import Union

from .local_storage import LocalStorage


class ThumbnailStorage(LocalStorage):
    def __init__(self, base_path: Union[str, Path]):
        super().__init__(base_path)

    async def save_thumbnail(self, filename: str, data: bytes) -> Path:
        return await self.save_bytes(Path("thumbnails") / filename, data)

    async def get_thumbnail_path(self, filename: str) -> Path:
        return self.base_path / "thumbnails" / filename
