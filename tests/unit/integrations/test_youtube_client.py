import pytest
from unittest.mock import AsyncMock

from app.integrations.youtube.auth import YouTubeAuthManager
from app.integrations.youtube.client import YouTubeApiClient


@pytest.mark.asyncio
async def test_get_video_details_calls_api():
    auth = YouTubeAuthManager("client", "secret", "refresh")
    auth.get_access_token = AsyncMock(return_value="token")

    client = YouTubeApiClient(auth_manager=auth)
    client.session = AsyncMock()
    client.session.request.return_value.json.return_value = {"items": []}
    client.session.request.return_value.raise_for_status.return_value = None

    result = await client.get_video_details("video123")
    assert result == {"items": []}
    client.session.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_video_metadata_builds_payload():
    auth = YouTubeAuthManager("client", "secret", "refresh")
    client = YouTubeApiClient(auth_manager=auth)

    metadata = await client.create_video_metadata(
        title="Test",
        description="Desc",
        tags=["tag1", "tag2"],
        category_id="24",
        privacy_status="private",
    )

    assert metadata["snippet"]["title"] == "Test"
    assert metadata["snippet"]["categoryId"] == "24"
    assert metadata["status"]["privacyStatus"] == "private"
