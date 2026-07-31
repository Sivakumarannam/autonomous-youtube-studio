"""Unit tests for the SEO gate stage in PipelineAgentService.

All external dependencies (DB, script agent, quality agent, video agent,
SEO scorer) are mocked.  No real DB session, no LLM calls.

The fixture wires up a minimal PipelineAgentService with a fake session and
exercises _run_seo_gate() and its integration inside _execute_stages().
"""
from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest

from app.agents.pipeline_agent.service import PipelineAgentService
from app.agents.seo_agent.scoring import score_seo_metadata, SeoScoreBreakdown
from app.core.exceptions import SeoError
from app.core.config import settings


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_script(
    *,
    seo_title: str = "A title",
    seo_description: str = "A description.",
    seo_tags: str = "[]",
    hashtags: str = "[]",
    seo_gate_score: float = 0.0,
):
    """Return a minimal mock Script object."""
    script = MagicMock()
    script.id = "script-uuid-001"
    script.seo_title = seo_title
    script.seo_description = seo_description
    script.seo_tags = seo_tags
    script.hashtags = hashtags
    script.seo_gate_score = seo_gate_score
    return script


def _make_service() -> PipelineAgentService:
    session = AsyncMock()
    session.flush = AsyncMock()
    return PipelineAgentService(session)


# ---------------------------------------------------------------------------
# _run_seo_gate unit tests
# ---------------------------------------------------------------------------

