import os
import time
from pathlib import Path

import pytest

from app.storage.cleanup import cleanup_empty_directories, cleanup_old_files


@pytest.mark.asyncio
async def test_cleanup_old_files_removes_stale_files(tmp_path):
    file_path = tmp_path / "old.txt"
    file_path.write_text("old")
    now = time.time()
    os.utime(file_path, (now - 100, now - 100))

    removed = await cleanup_old_files(tmp_path, keep_seconds=1)
    assert removed == 1
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_cleanup_empty_directories_removes_empty_dirs(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    removed = await cleanup_empty_directories(tmp_path)
    assert removed == 2
    assert not nested.exists()
