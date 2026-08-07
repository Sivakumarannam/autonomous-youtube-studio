"""HTMX Dashboard routes (Phase 5, item 2).

This layer only renders HTML around existing services/repositories — it does
not reimplement any business logic. Pipeline runs are created via
PipelineService.start() (the same service used by the JSON API), and
approve/reject/delete actions call PublishingService (same as the JSON API).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.services.channel_automation_service import ChannelAutomationService
from app.api.services.pipeline_service import PipelineService
from app.api.services.publishing_service import PublishingService
from app.core.config import settings
from app.database.connection import get_db
from app.database.models.channel_automation import AutomationStatus, ChannelAutomation
from app.database.models.upload import UploadStatus
from app.database.repositories.channel_automation_repository import (
    ChannelAutomationRepository,
)
from app.database.repositories.channel_repository import ChannelRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.topic_repository import TopicRepository
from app.database.repositories.upload_repository import UploadRepository
from app.scheduler.scheduler import get_last_tick_info, get_scheduler
from app.web.auth import require_dashboard_auth
from app.web.templates import templates

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])


@router.get("", name="dashboard_index")
async def dashboard_index(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    channels = await ChannelRepository(session).get_all(limit=200)
    topics = await TopicRepository(session).get_all(limit=200)
    runs = await PipelineRunRepository(session).get_latest(limit=20)
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    channel_automations = await _channel_automations_context(session)
    run_stages = {str(run.id): _pipeline_stage_context(run) for run in runs}

    ig_pending = [
        u for u in uploads
        if getattr(u, "instagram_scheduled_at", None)
        and not getattr(u, "instagram_posted", True)
        and not getattr(u, "instagram_failed_permanently", False)
        and getattr(u, "status", None) == UploadStatus.PUBLISHED
    ]
    ig_posted = [
        u for u in uploads
        if getattr(u, "instagram_posted", False)
    ]
    ig_next = min(
        (u.instagram_scheduled_at for u in ig_pending if u.instagram_scheduled_at),
        default=None,
    )

    from app.integrations.instagram_token_store import days_remaining as ig_token_days_remaining
    from app.integrations.youtube_token_store import days_remaining as yt_token_days_remaining

    youtube_configured = bool(
        settings.youtube_client_id
        and settings.youtube_client_secret
        and settings.youtube_refresh_token
    )

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "channels": channels,
            "topics": topics,
            "runs": runs,
            "run_stages": run_stages,
            "uploads": uploads,
            "channel_automations": channel_automations,
            "notification_email_enabled": settings.notification_email_enabled,
            "notification_slack_enabled": settings.notification_slack_enabled,
            "notification_discord_enabled": settings.notification_discord_enabled,
            "notification_telegram_enabled": settings.notification_telegram_enabled,
            "instagram_enabled": settings.instagram_enabled,
            "ig_pending_count": len(ig_pending),
            "ig_posted_count": len(ig_posted),
            "ig_next_scheduled": ig_next,
            "ig_token_days_remaining": ig_token_days_remaining(),
            "youtube_configured": youtube_configured,
            "yt_token_days_remaining": yt_token_days_remaining(),
            "pending_manual_actions": [
                u.youtube_video_id
                for u in uploads
                if getattr(u, "youtube_video_id", None)
                and str(getattr(u, "status", "")) == "published"
            ][:5],
            **_scheduler_context(),
        },
    )


@router.get("/partials/pipeline-runs")
async def pipeline_runs_partial(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    runs = await PipelineRunRepository(session).get_latest(limit=20)
    run_stages = {str(run.id): _pipeline_stage_context(run) for run in runs}
    return templates.TemplateResponse(
        request,
        "dashboard/_pipeline_runs.html",
        {"runs": runs, "run_stages": run_stages},
    )


@router.get("/partials/queue")
async def queue_partial(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request, "dashboard/_queue.html", {"uploads": uploads}
    )


@router.get("/partials/scheduler-status")
async def scheduler_status_partial(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard/_scheduler_status.html",
        _scheduler_context(),
    )


@router.get("/partials/channel-automation")
async def channel_automation_partial(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    channel_automations = await _channel_automations_context(session)
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_automation.html",
        {"channel_automations": channel_automations},
    )


@router.get("/partials/uploaded-videos")
async def uploaded_videos_partial(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
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


@router.post("/publishing/{upload_id}/approve", name="dashboard_approve_upload")
async def approve_upload(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    svc = PublishingService(session)
    await svc.approve(upload_id)
    await session.commit()
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request, "dashboard/_queue.html", {"uploads": uploads}
    )


@router.post("/publishing/{upload_id}/reject", name="dashboard_reject_upload")
async def reject_upload(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    svc = PublishingService(session)
    await svc.reject(upload_id, reason="Rejected via dashboard.")
    await session.commit()
    uploads = await UploadRepository(session).get_all_by_status(limit=50)
    return templates.TemplateResponse(
        request, "dashboard/_queue.html", {"uploads": uploads}
    )


@router.post("/uploads/{upload_id}/delete")
async def delete_upload_everywhere(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    from app.integrations.youtube.exceptions import YouTubeVideoNotFoundError

    svc = PublishingService(session)
    try:
        await svc.delete_video_everywhere(upload_id)
    except YouTubeVideoNotFoundError:
        await session.rollback()
        return templates.TemplateResponse(
            request,
            "dashboard/_confirm_already_deleted.html",
            {"upload_id": str(upload_id)},
        )
    await session.commit()
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


@router.post("/uploads/{upload_id}/delete-local")
async def delete_upload_local_only(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    svc = PublishingService(session)
    await svc.delete_local_only(upload_id)
    await session.commit()
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


@router.post("/pipeline-runs/{run_id}/delete")
async def delete_pipeline_run(
    run_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    svc = PipelineService(session)
    await svc.delete_run(run_id)
    await session.commit()
    runs = await PipelineRunRepository(session).get_latest(limit=20)
    run_stages = {str(run.id): _pipeline_stage_context(run) for run in runs}
    return templates.TemplateResponse(
        request,
        "dashboard/_pipeline_runs.html",
        {"runs": runs, "run_stages": run_stages},
    )


@router.post("/pipeline-runs/{run_id}/retry")
async def retry_pipeline_run(
    run_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    svc = PipelineService(session)
    await svc.retry_run(run_id, background_tasks=background_tasks)
    await session.commit()
    runs = await PipelineRunRepository(session).get_latest(limit=20)
    run_stages = {str(run.id): _pipeline_stage_context(run) for run in runs}
    return templates.TemplateResponse(
        request,
        "dashboard/_pipeline_runs.html",
        {"runs": runs, "run_stages": run_stages},
    )


@router.post("/channels/{channel_id}/automation/start")
async def start_automation(
    channel_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await ChannelAutomationService(session).start(channel_id)
    await session.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_automation.html",
        {"channel_automations": await _channel_automations_context(session)},
    )


@router.post("/channels/{channel_id}/automation/pause")
async def pause_automation(
    channel_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await ChannelAutomationService(session).pause(channel_id)
    await session.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_automation.html",
        {"channel_automations": await _channel_automations_context(session)},
    )


@router.post("/channels/{channel_id}/automation/delete")
async def delete_automation(
    channel_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    await ChannelAutomationService(session).delete(channel_id)
    await session.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_automation.html",
        {"channel_automations": await _channel_automations_context(session)},
    )


@router.post("/channels/{channel_id}/automation/reset")
async def reset_channel(
    channel_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    result = await ChannelAutomationService(session).reset_channel(channel_id)
    await session.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/_channel_reset_result.html",
        {
            "result": result,
            "channel_automations": await _channel_automations_context(session),
        },
    )


@router.post("/pipeline/run")
async def trigger_pipeline_run(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    form = await request.form()
    topic_id = UUID(str(form["topic_id"]))
    channel_id = UUID(str(form["channel_id"]))
    script_type = str(form.get("script_type", "long"))
    svc = PipelineService(session)
    await svc.start(
        topic_id=topic_id,
        channel_id=channel_id,
        script_type=script_type,
        background_tasks=background_tasks,
    )
    await session.commit()
    runs = await PipelineRunRepository(session).get_latest(limit=20)
    run_stages = {str(run.id): _pipeline_stage_context(run) for run in runs}
    return templates.TemplateResponse(
        request,
        "dashboard/_pipeline_runs.html",
        {"runs": runs, "run_stages": run_stages},
    )


_PIPELINE_STAGES = [
    "script", "quality", "seo", "voice", "video", "upload", "analytics",
]


def _pipeline_stage_context(run) -> list[dict]:
    is_complete = str(getattr(run.status, "value", run.status)) == "complete"
    failed_stage = run.failed_stage or ""
    current_stage = run.current_stage or ""
    current_idx = (
        _PIPELINE_STAGES.index(current_stage)
        if current_stage in _PIPELINE_STAGES else -1
    )
    failed_idx = (
        _PIPELINE_STAGES.index(failed_stage)
        if failed_stage in _PIPELINE_STAGES else -1
    )
    effective_done_boundary = current_idx if current_idx >= 0 else failed_idx
    _icons = {"done": "✓", "active": "…", "failed": "✕", "pending": "○"}
    stages = []
    for i, name in enumerate(_PIPELINE_STAGES):
        if is_complete:
            state = "done"
        elif name == failed_stage:
            state = "failed"
        elif effective_done_boundary >= 0 and i < effective_done_boundary:
            state = "done"
        elif name == current_stage:
            state = "active"
        else:
            state = "pending"
        stages.append({"name": name, "state": state, "icon": _icons[state]})
    return stages


async def _channel_automations_context(session: AsyncSession) -> list[dict]:
    channels = await ChannelRepository(session).get_all(limit=200)
    automation_repo = ChannelAutomationRepository(session)
    service = ChannelAutomationService(session)
    rows: list[dict] = []
    for channel in channels:
        automation = await automation_repo.get_by_channel_id(channel.id)
        if automation is None:
            continue
        response = service._to_response(automation)
        rows.append(
            {
                "channel": channel,
                "automation": response,
                "phase": response.phase,
                "next_long": response.next_expected_long_video_date,
            }
        )
    return rows


def _scheduler_context() -> dict:
    next_run_at = None
    try:
        job = get_scheduler()._scheduler.get_job("publish_due_videos")
        if job and job.next_run_time:
            next_run_at = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return {
        "interval_minutes": settings.scheduler_interval_minutes,
        "next_run_at": next_run_at,
        "last_tick": get_last_tick_info(),
    }


@router.post("/notifications/test")
async def test_notifications(request: Request):
    from app.notifications.service import notify
    try:
        await notify(
            title="🔔 YouTube Studio — Test Notification",
            body="This is a test message from your Autonomous YouTube Studio dashboard.",
            level="info",
            extra={"Triggered by": "Dashboard → Test All button"},
        )
        return templates.TemplateResponse(
            request,
            "dashboard/_toast.html",
            {"message": "Test notification sent to all enabled channels ✅"},
            status_code=200,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "dashboard/_toast.html",
            {"message": f"Notification failed: {exc}", "error": True},
            status_code=200,
        )


@router.post("/instagram/refresh-token")
async def refresh_instagram_token(request: Request):
    from app.scheduler.instagram_token_watchdog import get_instagram_token_watchdog
    watchdog = get_instagram_token_watchdog()
    success, message, expires_in = await watchdog.manual_refresh()
    if success:
        return templates.TemplateResponse(
            request,
            "dashboard/_instagram_refresh_result.html",
            {
                "success": True,
                "expires_in_days": (expires_in // 86400) if expires_in else 60,
                "auto_hide_seconds": 20,
            },
        )
    return templates.TemplateResponse(
        request,
        "dashboard/_instagram_refresh_result.html",
        {
            "success": False,
            "instructions": watchdog.manual_refresh_instructions(message),
            "auto_hide_seconds": 600,
        },
    )


@router.post("/youtube/refresh-token")
async def refresh_youtube_token(request: Request):
    """Verify YouTube refresh token (dashboard button)."""
    from app.scheduler.youtube_token_watchdog import get_youtube_token_watchdog
    from app.integrations.youtube_token_store import days_remaining

    watchdog = get_youtube_token_watchdog()
    success, message = await watchdog.manual_refresh()

    if success:
        return templates.TemplateResponse(
            request,
            "dashboard/_youtube_refresh_result.html",
            {
                "success": True,
                "days_remaining": days_remaining(),
                "auto_hide_seconds": 20,
            },
        )
    return templates.TemplateResponse(
        request,
        "dashboard/_youtube_refresh_result.html",
        {
            "success": False,
            "instructions": watchdog.reauth_instructions(message),
            "auto_hide_seconds": 600,
        },
    )
