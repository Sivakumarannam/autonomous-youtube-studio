import pytest
from unittest.mock import AsyncMock, Mock

from app.integrations.youtube.client import YouTubeApiClient
from app.integrations.youtube.uploader import YouTubeUploader


@pytest.mark.asyncio
async def test_upload_thumbnail_posts_binary_content(tmp_path):
    auth = Mock()
    auth.get_access_token = AsyncMock(return_value="token")
    client = YouTubeApiClient(auth_manager=auth)
    client._headers = AsyncMock(return_value={"Authorization": "Bearer token"})
    client.session = AsyncMock()
    client.session.post.return_value.raise_for_status.return_value = None
    thumbnail = tmp_path / "thumb.png"
    thumbnail.write_bytes(b"pngdata")

    uploader = YouTubeUploader(api_client=client)
    await uploader.upload_thumbnail("video123", str(thumbnail))
    client.session.post.assert_awaited_once()
