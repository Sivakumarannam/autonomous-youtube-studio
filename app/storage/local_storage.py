import asyncio
from pathlib import Path
from typing import Any, Optional, Union


class LocalStorage:
    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_bytes(self, relative_path: Union[str, Path], data: bytes) -> Path:
        file_path = self.base_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._write_bytes, file_path, data)
        return file_path

    async def read_bytes(self, relative_path: Union[str, Path]) -> bytes:
        file_path = self.base_path / relative_path
        return await asyncio.to_thread(self._read_bytes, file_path)

    async def exists(self, relative_path: Union[str, Path]) -> bool:
        file_path = self.base_path / relative_path
        return await asyncio.to_thread(file_path.exists)

    async def delete(self, relative_path: Union[str, Path]) -> None:
        file_path = self.base_path / relative_path
        await asyncio.to_thread(self._remove_file, file_path)

    def _write_bytes(self, file_path: Path, data: bytes) -> None:
        with open(file_path, "wb") as file_handle:
            file_handle.write(data)

    def _read_bytes(self, file_path: Path) -> bytes:
        with open(file_path, "rb") as file_handle:
            return file_handle.read()

    def _remove_file(self, file_path: Path) -> None:
        if file_path.exists():
            file_path.unlink()
