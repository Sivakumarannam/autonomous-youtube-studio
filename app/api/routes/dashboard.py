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


# -------------------------
# DASHBOARD PAGE
# -------------------------
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

    # Instagram queue stats
    ig_pending = [
        u for u in uploads
        if getattr(u, "instagram_scheduled_at", None)
        and not getattr(u, "instagram_posted", True)
        and str(getattr(u, "status", "")) == "published"
    ]
    ig_posted = [
        u for u in uploads
        if getattr(u, "instagram_posted", False)
    ]
    ig_next = min(
        (u.instagram_scheduled_at for u in ig_pending if u.instagram_scheduled_at),
        default=None,
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
            # Notification channel status for the dashboard panel
            "notification_email_enabled": settings.notification_email_enabled,
            "notification_slack_enabled": settings.notification_slack_enabled,
            "notification_discord_enabled": settings.notification_discord_enabled,
            "notification_telegram_enabled": settings.notification_telegram_enabled,
            "instagram_enabled": settings.instagram_enabled,
            # Instagram queue metrics
            "ig_pending_count": len(ig_pending),
            "ig_posted_count": len(ig_posted),
            "ig_next_scheduled": ig_next,
            # Recent published uploads that need manual YouTube Studio actions
            "pending_manual_actions": [
                u.youtube_video_id
                for u in uploads
                if getattr(u, "youtube_video_id", None)
                and str(getattr(u, "status", "")) == "published"
            ][:5],
            **_scheduler_context(),
        },
    )


# -------------------------
# PARTIALS
# -------------------------
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

    # Get published uploads with their related video/script info
    uploaded_videos = await upload_repo.get_published_videos(limit=15)

    return templates.TemplateResponse(
        request,
        "dashboard/_uploaded_videos.html",
        {
            "uploaded_videos": uploaded_videos,
            "now": datetime.now(timezone.utc),
        },
    )


# -------------------------
# PUBLISHING ACTIONS (approve / reject)
# -------------------------
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


# -------------------------
# DELETE ACTIONS (YouTube + local, and local-only)
# -------------------------
@router.post("/uploads/{upload_id}/delete")
async def delete_upload_everywhere(
    upload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Delete a video from YouTube AND this dashboard. Irreversible.

    If YouTube reports the video was already deleted externally
    (404 videoNotFound), the local record is NOT touched — instead a
    confirmation dialog is returned asking the user whether to also
    remove the now-orphaned local record.
    """
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
    uploaded_videos = await upload_repo.get_published_videos(limit=15)

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
    """Remove only the local Upload record — used after the user confirms
    the video was already deleted directly on YouTube. No YouTube API call.
    """
    from datetime import datetime, timezone

    svc = PublishingService(session)
    await svc.delete_local_only(upload_id)
    await session.commit()

    upload_repo = UploadRepository(session)
    uploaded_videos = await upload_repo.get_published_videos(limit=15)

    return templates.TemplateResponse(
        request,
        "dashboard/_uploaded_videos.html",
        {
            "uploaded_videos": uploaded_videos,
            "now": datetime.now(timezone.utc),
        },
    )


# -------------------------
# PIPELINE RUN — delete (dashboard-only) & retry (self-heal)
# -------------------------
@router.post("/pipeline-runs/{run_id}/delete")
async def delete_pipeline_run(
    run_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Remove a PipelineRun row from the dashboard only — never calls
    YouTube. If that run already published a video, the video and its
    Upload record are untouched; use the Uploads delete action for that."""
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
    """Self-heal a failed or stuck pipeline run: starts a fresh attempt
    for the same topic/channel/script_type. Does not resume mid-stage —
    the pipeline doesn't support that — this creates a new run instead."""
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


# -------------------------
# AUTOMATION ACTIONS
# -------------------------
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
    """HARD RESET — irreversible. Deletes every PipelineRun/Script/Video/
    Upload for this channel AND deletes every matching video from YouTube
    itself. The Channel and its Topics are left alone. Unlike the archive
    action above, this does not preserve history."""
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


# -------------------------
# PIPELINE RUN
# -------------------------
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


# -------------------------
# HELPERS
# -------------------------

# Ordered pipeline stages shown in the stepper (must match the values written
# to PipelineRun.current_stage / PipelineRun.failed_stage in the service).
_PIPELINE_STAGES = [
    "script",
    "quality",
    "seo",
    "voice",
    "video",
    "upload",
    "analytics",
]


def _pipeline_stage_context(run) -> list[dict]:
    """Return a list of stage dicts (name, state, icon) for the stepper UI.

    State is one of: "done" | "active" | "failed" | "pending".
    When the run is COMPLETE every stage is "done".

    For failed runs (current_stage=None, failed_stage set) we infer completed
    stages from the failed_stage position: every stage before the failed one
    is marked "done" since the pipeline ran through them successfully.
    """
    is_complete = str(getattr(run.status, "value", run.status)) == "complete"
    failed_stage = run.failed_stage or ""
    current_stage = run.current_stage or ""

    current_idx = (
        _PIPELINE_STAGES.index(current_stage)
        if current_stage in _PIPELINE_STAGES
        else -1
    )
    failed_idx = (
        _PIPELINE_STAGES.index(failed_stage)
        if failed_stage in _PIPELINE_STAGES
        else -1
    )

    # For failed runs where current_stage is cleared, use the failed_stage
    # position to determine which prior stages completed successfully.
    effective_done_boundary = current_idx if current_idx >= 0 else failed_idx

    _icons = {
        "done": "✓",
        "active": "…",
        "failed": "✕",
        "pending": "○",
    }

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
    """Fetch channel automations for display in dashboard.

    IMPORTANT: This is a GET context. We NEVER write to the database here.
    If an automation doesn't exist, we skip the channel (don't show it in the UI).
    Automations must be created via explicit API calls, not implicitly during GET.
    """
    channels = await ChannelRepository(session).get_all(limit=200)
    automation_repo = ChannelAutomationRepository(session)
    service = ChannelAutomationService(session)

    rows: list[dict] = []

    for channel in channels:
        automation = await automation_repo.get_by_channel_id(channel.id)

        # If no automation exists in DB, skip this channel (don't show it).
        # Automations are created via explicit API calls only.
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


# -------------------------
# NOTIFICATION TEST
# -------------------------
@router.post("/notifications/test")
async def test_notifications(request: Request):
    """Fire a test message to every enabled notification channel."""
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