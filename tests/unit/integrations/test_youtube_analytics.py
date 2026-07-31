import pytest
from unittest.mock import AsyncMock, MagicMock

from app.integrations.youtube.analytics import YouTubeAnalyticsService
from app.integrations.youtube.auth import YouTubeAuthManager


@pytest.mark.asyncio
async def test_fetch_video_analytics_builds_query():
    auth = YouTubeAuthManager("client", "secret", "refresh")
    auth.get_access_token = AsyncMock(return_value="tok")
    service = YouTubeAnalyticsService(auth_manager=auth)
    service.session = AsyncMock()
    response = MagicMock()
    response.json.return_value = {"rows": []}
    response.raise_for_status.return_value = None
    service.session.get.return_value = response

    result = await service.fetch_video_analytics(
        video_id="video123",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert result == {"rows": []}
    service.session.get.assert_awaited_once()
