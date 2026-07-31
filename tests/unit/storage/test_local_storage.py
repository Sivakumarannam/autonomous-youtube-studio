import pytest

from app.storage.audio_storage import AudioStorage
from app.storage.local_storage import LocalStorage
from app.storage.thumbnail_storage import ThumbnailStorage
from app.storage.video_storage import VideoStorage


@pytest.mark.asyncio
async def test_local_storage_save_read_delete(tmp_path):
    storage = LocalStorage(tmp_path)
    saved_path = await storage.save_bytes("test.bin", b"abc")

    assert saved_path.exists()
    assert await storage.read_bytes("test.bin") == b"abc"
    assert await storage.exists("test.bin")

    await storage.delete("test.bin")
    assert not await storage.exists("test.bin")


@pytest.mark.asyncio
async def test_specialized_storages_create_subdirectories(tmp_path):
    audio = AudioStorage(tmp_path)
    video = VideoStorage(tmp_path)
    thumbnail = ThumbnailStorage(tmp_path)

    await audio.save_audio("song.wav", b"wave")
    await video.save_video("movie.mp4", b"video")
    await thumbnail.save_thumbnail("cover.png", b"png")

    assert (tmp_path / "audio" / "song.wav").exists()
    assert (tmp_path / "video" / "movie.mp4").exists()
    assert (tmp_path / "thumbnails" / "cover.png").exists()
