"""Targeted tests for Phase 5 dashboard/websocket/metrics additions.

These only cover the new surface area (HTMX dashboard routes, WebSocket
endpoint wiring, and the /metrics endpoint). They reuse the shared
``client``/DB fixtures from tests/conftest.py and the existing
create_test_channel/create_test_topic helpers — no new business logic is
exercised beyond what PipelineService/PublishingService already own.
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import create_test_channel, create_test_topic


class TestDashboardPages:
    @pytest.mark.asyncio
    async def test_dashboard_index_renders(self, client, test_session):
        await create_test_channel(test_session)
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Autonomous YouTube Studio" in resp.text
        assert "Trigger New Pipeline Run" in resp.text

    @pytest.mark.asyncio
    async def test_pipeline_runs_partial_renders_empty_state(self, client):
        resp = await client.get("/dashboard/partials/pipeline-runs")
        assert resp.status_code == 200
        assert "No pipeline runs yet." in resp.text

    @pytest.mark.asyncio
    async def test_queue_partial_renders_empty_state(self, client):
        resp = await client.get("/dashboard/partials/queue")
        assert resp.status_code == 200
        assert "No uploads yet." in resp.text

    @pytest.mark.asyncio
    async def test_channel_automation_partial_shows_archived_channel_with_start_action(
        self, client, test_session
    ):
        from app.api.services.channel_automation_service import ChannelAutomationService

        channel = await create_test_channel(test_session)
        service = ChannelAutomationService(test_session)

        await service.start(channel.id)
        await service.delete(channel.id)
        await test_session.commit()

        resp = await client.get("/dashboard/partials/channel-automation")

        assert resp.status_code == 200
        assert channel.name in resp.text
        assert "Start" in resp.text

    @pytest.mark.asyncio
    async def test_scheduler_status_partial_renders(self, client):
        resp = await client.get("/dashboard/partials/scheduler-status")
        assert resp.status_code == 200
        assert "Scheduler Status" in resp.text


class TestDashboardActions:
    @pytest.mark.asyncio
    async def test_start_triggers_immediate_scheduler_processing(self, test_session):
        from app.api.services.channel_automation_service import ChannelAutomationService

        channel = await create_test_channel(test_session)
        service = ChannelAutomationService(test_session)

        fake_scheduler = type("FakeScheduler", (), {})()
        fake_scheduler._process_channel = AsyncMock()

        with patch(
            "asyncio.create_task",
            side_effect=lambda coro: coro.close() or None,
        ) as mock_create_task, patch(
            "app.scheduler.automation_scheduler.get_automation_scheduler",
            return_value=fake_scheduler,
        ):
            await service.start(channel.id)

        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_clears_last_run_date_for_immediate_processing(self, test_session):
        from app.api.services.channel_automation_service import ChannelAutomationService
        from app.database.models.channel_automation import ChannelAutomation

        channel = await create_test_channel(test_session)
        service = ChannelAutomationService(test_session)

        automation = ChannelAutomation(
            channel_id=channel.id,
            automation_status="stopped",
            last_run_date=date.today(),
        )
        test_session.add(automation)
        await test_session.commit()

        with patch(
            "asyncio.create_task",
            side_effect=lambda coro: coro.close() or None,
        ):
            await service.start(channel.id)

        await test_session.refresh(automation)
        assert automation.last_run_date is None

    @pytest.mark.asyncio
    async def test_trigger_pipeline_run_calls_pipeline_service(
        self, client, test_session
    ):
        from app.api.services.pipeline_service import PipelineService
        from app.database.models.pipeline_run import PipelineRun, PipelineStatus

        channel = await create_test_channel(test_session)
        topic = await create_test_topic(test_session, channel.id)

        run = PipelineRun(
            id=uuid.uuid4(),
            topic_id=topic.id,
            channel_id=channel.id,
            script_type="long",
            status=PipelineStatus.PENDING,
        )

        with patch.object(
            PipelineService, "start", new=AsyncMock(return_value=run)
        ) as mock_start:
            resp = await client.post(
                "/dashboard/pipeline/run",
                data={
                    "channel_id": str(channel.id),
                    "topic_id": str(topic.id),
                    "script_type": "long",
                },
            )

        assert resp.status_code == 200
        mock_start.assert_awaited_once()
        assert mock_start.await_args.kwargs["topic_id"] == topic.id
        assert mock_start.await_args.kwargs["channel_id"] == channel.id
        assert mock_start.await_args.kwargs["script_type"] == "long"

    @pytest.mark.asyncio
    async def test_approve_upload_calls_publishing_service(self, client):
        from app.api.services.publishing_service import PublishingService
        from app.database.models.upload import Upload, UploadStatus, PublishStatus

        upload_id = uuid.uuid4()
        upload = Upload(
            id=upload_id,
            video_id=uuid.uuid4(),
            status=UploadStatus.PENDING,
            publish_status=PublishStatus.APPROVED,
        )

        with patch.object(
            PublishingService, "approve", new=AsyncMock(return_value=upload)
        ) as mock_approve:
            resp = await client.post(f"/dashboard/publishing/{upload_id}/approve")

        assert resp.status_code == 200
        mock_approve.assert_awaited_once_with(upload_id)

    @pytest.mark.asyncio
    async def test_reject_upload_calls_publishing_service(self, client):
        from app.api.services.publishing_service import PublishingService
        from app.database.models.upload import Upload, UploadStatus, PublishStatus

        upload_id = uuid.uuid4()
        upload = Upload(
            id=upload_id,
            video_id=uuid.uuid4(),
            status=UploadStatus.PENDING,
            publish_status=PublishStatus.REJECTED,
        )

        with patch.object(
            PublishingService, "reject", new=AsyncMock(return_value=upload)
        ) as mock_reject:
            resp = await client.post(f"/dashboard/publishing/{upload_id}/reject")

        assert resp.status_code == 200
        mock_reject.assert_awaited_once()
        assert mock_reject.await_args.args[0] == upload_id


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_exposes_prometheus_text(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "python_gc_objects_collected_total" in resp.text
        assert "pipeline_runs_total" in resp.text
        assert "scheduler_ticks_total" in resp.text
        assert "http_request_duration_seconds" in resp.text


class TestWebSocketManager:
    @pytest.mark.asyncio
    async def test_connection_manager_broadcast_delivers_to_connected_clients(self):
        from app.websocket.manager import ConnectionManager

        manager = ConnectionManager()

        class FakeWebSocket:
            def __init__(self):
                self.sent: list[str] = []

            async def accept(self):
                pass

            async def send_text(self, data: str):
                self.sent.append(data)

        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.broadcast({"type": "pipeline_update", "id": "abc"})

        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        assert "pipeline_update" in ws1.sent[0]

        manager.disconnect(ws1)
        await manager.broadcast({"type": "scheduler_tick"})
        assert len(ws1.sent) == 1  # unchanged, disconnected
        assert len(ws2.sent) == 2

    @pytest.mark.asyncio
    async def test_broadcast_safe_swallows_errors(self):
        from app.websocket.manager import broadcast_safe

        with patch(
            "app.websocket.manager.get_connection_manager",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise even though the underlying broadcast fails.
            await broadcast_safe({"type": "x"})