class TestRunSeoGateUnit:
    """Direct tests of _run_seo_gate; no _execute_stages involved."""

    @pytest.mark.asyncio
    async def test_gate_passes_when_score_at_threshold(self):
        """Score exactly equal to seo_min_score should pass."""
        svc = _make_service()

        # Build metadata that the scorer will give exactly 60 pts.
        # We'll patch score_seo_metadata to return a controlled breakdown.
        breakdown = SeoScoreBreakdown(
            title_score=10.0,
            description_score=15.0,
            hashtag_score=10.0,
            tags_score=25.0,
            total=60.0,
        )

        with patch(
            "app.agents.pipeline_agent.service.PipelineAgentService._run_seo_gate",
            new=None,
        ):
            pass  # We call the real method below, just patching scorer.

        with patch(
            "app.agents.seo_agent.scoring.score_seo_metadata",
            return_value=breakdown,
        ) as mock_scorer, patch(
            "app.database.repositories.script_repository.ScriptRepository.update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = _make_script(seo_gate_score=60.0)

            script = _make_script()
            result = await svc._run_seo_gate(script)

        assert result is True
        mock_scorer.assert_called_once_with(
            seo_title=script.seo_title,
            seo_description=script.seo_description,
            seo_tags_json=script.seo_tags,
            hashtags_json=script.hashtags,
        )

    @pytest.mark.asyncio
    async def test_gate_fails_when_score_below_threshold(self):
        """Score below seo_min_score should return False."""
        svc = _make_service()

        breakdown = SeoScoreBreakdown(
            title_score=0.0,
            description_score=0.0,
            hashtag_score=0.0,
            tags_score=0.0,
            total=8.0,  # only no-clickbait bonus
        )

        with patch(
            "app.agents.seo_agent.scoring.score_seo_metadata",
            return_value=breakdown,
        ), patch(
            "app.database.repositories.script_repository.ScriptRepository.update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = _make_script(seo_gate_score=8.0)
            script = _make_script()
            result = await svc._run_seo_gate(script)

        assert result is False

    @pytest.mark.asyncio
    async def test_gate_writes_score_to_script_repo(self):
        """seo_gate_score is persisted to the script record."""
        svc = _make_service()

        breakdown = SeoScoreBreakdown(total=75.0)

        with patch(
            "app.agents.seo_agent.scoring.score_seo_metadata",
            return_value=breakdown,
        ), patch(
            "app.database.repositories.script_repository.ScriptRepository.update",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = _make_script(seo_gate_score=75.0)
            script = _make_script()
            await svc._run_seo_gate(script)

        mock_update.assert_called_once()
        _, kwargs = mock_update.call_args
        assert kwargs.get("seo_gate_score") == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_gate_respects_custom_seo_min_score(self):
        """Gate uses settings.seo_min_score, not a hardcoded constant."""
        svc = _make_service()
        breakdown = SeoScoreBreakdown(total=55.0)

        # Patch the settings object used inside pipeline_agent.service directly.
        mock_settings = MagicMock()
        mock_settings.seo_min_score = 50

        with patch(
            "app.agents.seo_agent.scoring.score_seo_metadata",
            return_value=breakdown,
        ), patch(
            "app.database.repositories.script_repository.ScriptRepository.update",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "app.agents.pipeline_agent.service.settings",
            mock_settings,
        ):
            mock_update.return_value = _make_script()
            script = _make_script()
            result = await svc._run_seo_gate(script)

        # 55.0 ≥ 50 → should pass
        assert result is True


# ---------------------------------------------------------------------------
# Pipeline integration: SEO gate stage wired into _execute_stages
# ---------------------------------------------------------------------------

class TestPipelineSeoGateIntegration:
    """_execute_stages integration: quality passes, SEO gate fires next."""

    def _make_pipeline_run(self, *, script_id=None, upload_id=None):
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

    @pytest.mark.asyncio
    async def test_seo_failure_halts_pipeline_and_rejects_topic(self):
        """When _run_seo_gate returns False the pipeline halts at stage='seo'."""
        svc = _make_service()
        pipeline_run = self._make_pipeline_run()

        pipeline_repo = AsyncMock()
        # Make update always return the same run object (simplified)
        pipeline_repo.update = AsyncMock(return_value=pipeline_run)

        topic = MagicMock()
        topic.content_type = "technology"

        topic_repo = AsyncMock()
        topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
        topic_repo.update = AsyncMock(return_value=topic)

        script = _make_script()
        video_repo = AsyncMock()
        upload_repo = AsyncMock()

        svc._session.commit = AsyncMock()
        svc._session.add = MagicMock()
        svc._session.flush = AsyncMock()

        mock_render_video = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=False)), \
             patch.object(svc, "_render_video", new=mock_render_video), \
             patch.object(svc, "_log", new=AsyncMock()), \
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

        # Topic must be marked REJECTED
        topic_repo.update.assert_called()

        # pipeline_repo.update should have been called with failed_stage="seo"
        seo_fail_calls = [
            call for call in pipeline_repo.update.call_args_list
            if call.kwargs.get("failed_stage") == "seo"
        ]
        assert seo_fail_calls, "Expected pipeline update with failed_stage='seo'"

        # _render_video must NOT have been called
        mock_render_video.assert_not_called()

    @pytest.mark.asyncio
    async def test_seo_gate_runs_after_quality_gate(self):
        """SEO gate must be invoked when quality gate passes."""
        svc = _make_service()
        pipeline_run = self._make_pipeline_run()

        pipeline_repo = AsyncMock()
        pipeline_repo.update = AsyncMock(return_value=pipeline_run)

        topic = MagicMock()
        topic.content_type = "technology"
        topic_repo = AsyncMock()
        topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
        topic_repo.update = AsyncMock(return_value=topic)

        script = _make_script()
        video = MagicMock()
        from app.database.models.video import VideoStatus
        video.status = VideoStatus.COMPLETE
        video.error_message = None
        video_repo = AsyncMock()
        video_repo.get_by_script_id = AsyncMock(return_value=video)

        upload = MagicMock()
        upload.id = "upload-uuid"
        upload.publish_status = MagicMock()
        upload.publish_status.value = "scheduled"
        upload_repo = AsyncMock()
        upload_repo.update = AsyncMock(return_value=upload)

        svc._session.commit = AsyncMock()
        svc._session.add = MagicMock()
        svc._session.flush = AsyncMock()
        svc._session.refresh = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=True)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=True)) as mock_seo, \
             patch.object(svc, "_render_video", new=AsyncMock()), \
             patch.object(svc, "_log", new=AsyncMock()), \
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

        mock_seo.assert_called_once_with(script)

    @pytest.mark.asyncio
    async def test_seo_gate_not_called_when_quality_fails(self):
        """If quality gate fails, SEO gate must not be invoked."""
        svc = _make_service()
        pipeline_run = self._make_pipeline_run()

        pipeline_repo = AsyncMock()
        pipeline_repo.update = AsyncMock(return_value=pipeline_run)

        topic = MagicMock()
        topic.content_type = "technology"
        topic_repo = AsyncMock()
        topic_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
        topic_repo.update = AsyncMock(return_value=topic)

        script = _make_script()
        video_repo = AsyncMock()
        upload_repo = AsyncMock()

        svc._session.commit = AsyncMock()
        svc._session.add = MagicMock()
        svc._session.flush = AsyncMock()

        with patch.object(svc, "_generate_script", new=AsyncMock(return_value=script)), \
             patch.object(svc, "_run_quality_gate", new=AsyncMock(return_value=False)), \
             patch.object(svc, "_run_seo_gate", new=AsyncMock(return_value=True)) as mock_seo, \
             patch.object(svc, "_render_video", new=AsyncMock()), \
             patch.object(svc, "_log", new=AsyncMock()), \
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

        mock_seo.assert_not_called()


# ---------------------------------------------------------------------------
# SeoError exception shape
# ---------------------------------------------------------------------------

class TestSeoError:
    def test_seo_error_has_score_and_threshold(self):
        err = SeoError(score=42.0, threshold=60.0)
        assert err.score == pytest.approx(42.0)
        assert err.threshold == pytest.approx(60.0)
        assert "42.0" in str(err)
        assert "60.0" in str(err)
        assert err.code == "SEO_ERROR"

    def test_seo_error_is_not_retryable(self):
        """SeoError must NOT be classified as retryable."""
        from app.utils.retry import is_retryable_error
        err = SeoError(score=30.0, threshold=60.0)
        assert is_retryable_error(err) is False
