from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.services.storyboard_service import StoryboardAPIService


pytestmark = pytest.mark.asyncio


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def repository():
    repo = MagicMock()

    repo.create_storyboard = AsyncMock()
    repo.get_or_raise = AsyncMock()
    repo.update_storyboard = AsyncMock()
    repo.delete_storyboard = AsyncMock()

    return repo


@pytest.fixture
def agent():
    mock = MagicMock()
    mock.generate = AsyncMock()
    return mock


@pytest.fixture
def service(db, repository, agent):
    service = StoryboardAPIService(db)
    service.repository = repository
    service.agent = agent
    return service


async def test_generate_storyboard(
    service,
    repository,
    agent,
):
    script_id = uuid4()

    scene = MagicMock()
    scene.model_dump.return_value = {
        "scene_number": 1,
        "narration": "Intro",
        "visual": "Village",
        "image_prompt": "Village at sunrise",
        "duration_seconds": 8,
    }

    response = MagicMock()
    response.scenes = [scene]

    agent.generate.return_value = response

    storyboard = MagicMock()

    repository.create_storyboard.return_value = storyboard

    result = await service.generate(
        script_id=script_id,
        script="Test script",
    )

    repository.create_storyboard.assert_awaited_once()

    assert result == storyboard


async def test_get_storyboard(
    service,
    repository,
):
    storyboard = MagicMock()

    repository.get_or_raise.return_value = storyboard

    result = await service.get(uuid4())

    repository.get_or_raise.assert_awaited_once()

    assert result == storyboard


async def test_update_storyboard(
    service,
    repository,
):
    storyboard = MagicMock()

    repository.get_or_raise.return_value = storyboard
    repository.update_storyboard.return_value = storyboard

    result = await service.update(
        uuid4(),
        {
            "scenes": [
                {
                    "scene_number": 2,
                }
            ]
        },
    )

    repository.update_storyboard.assert_awaited_once()

    assert result == storyboard


async def test_delete_storyboard(
    service,
    repository,
):
    storyboard = MagicMock()

    repository.get_or_raise.return_value = storyboard

    result = await service.delete(
        uuid4(),
    )

    repository.delete_storyboard.assert_awaited_once_with(
        storyboard,
    )

    assert result == {
        "message": "Storyboard deleted successfully."
    }