import asyncio
from pathlib import Path

import pytest

from app.utils.file_utils import ensure_directory, read_text_file, safe_remove, write_text_file


def test_ensure_directory_creates_folder(tmp_path):
    folder = tmp_path / "nested"
    result = ensure_directory(folder)
    assert result.exists() and result.is_dir()

@pytest.mark.asyncio
async def test_write_and_read_text_file(tmp_path):
    path = tmp_path / "notes" / "test.txt"
    await write_text_file(path, "hello world")
    text = await read_text_file(path)
    assert text == "hello world"


def test_safe_remove_deletes_file(tmp_path):
    file_path = tmp_path / "delete.txt"
    file_path.write_text("bye")
    safe_remove(file_path)
    assert not file_path.exists()
