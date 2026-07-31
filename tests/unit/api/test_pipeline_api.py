"""Unit tests for the Pipeline API (Stage 1).

All LLM/agent/YouTube calls are mocked. The pipeline background task is
NOT awaited in tests — we test the service layer and route layer separately.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.models.script import Script, ScriptType, ScriptStatus
from app.database.models.video import Video, VideoStatus
from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.database.models.topic import Topic, TopicStatus, TopicSource
from app.database.models.quality_report import QualityReport, QualityStatus
from app.database.models.channel import Channel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def topic_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def channel_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def script_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def video_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def upload_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def pipeline_run_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_topic(topic_id, channel_id):
    return Topic(
        id=topic_id,
        channel_id=channel_id,
        title="Test Topic: AI in 2026",
        description="A deep dive into AI trends",
        content_type="technology",
        status=TopicStatus.PENDING,
        source=TopicSource.MANUAL,
        score=0.9,
    )


def _make_channel(channel_id):
    from app.database.models.channel import Channel, ChannelStatus, ContentType, AspectRatio
    return Channel(
        id=channel_id,
        name="Test Channel",
        niche="technology",
        language="en",
        content_type=ContentType.LONG,
        aspect_ratio=AspectRatio.LANDSCAPE,
        target_duration=600,
        upload_schedule="daily",
        status=ChannelStatus.ACTIVE,
    )


def _make_script(script_id, topic_id, channel_id):
    return Script(
        id=script_id,
        topic_id=topic_id,
        channel_id=channel_id,
        script_type=ScriptType.LONG,
        content="This is a test script about AI.",
        word_count=50,
        estimated_duration=300,
        seo_title="AI in 2026: Everything You Need to Know",
        seo_description="Comprehensive overview of AI developments in 2026.",
        seo_tags='["ai", "technology", "2026"]',
        quality_score=0.0,
        status=ScriptStatus.DRAFT,
    )


def _make_pipeline_run(
    run_id,
    topic_id,
    channel_id,
    status=PipelineStatus.PENDING,
    script_id=None,
    video_id=None,
    upload_id=None,
):
    return PipelineRun(
        id=run_id,
        topic_id=topic_id,
        channel_id=channel_id,
        script_type="long",
        status=status,
        current_stage=None,
        failed_stage=None,
        error_message=None,
        script_id=script_id,
        video_id=video_id,
        upload_id=upload_id,
        retry_count=0,
        max_retries=3,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# PipelineAgentService unit tests
# ---------------------------------------------------------------------------

class TestPipelineAgentServiceQualityGate:
    """Quality gate branching within PipelineAgentService."""

    @pytest.mark.asyncio
    async def test_quality_gate_pass_continues_pipeline(
        self, topic_id, channel_id, script_id, video_id, upload_id, pipeline_run_id
    ):
        """When quality passes, pipeline proceeds to video and upload stages."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        from app.core.exceptions import QualityError

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        topic = _make_topic(topic_id, channel_id)
        script = _make_script(script_id, topic_id, channel_id)
        video = Video(
            id=video_id,
            script_id=script_id,
            status=VideoStatus.COMPLETE,
            video_path="/tmp/video.mp4",
            duration=300.0,
            file_size=1024,
        )
        upload = Upload(
            id=upload_id,
            video_id=video_id,
            title="AI in 2026",
            status=UploadStatus.SCHEDULED,
            publish_status=PublishStatus.SCHEDULED,
        )
        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)

        with (
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPR,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTR,
            patch("app.agents.pipeline_agent.service.VideoRepository") as MockVR,
            patch("app.agents.pipeline_agent.service.UploadRepository") as MockUR,
            patch("app.agents.long_script_agent.service.LongScriptAgentService", autospec=True) as _,
            patch("app.agents.quality_agent.service.QualityAgentService", autospec=True) as _,
            patch("app.agents.video_agent.service.VideoAgentService", autospec=True) as _,
        ):
            pr_repo = MockPR.return_value
            pr_repo.update = AsyncMock(return_value=run)
            tr_repo = MockTR.return_value
            tr_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
            vr_repo = MockVR.return_value
            vr_repo.get_by_script_id = AsyncMock(return_value=video)
            ur_repo = MockUR.return_value
            ur_repo.update = AsyncMock(return_value=upload)

            svc = PipelineAgentService(session)
            svc._generate_script = AsyncMock(return_value=script)
            svc._run_quality_gate = AsyncMock(return_value=True)
            svc._run_seo_gate = AsyncMock(return_value=True)
            svc._render_video = AsyncMock()
            svc._log = AsyncMock()

            await svc.run(run)

            # Quality gate was called
            svc._run_quality_gate.assert_awaited_once_with(script, topic.content_type)
            # Video render was called
            svc._render_video.assert_awaited_once()
            # Upload repo update called (APPROVED → SCHEDULED)
            assert ur_repo.update.await_count >= 2

    @pytest.mark.asyncio
    async def test_quality_gate_fail_halts_pipeline(
        self, topic_id, channel_id, script_id, pipeline_run_id
    ):
        """When quality fails, pipeline sets FAILED status and does not render video."""
        from app.agents.pipeline_agent.service import PipelineAgentService

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        topic = _make_topic(topic_id, channel_id)
        script = _make_script(script_id, topic_id, channel_id)
        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)

        with (
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPR,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTR,
            patch("app.agents.pipeline_agent.service.VideoRepository"),
            patch("app.agents.pipeline_agent.service.UploadRepository"),
        ):
            pr_repo = MockPR.return_value
            pr_repo.update = AsyncMock(return_value=run)
            tr_repo = MockTR.return_value
            tr_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
            tr_repo.update = AsyncMock(return_value=topic)

            svc = PipelineAgentService(session)
            svc._generate_script = AsyncMock(return_value=script)
            svc._run_quality_gate = AsyncMock(return_value=False)
            svc._render_video = AsyncMock()
            svc._log = AsyncMock()

            await svc.run(run)

            # Video render must NOT be called
            svc._render_video.assert_not_awaited()
            # PipelineRun updated with FAILED status and failed_stage="quality"
            update_calls = pr_repo.update.await_args_list
            failed_call = next(
                (c for c in update_calls if c.kwargs.get("status") == PipelineStatus.FAILED),
                None,
            )
            assert failed_call is not None
            assert failed_call.kwargs.get("failed_stage") == "quality"

    @pytest.mark.asyncio
    async def test_video_failure_halts_pipeline(
        self, topic_id, channel_id, script_id, video_id, pipeline_run_id
    ):
        """When video render returns a FAILED video, pipeline halts at video stage."""
        from app.agents.pipeline_agent.service import PipelineAgentService

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        topic = _make_topic(topic_id, channel_id)
        script = _make_script(script_id, topic_id, channel_id)
        failed_video = Video(
            id=video_id,
            script_id=script_id,
            status=VideoStatus.FAILED,
            error_message="Render failed: PIL not available.",
        )
        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)

        with (
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPR,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTR,
            patch("app.agents.pipeline_agent.service.VideoRepository") as MockVR,
            patch("app.agents.pipeline_agent.service.UploadRepository"),
        ):
            pr_repo = MockPR.return_value
            pr_repo.update = AsyncMock(return_value=run)
            tr_repo = MockTR.return_value
            tr_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
            vr_repo = MockVR.return_value
            vr_repo.get_by_script_id = AsyncMock(return_value=failed_video)

            svc = PipelineAgentService(session)
            svc._generate_script = AsyncMock(return_value=script)
            svc._run_quality_gate = AsyncMock(return_value=True)
            svc._run_seo_gate = AsyncMock(return_value=True)
            svc._render_video = AsyncMock()
            svc._log = AsyncMock()

            await svc.run(run)

            update_calls = pr_repo.update.await_args_list
            failed_call = next(
                (c for c in update_calls if c.kwargs.get("status") == PipelineStatus.FAILED),
                None,
            )
            assert failed_call is not None
            assert failed_call.kwargs.get("failed_stage") == "video"

    @pytest.mark.asyncio
    async def test_pipeline_uses_delay_for_scheduled_at(
        self, topic_id, channel_id, script_id, video_id, upload_id, pipeline_run_id
    ):
        """scheduled_at must be now() + pipeline_publish_delay_minutes when the
        channel's peak windows span the full day (i.e. peak-time scheduling
        does not push the timestamp any later than the flat-delay floor)."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        from app.core.config import settings
        import json as _json

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        topic = _make_topic(topic_id, channel_id)
        script = _make_script(script_id, topic_id, channel_id)
        video = Video(
            id=video_id, script_id=script_id,
            status=VideoStatus.COMPLETE, video_path="/tmp/v.mp4",
        )
        captured_upload: list[Upload] = []

        async def capture_add(obj):
            if isinstance(obj, Upload):
                captured_upload.append(obj)

        session.add = MagicMock(side_effect=lambda obj: captured_upload.append(obj) if isinstance(obj, Upload) else None)

        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)
        upload = Upload(
            id=upload_id, video_id=video_id,
            status=UploadStatus.SCHEDULED, publish_status=PublishStatus.SCHEDULED,
        )
        channel = Channel(
            id=channel_id,
            name="Test Channel",
            niche="technology",
            timezone="UTC",
            config=_json.dumps(
                {"peak_windows": {"long": {"weekday": [0, 24], "weekend": [0, 24]}}}
            ),
        )

        with (
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPR,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTR,
            patch("app.agents.pipeline_agent.service.VideoRepository") as MockVR,
            patch("app.agents.pipeline_agent.service.UploadRepository") as MockUR,
            patch("app.agents.pipeline_agent.service.ChannelRepository") as MockCR,
        ):
            pr_repo = MockPR.return_value
            pr_repo.update = AsyncMock(return_value=run)
            tr_repo = MockTR.return_value
            tr_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
            vr_repo = MockVR.return_value
            vr_repo.get_by_script_id = AsyncMock(return_value=video)
            ur_repo = MockUR.return_value
            ur_repo.update = AsyncMock(return_value=upload)
            cr_repo = MockCR.return_value
            cr_repo.get_by_id_or_raise = AsyncMock(return_value=channel)

            svc = PipelineAgentService(session)
            svc._generate_script = AsyncMock(return_value=script)
            svc._run_quality_gate = AsyncMock(return_value=True)
            svc._run_seo_gate = AsyncMock(return_value=True)
            svc._render_video = AsyncMock()
            svc._log = AsyncMock()

            before = datetime.now(timezone.utc)
            await svc.run(run)
            after = datetime.now(timezone.utc)

        # Check the Upload object that was added to the session
        assert len(captured_upload) >= 1
        added_upload = captured_upload[0]
        assert added_upload.scheduled_at is not None
        from datetime import timedelta
        expected_min = before + timedelta(minutes=settings.pipeline_publish_delay_minutes - 1)
        expected_max = after + timedelta(minutes=settings.pipeline_publish_delay_minutes + 1)
        assert expected_min <= added_upload.scheduled_at <= expected_max

    async def test_missing_channel_falls_back_to_flat_delay_scheduling(
        self, topic_id, channel_id, script_id, video_id, upload_id, pipeline_run_id
    ):
        """If the channel row is missing (NotFoundError) when scheduling the
        upload, the pipeline must not fail the run -- it should fall back to
        flat-delay scheduling exactly like the pre-peak-scheduling behavior."""
        from app.agents.pipeline_agent.service import PipelineAgentService
        from app.core.config import settings
        from app.core.exceptions import NotFoundError
        from datetime import timedelta

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        topic = _make_topic(topic_id, channel_id)
        script = _make_script(script_id, topic_id, channel_id)
        video = Video(
            id=video_id, script_id=script_id,
            status=VideoStatus.COMPLETE, video_path="/tmp/v.mp4",
        )
        captured_upload: list[Upload] = []
        session.add = MagicMock(side_effect=lambda obj: captured_upload.append(obj) if isinstance(obj, Upload) else None)

        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)
        upload = Upload(
            id=upload_id, video_id=video_id,
            status=UploadStatus.SCHEDULED, publish_status=PublishStatus.SCHEDULED,
        )

        with (
            patch("app.agents.pipeline_agent.service.PipelineRunRepository") as MockPR,
            patch("app.agents.pipeline_agent.service.TopicRepository") as MockTR,
            patch("app.agents.pipeline_agent.service.VideoRepository") as MockVR,
            patch("app.agents.pipeline_agent.service.UploadRepository") as MockUR,
            patch("app.agents.pipeline_agent.service.ChannelRepository") as MockCR,
        ):
            pr_repo = MockPR.return_value
            pr_repo.update = AsyncMock(return_value=run)
            tr_repo = MockTR.return_value
            tr_repo.get_by_id_or_raise = AsyncMock(return_value=topic)
            vr_repo = MockVR.return_value
            vr_repo.get_by_script_id = AsyncMock(return_value=video)
            ur_repo = MockUR.return_value
            ur_repo.update = AsyncMock(return_value=upload)
            cr_repo = MockCR.return_value
            cr_repo.get_by_id_or_raise = AsyncMock(
                side_effect=NotFoundError("Channel", channel_id)
            )

            svc = PipelineAgentService(session)
            svc._generate_script = AsyncMock(return_value=script)
            svc._run_quality_gate = AsyncMock(return_value=True)
            svc._run_seo_gate = AsyncMock(return_value=True)
            svc._render_video = AsyncMock()
            svc._log = AsyncMock()

            before = datetime.now(timezone.utc)
            await svc.run(run)
            after = datetime.now(timezone.utc)

        assert len(captured_upload) >= 1
        added_upload = captured_upload[0]
        assert added_upload.scheduled_at is not None
        expected_min = before + timedelta(minutes=settings.pipeline_publish_delay_minutes - 1)
        expected_max = after + timedelta(minutes=settings.pipeline_publish_delay_minutes + 1)
        assert expected_min <= added_upload.scheduled_at <= expected_max


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------

class TestPipelineRoutes:
    """HTTP tests against the /api/v1/pipeline routes.

    Uses the shared ``client`` fixture (ASGITransport + get_db override).
    Service methods are patched at the class level so no real DB work happens.
    """

    @pytest.mark.asyncio
    async def test_start_pipeline_returns_202(
        self, client, topic_id, channel_id, pipeline_run_id
    ):
        """POST /pipeline/run returns 202 with pipeline_run_id."""
        from app.api.services.pipeline_service import PipelineService

        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)

        with patch.object(PipelineService, "start", new=AsyncMock(return_value=run)):
            resp = await client.post(
                "/api/v1/pipeline/run",
                json={
                    "topic_id": str(topic_id),
                    "channel_id": str(channel_id),
                    "script_type": "long",
                },
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["data"]["id"] == str(pipeline_run_id)
        assert body["data"]["status"] == PipelineStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_get_pipeline_run(
        self, client, topic_id, channel_id, pipeline_run_id
    ):
        """GET /pipeline/{id} returns the run record."""
        from app.api.services.pipeline_service import PipelineService

        run = _make_pipeline_run(
            pipeline_run_id, topic_id, channel_id, status=PipelineStatus.RUNNING
        )
        run.current_stage = "video"

        with patch.object(PipelineService, "get", new=AsyncMock(return_value=run)):
            resp = await client.get(f"/api/v1/pipeline/{pipeline_run_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "running"
        assert body["data"]["current_stage"] == "video"

    @pytest.mark.asyncio
    async def test_start_pipeline_topic_not_found(
        self, client, topic_id, channel_id
    ):
        """POST /pipeline/run with unknown topic returns 404."""
        from app.api.services.pipeline_service import PipelineService
        from app.core.exceptions import NotFoundError

        with patch.object(
            PipelineService,
            "start",
            new=AsyncMock(side_effect=NotFoundError("Topic", topic_id)),
        ):
            resp = await client.post(
                "/api/v1/pipeline/run",
                json={
                    "topic_id": str(topic_id),
                    "channel_id": str(channel_id),
                    "script_type": "long",
                },
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_pipeline_channel_mismatch(
        self, client, topic_id, channel_id
    ):
        """POST /pipeline/run with mismatched channel_id returns 422."""
        from app.api.services.pipeline_service import PipelineService
        from app.core.exceptions import ValidationError

        with patch.object(
            PipelineService,
            "start",
            new=AsyncMock(
                side_effect=ValidationError("channel_id does not match topic")
            ),
        ):
            resp = await client.post(
                "/api/v1/pipeline/run",
                json={
                    "topic_id": str(topic_id),
                    "channel_id": str(channel_id),
                    "script_type": "long",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_pipeline_runs(
        self, client, topic_id, channel_id, pipeline_run_id
    ):
        """GET /pipeline returns list of runs."""
        from app.api.services.pipeline_service import PipelineService

        run = _make_pipeline_run(pipeline_run_id, topic_id, channel_id)

        with patch.object(
            PipelineService, "list_runs", new=AsyncMock(return_value=[run])
        ):
            resp = await client.get("/api/v1/pipeline")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
