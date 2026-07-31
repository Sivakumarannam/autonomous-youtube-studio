"""Unit tests for the self-healing voice stage in PipelineAgentService.

All external dependencies (DB, VoiceAgentService, VoiceRepository) are
mocked. No real DB session, no LLM/TTS calls.

Mirrors the structure and conventions of test_pipeline_seo_gate.py.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.pipeline_agent.service import PipelineAgentService
from app.database.models.voice import VoiceStatus


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_script():
    script = MagicMock()
    script.id = "script-uuid-001"
    return script


def _make_voice(status: VoiceStatus):
    voice = MagicMock()
    voice.status = status
    return voice


def _make_service() -> PipelineAgentService:
    session = AsyncMock()
    session.flush = AsyncMock()
    return PipelineAgentService(session)


def _make_pipeline_run(*, script_id=None, upload_id=None):
    run = MagicMock()
    run.id = "run-uuid-001"
    run.topic_id = "topic-uuid-001"
    run.script_type = "long"
    run.retry_count = 0
    run.max_retries = 3
    run.current_stage = None
    run.failed_stage = None
    run.upload_id = upload_id
    run.script_id = script_id
    run.video_id = None
    return run


# ---------------------------------------------------------------------------
# _run_voice_stage unit tests
# ---------------------------------------------------------------------------

class TestRunVoiceStageUnit:
    """Direct tests of _run_voice_stage; no _execute_stages involved."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        svc = _make_service()
        script = _make_script()

        mock_run_for_script = AsyncMock()
        mock_get_by_script_id = AsyncMock(
            return_value=_make_voice(VoiceStatus.COMPLETE)
        )

        with patch(
            "app.agents.voice_agent.service.VoiceAgentService.run_for_script",
            new=mock_run_for_script,
        ), patch(
            "app.database.repositories.voice_repository.VoiceRepository.get_by_script_id",
            new=mock_get_by_script_id,
        ), patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await svc._run_voice_stage(script)

        assert result is True
        mock_run_for_script.assert_awaited_once()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_heals_locally_after_incomplete_first_attempt(self):
        """First attempt leaves the Voice record incomplete; a local retry
        produces COMPLETE. The stage must succeed and sleep once between
        attempts, without touching pipeline_run.retry_count at all (the
        stage has no access to pipeline_run, by design)."""
        svc = _make_service()
        script = _make_script()

        mock_run_for_script = AsyncMock()
        mock_get_by_script_id = AsyncMock(
            side_effect=[
                _make_voice(VoiceStatus.PENDING),
                _make_voice(VoiceStatus.COMPLETE),
            ]
        )

        with patch(
            "app.agents.voice_agent.service.VoiceAgentService.run_for_script",
            new=mock_run_for_script,
        ), patch(
            "app.database.repositories.voice_repository.VoiceRepository.get_by_script_id",
            new=mock_get_by_script_id,
        ), patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await svc._run_voice_stage(script)

        assert result is True
        assert mock_run_for_script.await_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exhausts_heal_attempts_and_returns_false(self):
        """Voice record never becomes COMPLETE within voice_max_heal_attempts
        → the stage gives up and returns False. Total attempts =
        voice_max_heal_attempts + 1 (one initial + N local heals)."""
        svc = _make_service()
        script = _make_script()

        mock_settings = MagicMock()
        mock_settings.voice_max_heal_attempts = 2

        mock_run_for_script = AsyncMock()
        mock_get_by_script_id = AsyncMock(
            return_value=_make_voice(VoiceStatus.FAILED)
        )

        with patch(
            "app.agents.voice_agent.service.VoiceAgentService.run_for_script",
            new=mock_run_for_script,
        ), patch(
            "app.database.repositories.voice_repository.VoiceRepository.get_by_script_id",
            new=mock_get_by_script_id,
        ), patch(
            "app.agents.pipeline_agent.service.settings", mock_settings
        ), patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await svc._run_voice_stage(script)

        assert result is False
        # 1 initial + 2 local heal attempts = 3 total calls.
        assert mock_run_for_script.await_count == 3
        # Sleeps between attempts only, never after the final one: 2 sleeps.
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    async def test_technical_failure_propagates_uncaught(self):
        """An exception from run_for_script must propagate out of
        _run_voice_stage untouched — it is handled by the existing outer
        retry loop in run(), not by local healing logic."""
        svc = _make_service()
        script = _make_script()

        mock_run_for_script = AsyncMock(side_effect=RuntimeError("tts down"))

        with patch(
            "app.agents.voice_agent.service.VoiceAgentService.run_for_script",
            new=mock_run_for_script,
        ), patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError, match="tts down"):
                await svc._run_voice_stage(script)


