import pytest
from unittest.mock import AsyncMock, Mock

from app.integrations.youtube.auth import YouTubeAuthManager


@pytest.mark.asyncio
async def test_youtube_auth_manager_refreshes_token():
    response = Mock()
    response.json.return_value = {"access_token": "abc123", "expires_in": 3600}
    response.raise_for_status.return_value = None

    http_client = AsyncMock()
    http_client.post.return_value = response

    auth = YouTubeAuthManager(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        http_client=http_client,
    )

    token = await auth.refresh_access_token()
    assert token == "abc123"
    assert await auth.get_access_token() == "abc123"
    http_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_youtube_auth_manager_close_closes_client():
    http_client = AsyncMock()
    auth = YouTubeAuthManager("client", "secret", "refresh", http_client=http_client)

    await auth.close()
    http_client.aclose.assert_awaited_once()
