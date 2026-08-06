"""HTMX Dashboard routes (Phase 5, item 2).

This layer only renders HTML around existing services/repositories — it does
not reimplement any business logic. Pipeline runs are created via
PipelineService.start() (the same service used by the JSON API).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services.pipeline_service import PipelineService
from app.api.services.publishing_service import PublishingService
from app.core.logging import get_logger
from app.database.connection import get_db
from app.database.models.upload import UploadStatus
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.topic_repository import TopicRepository
from app.database.repositories.upload_repository import UploadRepository
from app.web.auth import require_dashboard_auth
from app.web.templates import templates

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])

# NOTE: Full dashboard route set restored for publish-UX.
# Core partials used by the live dashboard are included below.


@router.get("")
async def dashboard_index(request: Request, session: AsyncSession = Depends(get_db)):
    from app.scheduler.scheduler import get_scheduler

    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "uploads": uploads,
            "now": datetime.now(timezone.utc),
        },
    )


@router.get("/partials/uploaded-videos")
async def uploaded_videos_partial(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    upload_repo = UploadRepository(session)
    uploaded_videos = await upload_repo.get_dashboard_videos(limit=20)
    return templates.TemplateResponse(
        request,
        "dashboard/_uploaded_videos.html",
        {
            "uploaded_videos": uploaded_videos,
            "now": datetime.now(timezone.utc),
        },
    )


@router.get("/partials/queue")
async def queue_partial(request: Request, session: AsyncSession = Depends(get_db)):
    from app.database.repositories.pipeline_run_repository import PipelineRunRepository

    runs = await PipelineRunRepository(session).get_recent(limit=20)
    return templates.TemplateResponse(
        request,
        "dashboard/_queue.html",
        {"runs": runs, "now": datetime.now(timezone.utc)},
    )


@router.get("/partials/pipeline-runs")
async def pipeline_runs_partial(
    request: Request, session: AsyncSession = Depends(get_db)
):
    runs = await PipelineRunRepository(session).get_recent(limit=30)
    return templates.TemplateResponse(
        request,
        "dashboard/_pipeline_runs.html",
        {"pipeline_runs": runs, "now": datetime.now(timezone.utc)},
    )


@router.get("/partials/scheduler-status")
async def scheduler_status_partial(request: Request):
    from app.scheduler.scheduler import get_scheduler

    job = get_scheduler()._scheduler.get_job("publish_due_videos")
    next_run = job.next_run_time if job else None
    return templates.TemplateResponse(
        request,
        "dashboard/_scheduler_status.html",
        {
            "next_run": next_run,
            "now": datetime.now(timezone.utc),
        },
    )


@router.get("/partials/channel-automation")
async def channel_automation_partial(
    request: Request, session: AsyncSession = Depends(get_db)
):
    channels = await ChannelRepository(session).get_all(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_automation.html",
        {"channels": channels, "now": datetime.now(timezone.utc)},
    )


@router.post("/uploads/{upload_id}/delete")
async def delete_upload(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    upload_repo = UploadRepository(session)
    upload = await upload_repo.get_or_raise(upload_id)
    await upload_repo.delete_upload(upload)
    uploaded_videos = await upload_repo.get_dashboard_videos(limit=20)
    return templates.TemplateResponse(
        request,
        "dashboard/_uploaded_videos.html",
        {
            "uploaded_videos": uploaded_videos,
            "now": datetime.now(timezone.utc),
        },
    )


@router.post("/publishing/{upload_id}/approve", name="dashboard_approve_upload")
async def approve_upload(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await PublishingService(session).approve(upload_id)
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {"uploads": uploads, "now": datetime.now(timezone.utc)},
    )


@router.post("/publishing/{upload_id}/reject", name="dashboard_reject_upload")
async def reject_upload(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await PublishingService(session).reject(upload_id)
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {"uploads": uploads, "now": datetime.now(timezone.utc)},
    )
