from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.storyboard_agent.agents import StoryboardAgent
from app.agents.storyboard_agent.models import (
    StoryboardRequest,
    StoryboardResponse,
    StoryboardScene,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_service():
    service = MagicMock()
    service.generate = AsyncMock()
    return service


@pytest.fixture
def agent(mock_service):
    agent = StoryboardAgent()
    agent.service = mock_service
    return agent


async def test_run_storyboard(agent, mock_service):
    request = StoryboardRequest(
        script="This is a test script."
    )

    response = StoryboardResponse(
        scenes=[
            StoryboardScene(
                scene_number=1,
                timestamp="00:00-00:08",
                narration="Opening narration",
                visual="Village sunrise",
                image_prompt="Beautiful sunrise over a village",
                duration_seconds=8,
            ),
            StoryboardScene(
                scene_number=2,
                timestamp="00:08-00:15",
                narration="Second narration",
                visual="Marketplace",
                image_prompt="Busy village marketplace",
                duration_seconds=7,
            ),
        ]
    )

    mock_service.generate.return_value = response

    result = await agent.run(request)

    mock_service.generate.assert_awaited_once_with(request)

    assert result == response


async def test_run_returns_storyboard_response(agent, mock_service):
    request = StoryboardRequest(
        script="Another script."
    )

    response = StoryboardResponse(
        scenes=[]
    )

    mock_service.generate.return_value = response

    result = await agent.run(request)

    assert isinstance(result, StoryboardResponse)
    assert result.scenes == []