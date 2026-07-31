"""Unit tests for PublishingWorkflow."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflows.publishing_workflow import PublishingWorkflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_script():
    script = MagicMock()
    script.id = uuid.uuid4()
    script.content = "Test script content about Docker vs Kubernetes"
    script.seo_title = "Docker vs Kubernetes"
    script.script_type = "long"
    return script


def _make_mock_video():
    video = MagicMock()
    video.id = uuid.uuid4()
    return video


def _make_mock_session(video):
    """Build an AsyncSession mock whose execute().scalar_one() returns the video."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = video
    session.execute.return_value = execute_result
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publishing_workflow_runs_successfully():
    script = _make_mock_script()
    video = _make_mock_video()
    session = _make_mock_session(video)

    with (
        patch(
            "app.workflows.publishing_workflow.StoryboardService.generate",
            new_callable=AsyncMock,
            return_value=MagicMock(scenes=[]),
        ),
        patch(
            "app.workflows.publishing_workflow.ThumbnailAgentService.run_for_script",
            new_callable=AsyncMock,
            return_value=MagicMock(concept="Bold thumbnail", ctr_score=80.0),
        ),
        patch(
            "app.workflows.publishing_workflow.VoiceAgentService.run_for_script",
            new_callable=AsyncMock,
            return_value=MagicMock(audio_path="/audio/test.mp3"),
        ),
        patch(
            "app.workflows.publishing_workflow.VideoAgentService.run_for_script",
            new_callable=AsyncMock,
            return_value=MagicMock(title="Docker vs Kubernetes", video_path="/video/test.mp4"),
        ),
        patch(
            "app.workflows.publishing_workflow.UploadAgentService.run_for_video",
            new_callable=AsyncMock,
            return_value=MagicMock(video_title="Docker vs Kubernetes", status="ready"),
        ),
    ):
        workflow = PublishingWorkflow(session)
        result = await workflow.run(script, niche="technology")

    assert "storyboard" in result
    assert "voice" in result
    assert "thumbnail" in result
    assert "video" in result
    assert "upload" in result


@pytest.mark.asyncio
async def test_publishing_workflow_passes_script_content_to_storyboard():
    script = _make_mock_script()
    video = _make_mock_video()
    session = _make_mock_session(video)

    storyboard_mock = AsyncMock(return_value=MagicMock(scenes=[]))

    with (
        patch("app.workflows.publishing_workflow.StoryboardService.generate", storyboard_mock),
        patch("app.workflows.publishing_workflow.ThumbnailAgentService.run_for_script", new_callable=AsyncMock, return_value=MagicMock()),
        patch("app.workflows.publishing_workflow.VoiceAgentService.run_for_script", new_callable=AsyncMock, return_value=MagicMock()),
        patch("app.workflows.publishing_workflow.VideoAgentService.run_for_script", new_callable=AsyncMock, return_value=MagicMock(title="T")),
        patch("app.workflows.publishing_workflow.UploadAgentService.run_for_video", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        workflow = PublishingWorkflow(session)
        await workflow.run(script)

    # Verify storyboard received a request built from script.content
    call_args = storyboard_mock.call_args
    request = call_args[0][0] if call_args[0] else call_args[1].get("request") or list(call_args[1].values())[0]
    assert request.script == script.content


@pytest.mark.asyncio
async def test_publishing_workflow_uses_niche():
    script = _make_mock_script()
    video = _make_mock_video()
    session = _make_mock_session(video)

    thumbnail_mock = AsyncMock(return_value=MagicMock(concept="test", ctr_score=70.0))

    with (
        patch("app.workflows.publishing_workflow.StoryboardService.generate", new_callable=AsyncMock, return_value=MagicMock(scenes=[])),
        patch("app.workflows.publishing_workflow.ThumbnailAgentService.run_for_script", thumbnail_mock),
        patch("app.workflows.publishing_workflow.VoiceAgentService.run_for_script", new_callable=AsyncMock, return_value=MagicMock()),
        patch("app.workflows.publishing_workflow.VideoAgentService.run_for_script", new_callable=AsyncMock, return_value=MagicMock(title="T")),
        patch("app.workflows.publishing_workflow.UploadAgentService.run_for_video", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        workflow = PublishingWorkflow(session)
        await workflow.run(script, niche="gaming")

    thumbnail_mock.assert_called_once()
    _, kwargs = thumbnail_mock.call_args
    assert kwargs.get("niche") == "gaming"