# ---------------------------------------------------------------------------
# Pipeline integration: voice stage wired into _execute_stages
# ---------------------------------------------------------------------------

class TestPipelineVoiceStageIntegration:
    """_execute_stages integration: voice stage sits between SEO gate and
    video render, gated on settings.voice_enabled."""

    def _wire_common_mocks(self, svc, script, pipeline_run):
        pipeline_repo = AsyncMock()
        pipeline_repo.update = AsyncMock(return_value=pipeline_run)

        topic = MagicMock()
        topic.content_type = "technology"
        topic_repo = AsyncMock()
        topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
        topic_repo.update = AsyncMock(return_value=topic)

        video_repo = AsyncMock()
        upload_repo = AsyncMock()

        svc._session.commit = AsyncMock()
        svc._session.add = MagicMock()
        svc._session.flush = AsyncMock()
        svc._session.refresh = AsyncMock()

        return pipeline_repo, topic_repo, video_repo, upload_repo

    @pytest.mark.asyncio
    async def test_voice_disabled_skips_stage_entirely(self):
        """voice_enabled=False → _run_voice_stage / VoiceAgentService must
        never be called; pipeline proceeds exactly as today."""
        svc = _make_service()
        pipeline_run = _make_pipeline_run()
        script = _make_script()

        pipeline_repo, topic_repo, video_repo, upload_repo = (
            self._wire_common_mocks(svc, script, pipeline_run)
        )

        video = MagicMock()
        from app.database.models.video import VideoStatus
        video.status = VideoStatus.COMPLETE
        video.error_message = None
        video_repo.get_by_script_id = AsyncMock(return_value=video)

        upload = MagicMock()
        upload.id = "upload-uuid"
        upload.publish_status = MagicMock()
        upload.publish_status.value = "scheduled"
        upload_repo.update = AsyncMock(return_value=upload)

        mock_settings = MagicMock()
        mock_settings.voice_enabled = False
        mock_settings.auto_publish_enabled = True
        mock_settings.pipeline_publish_delay_minutes = 15
        mock_settings.scheduler_max_retries = 3

        mock_voice_stage = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_voice_stage", new=mock_voice_stage), \
             patch.object(svc, "_render_video", new=AsyncMock()), \
             patch.object(svc, "_log", new=AsyncMock()), \
             patch("app.agents.pipeline_agent.service.settings", mock_settings), \
             patch(
                 "app.agents.pipeline_agent.service.PipelineRunRepository",
                 return_value=pipeline_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.TopicRepository",
                 return_value=topic_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.VideoRepository",
                 return_value=video_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.UploadRepository",
                 return_value=upload_repo,
             ):
            await svc._execute_stages(pipeline_repo, pipeline_run, 0.0)

        mock_voice_stage.assert_not_called()
        # No pipeline update should have set current_stage="voice".
        voice_stage_calls = [
            call for call in pipeline_repo.update.call_args_list
            if call.kwargs.get("current_stage") == "voice"
        ]
        assert not voice_stage_calls

    @pytest.mark.asyncio
    async def test_voice_enabled_success_proceeds_to_video(self):
        """voice_enabled=True, voice stage succeeds → pipeline proceeds
        normally to video render."""
        svc = _make_service()
        pipeline_run = _make_pipeline_run()
        script = _make_script()

        pipeline_repo, topic_repo, video_repo, upload_repo = (
            self._wire_common_mocks(svc, script, pipeline_run)
        )

        video = MagicMock()
        from app.database.models.video import VideoStatus
        video.status = VideoStatus.COMPLETE
        video.error_message = None
        video_repo.get_by_script_id = AsyncMock(return_value=video)

        upload = MagicMock()
        upload.id = "upload-uuid"
        upload.publish_status = MagicMock()
        upload.publish_status.value = "scheduled"
        upload_repo.update = AsyncMock(return_value=upload)

        mock_settings = MagicMock()
        mock_settings.voice_enabled = True
        mock_settings.auto_publish_enabled = True
        mock_settings.pipeline_publish_delay_minutes = 15
        mock_settings.scheduler_max_retries = 3

        mock_render_video = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_voice_stage", new=AsyncMock(return_value=True)) as mock_voice_stage, \
             patch.object(svc, "_render_video", new=mock_render_video), \
             patch.object(svc, "_log", new=AsyncMock()), \
             patch("app.agents.pipeline_agent.service.settings", mock_settings), \
             patch(
                 "app.agents.pipeline_agent.service.PipelineRunRepository",
                 return_value=pipeline_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.TopicRepository",
                 return_value=topic_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.VideoRepository",
                 return_value=video_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.UploadRepository",
                 return_value=upload_repo,
             ):
            await svc._execute_stages(pipeline_repo, pipeline_run, 0.0)

        mock_voice_stage.assert_called_once_with(script)
        mock_render_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_voice_enabled_exhausted_fails_pipeline_and_rejects_topic(self):
        """voice_enabled=True, all local heal attempts exhausted →
        PipelineRun FAILED, failed_stage='voice', Topic REJECTED,
        automation_status untouched (mirrors quality/SEO gate failures)."""
        svc = _make_service()
        pipeline_run = _make_pipeline_run()
        script = _make_script()

        pipeline_repo, topic_repo, video_repo, upload_repo = (
            self._wire_common_mocks(svc, script, pipeline_run)
        )

        mock_settings = MagicMock()
        mock_settings.voice_enabled = True
        mock_settings.auto_publish_enabled = True
        mock_settings.pipeline_publish_delay_minutes = 15
        mock_settings.scheduler_max_retries = 3

        mock_render_video = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_voice_stage", new=AsyncMock(return_value=False)), \
             patch.object(svc, "_render_video", new=mock_render_video), \
             patch.object(svc, "_log", new=AsyncMock()), \
             patch("app.agents.pipeline_agent.service.settings", mock_settings), \
             patch(
                 "app.agents.pipeline_agent.service.PipelineRunRepository",
                 return_value=pipeline_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.TopicRepository",
                 return_value=topic_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.VideoRepository",
                 return_value=video_repo,
             ), patch(
                 "app.agents.pipeline_agent.service.UploadRepository",
                 return_value=upload_repo,
             ):
            await svc._execute_stages(pipeline_repo, pipeline_run, 0.0)

        # Topic must be marked REJECTED.
        topic_repo.update.assert_called_once()
        from app.database.models.topic import TopicStatus
        _, kwargs = topic_repo.update.call_args
        assert kwargs.get("status") == TopicStatus.REJECTED

        # pipeline_repo.update should have been called with failed_stage="voice".
        voice_fail_calls = [
            call for call in pipeline_repo.update.call_args_list
            if call.kwargs.get("failed_stage") == "voice"
        ]
        assert voice_fail_calls, "Expected pipeline update with failed_stage='voice'"
        assert voice_fail_calls[0].kwargs.get("status") == "failed" or hasattr(
            voice_fail_calls[0].kwargs.get("status"), "value"
        )

        # _render_video must NOT have been called — pipeline halted before video.
        mock_render_video.assert_not_called()

        # automation_status is never referenced/touched by this stage at all —
        # no call in this test path should mention it.
        for call in pipeline_repo.update.call_args_list:
            assert "automation_status" not in call.kwargs
        for call in topic_repo.update.call_args_list:
            assert "automation_status" not in call.kwargs
