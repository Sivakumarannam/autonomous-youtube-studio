import asyncio
import os
import time
from pathlib import Path
from typing import Optional, Union


async def cleanup_old_files(
    path: Union[str, Path],
    keep_seconds: int,
    exclude: Optional[set] = None,
) -> int:
    directory = Path(path)
    cutoff = time.time() - keep_seconds
    if not directory.exists() or not directory.is_dir():
        return 0
    return await asyncio.to_thread(_delete_old_files, directory, cutoff, exclude or set())


def _delete_old_files(directory: Path, cutoff: float, exclude: set) -> int:
    removed = 0
    for item in directory.rglob("*"):
        if item.is_file() and item.stat().st_mtime < cutoff:
            if str(item.resolve()) in exclude:
                continue
            item.unlink()
            removed += 1
    return removed


async def cleanup_empty_directories(path: Union[str, Path]) -> int:
    directory = Path(path)
    if not directory.exists() or not directory.is_dir():
        return 0
    return await asyncio.to_thread(_delete_empty_dirs, directory)


def _delete_empty_dirs(directory: Path) -> int:
    removed = 0
    for dir_path in sorted(directory.rglob("*"), key=lambda p: len(str(p)), reverse=True):
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            dir_path.rmdir()
            removed += 1
    return removed
