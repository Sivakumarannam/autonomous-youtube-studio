import asyncio
from pathlib import Path
from typing import Union


def ensure_directory(path: Union[str, Path]) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def read_text_file(path: Union[str, Path], encoding: str = "utf-8") -> str:
    return await asyncio.to_thread(_read_file, Path(path), encoding)


async def write_text_file(path: Union[str, Path], content: str, encoding: str = "utf-8") -> Path:
    return await asyncio.to_thread(_write_file, Path(path), content, encoding)


def _read_file(path: Path, encoding: str) -> str:
    with open(path, "r", encoding=encoding) as handle:
        return handle.read()


def _write_file(path: Path, content: str, encoding: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=encoding) as handle:
        handle.write(content)
    return path


def safe_remove(path: Union[str, Path]) -> None:
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink()
