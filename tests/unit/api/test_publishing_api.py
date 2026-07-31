"""Unit tests for the Publishing Workflow API (Stage 2).

Covers:
  - Legal publish_status transitions (reject, schedule)
  - Illegal transitions raise PublishError → 409
  - Route-level HTTP tests
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database.models.upload import Upload, UploadStatus, PublishStatus
from app.core.exceptions import PublishError, NotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_upload(
    upload_id=None,
    video_id=None,
    publish_status=PublishStatus.APPROVED,
    upload_status=UploadStatus.SCHEDULED,
    scheduled_at=None,
):
    return Upload(
        id=upload_id or uuid.uuid4(),
        video_id=video_id or uuid.uuid4(),
        title="AI in 2026",
        description="Full description.",
        tags='["ai", "tech"]',
        privacy_status="public",
        status=upload_status,
        publish_status=publish_status,
        scheduled_at=scheduled_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# PublishingService unit tests
# ---------------------------------------------------------------------------

class TestPublishingServiceTransitions:

    @pytest.mark.asyncio
    async def test_reject_approved_upload(self):
        """APPROVED → REJECTED is a legal transition."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, publish_status=PublishStatus.APPROVED)

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)
            rejected = _make_upload(upload_id=upload_id, publish_status=PublishStatus.REJECTED)
            repo.update = AsyncMock(return_value=rejected)

            svc = PublishingService(session)
            result = await svc.reject(upload_id, reason="Bad render quality.")

        assert result.publish_status == PublishStatus.REJECTED
        repo.update.assert_awaited_once()
        call_kwargs = repo.update.await_args.kwargs
        assert call_kwargs["publish_status"] == PublishStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_scheduled_upload(self):
        """SCHEDULED → REJECTED is legal (safety window rejection)."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id,
            publish_status=PublishStatus.SCHEDULED,
            upload_status=UploadStatus.SCHEDULED,
        )

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)
            rejected = _make_upload(upload_id=upload_id, publish_status=PublishStatus.REJECTED)
            repo.update = AsyncMock(return_value=rejected)

            svc = PublishingService(session)
            result = await svc.reject(upload_id, reason="Noticed a mistake.")

        assert result.publish_status == PublishStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_draft_raises_publish_error(self):
        """DRAFT → REJECTED is not a legal transition from the API."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id, publish_status=PublishStatus.DRAFT
        )

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)

            svc = PublishingService(session)
            with pytest.raises(PublishError) as exc_info:
                await svc.reject(upload_id)

        assert "draft" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_reject_published_upload_raises_publish_error(self):
        """Cannot reject a video that has already been published to YouTube."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        # publish_status=SCHEDULED but upload_status=PUBLISHED (already live)
        upload = _make_upload(
            upload_id=upload_id,
            publish_status=PublishStatus.SCHEDULED,
            upload_status=UploadStatus.PUBLISHED,
        )

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)

            svc = PublishingService(session)
            with pytest.raises(PublishError) as exc_info:
                await svc.reject(upload_id)

        assert "published" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_schedule_approved_upload(self):
        """APPROVED → SCHEDULED with a future scheduled_at."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id, publish_status=PublishStatus.APPROVED
        )
        future = datetime.now(timezone.utc) + timedelta(hours=2)

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)
            scheduled = _make_upload(
                upload_id=upload_id,
                publish_status=PublishStatus.SCHEDULED,
                scheduled_at=future,
            )
            repo.update = AsyncMock(return_value=scheduled)

            svc = PublishingService(session)
            result = await svc.schedule(upload_id, scheduled_at=future)

        assert result.publish_status == PublishStatus.SCHEDULED
        call_kwargs = repo.update.await_args.kwargs
        assert call_kwargs["publish_status"] == PublishStatus.SCHEDULED
        assert call_kwargs["scheduled_at"] == future

    @pytest.mark.asyncio
    async def test_schedule_draft_raises_publish_error(self):
        """DRAFT → SCHEDULED is not a legal transition."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id, publish_status=PublishStatus.DRAFT
        )
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)

            svc = PublishingService(session)
            with pytest.raises(PublishError):
                await svc.schedule(upload_id, scheduled_at=future)

    @pytest.mark.asyncio
    async def test_approve_draft_upload(self):
        """DRAFT → APPROVED is the legal manual-approval transition."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(
            upload_id=upload_id,
            publish_status=PublishStatus.DRAFT,
            upload_status=UploadStatus.SCHEDULED,
        )

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)
            approved = _make_upload(upload_id=upload_id, publish_status=PublishStatus.APPROVED)
            repo.update = AsyncMock(return_value=approved)

            svc = PublishingService(session)
            result = await svc.approve(upload_id)

        assert result.publish_status == PublishStatus.APPROVED
        call_kwargs = repo.update.await_args.kwargs
        assert call_kwargs["publish_status"] == PublishStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_already_approved_raises_publish_error(self):
        """APPROVED → APPROVED is not a legal transition."""
        from app.api.services.publishing_service import PublishingService

        session = AsyncMock()
        upload_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, publish_status=PublishStatus.APPROVED)

        with patch("app.api.services.publishing_service.UploadRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_or_raise = AsyncMock(return_value=upload)

            svc = PublishingService(session)
            with pytest.raises(PublishError):
                await svc.approve(upload_id)


# ---------------------------------------------------------------------------
# Route-level HTTP tests
# ---------------------------------------------------------------------------

class TestPublishingRoutes:
    """HTTP tests against /api/v1/publishing routes.

    Uses the shared ``client`` fixture so get_db is overridden with the
    in-memory test session. Service methods are patched at class level.
    """

    @pytest.mark.asyncio
    async def test_get_upload(self, client):
        """GET /publishing/{id} returns upload with publish_status."""
        from app.api.services.publishing_service import PublishingService

        upload_id = uuid.uuid4()
        upload = _make_upload(upload_id=upload_id, publish_status=PublishStatus.APPROVED)

        with patch.object(PublishingService, "get", new=AsyncMock(return_value=upload)):
            resp = await client.get(f"/api/v1/publishing/{upload_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["publish_status"] == "approved"

    @pytest.mark.asyncio
    async def test_reject_upload_route(self, client):
        """POST /publishing/{id}/reject → 200 with rejected status."""
        from app.api.services.publishing_service import PublishingService

        upload_id = uuid.uuid4()
        rejected = _make_upload(
            upload_id=upload_id, publish_status=PublishStatus.REJECTED
        )

        with patch.object(
            PublishingService, "reject", new=AsyncMock(return_value=rejected)
        ):
            resp = await client.post(
                f"/api/v1/publishing/{upload_id}/reject",
                json={"reason": "Spotted render glitch."},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["publish_status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_upload_illegal_transition_returns_409(self, client):
        """Illegal transitions return 409 Conflict."""
        from app.api.services.publishing_service import PublishingService

        upload_id = uuid.uuid4()

        with patch.object(
            PublishingService,
            "reject",
            new=AsyncMock(
                side_effect=PublishError("Cannot transition DRAFT → REJECTED")
            ),
        ):
            resp = await client.post(
                f"/api/v1/publishing/{upload_id}/reject",
                json={},
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_schedule_upload_route(self, client):
        """POST /publishing/{id}/schedule → 200 with scheduled status."""
        from app.api.services.publishing_service import PublishingService

        upload_id = uuid.uuid4()
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        scheduled = _make_upload(
            upload_id=upload_id,
            publish_status=PublishStatus.SCHEDULED,
            scheduled_at=future,
        )

        with patch.object(
            PublishingService, "schedule", new=AsyncMock(return_value=scheduled)
        ):
            resp = await client.post(
                f"/api/v1/publishing/{upload_id}/schedule",
                json={"scheduled_at": future.isoformat()},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["publish_status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_list_uploads_with_publish_status_filter(self, client):
        """GET /publishing?publish_status=scheduled returns filtered list."""
        from app.api.services.publishing_service import PublishingService

        upload = _make_upload(publish_status=PublishStatus.SCHEDULED)

        with patch.object(
            PublishingService,
            "list_uploads",
            new=AsyncMock(return_value=[upload]),
        ):
            resp = await client.get("/api/v1/publishing?publish_status=scheduled")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["publish_status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_get_upload_not_found(self, client):
        """GET /publishing/{unknown_id} returns 404."""
        from app.api.services.publishing_service import PublishingService

        upload_id = uuid.uuid4()

        with patch.object(
            PublishingService,
            "get",
            new=AsyncMock(side_effect=NotFoundError("Upload", upload_id)),
        ):
            resp = await client.get(f"/api/v1/publishing/{upload_id}")

        assert resp.status_code == 404