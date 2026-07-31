import uuid

import pytest

from app.database.repositories.storyboard_repository import StoryboardRepository
from tests.conftest import (
    create_test_channel,
    create_test_topic,
)


pytestmark = pytest.mark.asyncio


async def create_script(test_session, create_test_script):
    channel = await create_test_channel(test_session)

    topic = await create_test_topic(
        test_session,
        channel.id,
    )

    return await create_test_script(
        test_session,
        topic.id,
        channel.id,
    )


async def test_create_storyboard(
    test_session,
    create_test_script,
):
    script = await create_script(
        test_session,
        create_test_script,
    )

    repository = StoryboardRepository(test_session)

    storyboard = await repository.create_storyboard(
        script_id=script.id,
        scenes=[
            {
                "scene_number": 1,
                "narration": "Hello",
                "visual": "Character waving",
                "image_prompt": "Cute cartoon",
                "duration_seconds": 5,
            }
        ],
    )

    assert storyboard.id is not None
    assert storyboard.script_id == script.id
    assert len(storyboard.scenes) == 1


async def test_get_by_script_id(
    test_session,
    create_test_script,
):
    script = await create_script(
        test_session,
        create_test_script,
    )

    repository = StoryboardRepository(test_session)

    created = await repository.create_storyboard(
        script_id=script.id,
        scenes=[
            {
                "scene_number": 1,
                "narration": "Intro",
                "visual": "Opening scene",
                "image_prompt": "Cartoon intro",
                "duration_seconds": 6,
            }
        ],
    )

    found = await repository.get_by_script_id(
        script.id,
    )

    assert found is not None
    assert found.id == created.id


async def test_get_by_id(
    test_session,
    create_test_script,
):
    script = await create_script(
        test_session,
        create_test_script,
    )

    repository = StoryboardRepository(test_session)

    created = await repository.create_storyboard(
        script_id=script.id,
        scenes=[],
    )

    found = await repository.get_by_id(created.id)

    assert found is not None
    assert found.id == created.id


async def test_update_storyboard(
    test_session,
    create_test_script,
):
    script = await create_script(
        test_session,
        create_test_script,
    )

    repository = StoryboardRepository(test_session)

    storyboard = await repository.create_storyboard(
        script_id=script.id,
        scenes=[],
    )

    updated = await repository.update_storyboard(
        storyboard,
        [
            {
                "scene_number": 2,
                "narration": "Updated",
                "visual": "Updated visual",
                "image_prompt": "Updated prompt",
                "duration_seconds": 8,
            }
        ],
    )

    assert updated.scenes[0]["scene_number"] == 2


async def test_delete_storyboard(
    test_session,
    create_test_script,
):
    script = await create_script(
        test_session,
        create_test_script,
    )

    repository = StoryboardRepository(test_session)

    storyboard = await repository.create_storyboard(
        script_id=script.id,
        scenes=[],
    )

    await repository.delete_storyboard(
        storyboard,
    )

    deleted = await repository.get_by_id(
        storyboard.id,
    )

    assert deleted is None


async def test_get_by_script_id_returns_none(
    test_session,
):
    repository = StoryboardRepository(test_session)

    result = await repository.get_by_script_id(
        uuid.uuid4(),
    )

    assert result is None