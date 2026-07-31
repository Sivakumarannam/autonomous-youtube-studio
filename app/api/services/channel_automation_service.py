"""Channel Automation API Service (Phase 6).

Thin, repository-pattern service backing the four user-facing dashboard
endpoints (start/pause/delete/get). Starts the immediate automation pass when
channel automation is turned on so the user sees pipeline activity without
waiting for the next scheduler interval.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.channel_automation import ChannelAutomationResponse
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.database.models.channel_automation import AutomationStatus, ChannelAutomation
from app.database.repositories.channel_automation_repository import (
    ChannelAutomationRepository,
)
from app.database.repositories.channel_repository import ChannelRepository

logger = get_logger(__name__)


class ChannelAutomationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._automation_repo = ChannelAutomationRepository(session)
        self._channel_repo = ChannelRepository(session)

    async def start(self, channel_id: UUID) -> ChannelAutomationResponse:
        channel = await self._channel_repo.get_by_id(channel_id)
        if channel is None:
            raise NotFoundError("Channel", channel_id)

        if channel.is_archived:
            channel = await self._channel_repo.update(channel, is_archived=False)
            logger.info(
                "Channel automation resumed by unarchiving channel.",
                channel_id=str(channel_id),
            )

        automation = await self._automation_repo.get_by_channel_id(channel_id)
        now = datetime.now(timezone.utc)

        if automation is None:
            automation = ChannelAutomation(
                channel_id=channel_id,
                automation_status=AutomationStatus.RUNNING,
                started_at=now,
            )
            automation = await self._automation_repo.create(automation)
        else:
            update_kwargs: dict = {
                "automation_status": AutomationStatus.RUNNING,
                "paused_at": None,
                "last_run_date": None,
            }
            if automation.started_at is None:
                update_kwargs["started_at"] = now
            automation = await self._automation_repo.update(automation, **update_kwargs)

        await self._session.commit()

        logger.info(
            "Channel automation started.",
            channel_id=str(channel_id),
            cumulative_active_days=automation.cumulative_active_days,
        )

        try:
            from app.scheduler.automation_scheduler import get_automation_scheduler

            scheduler = get_automation_scheduler()
            asyncio.create_task(scheduler._process_channel(channel_id))
            logger.info(
                "Queued immediate automation processing for channel.",
                channel_id=str(channel_id),
            )
        except Exception as exc:
            logger.warning(
                "Failed to queue immediate automation processing.",
                channel_id=str(channel_id),
                error=str(exc),
            )

        return self._to_response(automation)

    async def pause(self, channel_id: UUID) -> ChannelAutomationResponse:
        automation = await self._get_or_raise(channel_id)
        automation = await self._automation_repo.update(
            automation,
            automation_status=AutomationStatus.PAUSED,
            paused_at=datetime.now(timezone.utc),
        )
        logger.info("Channel automation paused.", channel_id=str(channel_id))
        return self._to_response(automation)

    async def delete(self, channel_id: UUID) -> ChannelAutomationResponse:
        """Soft delete/archive: stops automation and hides the channel.

        Does NOT delete any Topics/Scripts/Videos/Uploads/PipelineRuns/
        Analytics — all historical data is preserved. A separate, explicit
        hard-delete admin operation is out of scope for this task.
        """
        channel = await self._channel_repo.get_by_id_or_raise(channel_id)
        automation = await self._automation_repo.get_by_channel_id(channel_id)

        if automation is None:
            automation = ChannelAutomation(
                channel_id=channel_id,
                automation_status=AutomationStatus.STOPPED,
            )
            automation = await self._automation_repo.create(automation)
        else:
            automation = await self._automation_repo.update(
                automation, automation_status=AutomationStatus.STOPPED
            )

        await self._channel_repo.update(channel, is_archived=True)
        logger.info("Channel automation deleted (archived).", channel_id=str(channel_id))
        return self._to_response(automation)

    async def reset_channel(self, channel_id: UUID) -> dict:
        """Hard reset: deletes ALL generated content for this channel —
        PipelineRuns, Scripts, Videos, Uploads — AND deletes every
        published video from YouTube itself. Irreversible.

        Unlike delete()/archive above (which deliberately preserves
        history), this is the "wipe everything and start over" action.
        The Channel row and its Topics are left alone — this clears
        generated output, not your topic ideas or channel config.

        Automation is force-stopped first so the scheduler can't create
        a new PipelineRun while this is deleting rows out from under it.
        """
        from sqlalchemy import select, delete as sql_delete
        from app.database.models.script import Script
        from app.database.models.video import Video
        from app.database.models.upload import Upload
        from app.database.models.pipeline_run import PipelineRun
        from app.database.models.storyboard import Storyboard
        from app.database.models.quality_report import QualityReport
        from app.database.models.thumbnail import Thumbnail
        from app.database.models.voice import Voice
        from app.database.models.analytics import Analytics
        from app.integrations.youtube.auth import YouTubeAuthManager
        from app.integrations.youtube.client import YouTubeApiClient
        from app.integrations.youtube.exceptions import YouTubeVideoNotFoundError

        channel = await self._channel_repo.get_by_id_or_raise(channel_id)
        automation = await self._automation_repo.get_by_channel_id(channel_id)

        # Force-stop first so the scheduler doesn't race with the deletes below.
        if automation is not None:
            await self._automation_repo.update(
                automation, automation_status=AutomationStatus.STOPPED
            )
            await self._session.commit()

        script_ids = (
            (
                await self._session.execute(
                    select(Script.id).where(Script.channel_id == channel_id)
                )
            )
            .scalars()
            .all()
        )

        video_ids: list = []
        if script_ids:
            video_ids = (
                (
                    await self._session.execute(
                        select(Video.id).where(Video.script_id.in_(script_ids))
                    )
                )
                .scalars()
                .all()
            )

        upload_rows: list = []
        if video_ids:
            upload_rows = (
                (
                    await self._session.execute(
                        select(Upload).where(Upload.video_id.in_(video_ids))
                    )
                )
                .scalars()
                .all()
            )

        # Delete from YouTube FIRST, best-effort per video, and COMMIT
        # immediately after — a video actually deleted from YouTube is
        # irreversible, so it must never be left dependent on a later
        # local DB step succeeding. If the local cleanup below fails for
        # any reason, already-deleted videos stay correctly reflected as
        # gone rather than the dashboard silently pretending otherwise.
        youtube_deleted = 0
        youtube_failed: list[str] = []
        uploads_with_youtube_id = [u for u in upload_rows if u.youtube_video_id]

        if uploads_with_youtube_id:
            auth = YouTubeAuthManager(
                client_id=settings.youtube_client_id,
                client_secret=settings.youtube_client_secret,
                refresh_token=settings.youtube_refresh_token,
            )
            client = YouTubeApiClient(auth)
            try:
                for upload in uploads_with_youtube_id:
                    try:
                        await client.delete_video(upload.youtube_video_id)
                        youtube_deleted += 1
                    except YouTubeVideoNotFoundError:
                        # Already gone from YouTube (e.g. a previous
                        # partial reset attempt) — that's the desired
                        # end state, count it as done, not a failure.
                        youtube_deleted += 1
                    except Exception as exc:
                        youtube_failed.append(f"{upload.youtube_video_id}: {exc}")
            finally:
                await client.close()
                await auth.close()

        # Local cleanup — FK-safe order. Every table that references
        # scripts.id or uploads.id must be cleared before its parent:
        #   PipelineRun (channel_id)
        #   Analytics (upload_id)          -> before Upload
        #   Upload (video_id)              -> before Video
        #   Storyboard/QualityReport/Thumbnail/Voice (script_id) -> before Script
        #   Video (script_id)              -> before Script
        #   Script
        await self._session.execute(
            sql_delete(PipelineRun).where(PipelineRun.channel_id == channel_id)
        )

        upload_ids = [u.id for u in upload_rows]
        if upload_ids:
            await self._session.execute(
                sql_delete(Analytics).where(Analytics.upload_id.in_(upload_ids))
            )
        if video_ids:
            await self._session.execute(
                sql_delete(Upload).where(Upload.video_id.in_(video_ids))
            )
        if script_ids:
            await self._session.execute(
                sql_delete(Storyboard).where(Storyboard.script_id.in_(script_ids))
            )
            await self._session.execute(
                sql_delete(QualityReport).where(QualityReport.script_id.in_(script_ids))
            )
            await self._session.execute(
                sql_delete(Thumbnail).where(Thumbnail.script_id.in_(script_ids))
            )
            await self._session.execute(
                sql_delete(Voice).where(Voice.script_id.in_(script_ids))
            )
        if video_ids:
            await self._session.execute(
                sql_delete(Video).where(Video.id.in_(video_ids))
            )
        if script_ids:
            await self._session.execute(
                sql_delete(Script).where(Script.id.in_(script_ids))
            )

        # Reset automation counters back to a fresh, never-started state.
        if automation is not None:
            automation = await self._automation_repo.update(
                automation,
                cumulative_active_days=0,
                last_run_date=None,
                last_long_pipeline_date=None,
                started_at=None,
                paused_at=None,
            )

        await self._session.flush()

        logger.warning(
            "Channel RESET: all generated content deleted, YouTube videos removed.",
            channel_id=str(channel_id),
            scripts_deleted=len(script_ids),
            videos_deleted=len(video_ids),
            uploads_deleted=len(upload_rows),
            youtube_deleted=youtube_deleted,
            youtube_failed=len(youtube_failed),
        )

        return {
            "channel_name": channel.name,
            "scripts_deleted": len(script_ids),
            "videos_deleted": len(video_ids),
            "uploads_deleted": len(upload_rows),
            "youtube_deleted": youtube_deleted,
            "youtube_failed": youtube_failed,
        }

    async def get(self, channel_id: UUID) -> ChannelAutomationResponse:
        automation = await self._get_or_raise(channel_id)
        return self._to_response(automation)

    async def _get_or_raise(self, channel_id: UUID) -> ChannelAutomation:
        channel = await self._channel_repo.get_by_id(channel_id)
        if channel is None:
            raise NotFoundError("Channel", channel_id)
        automation = await self._automation_repo.get_by_channel_id(channel_id)
        if automation is None:
            raise NotFoundError("ChannelAutomation", channel_id)
        return automation

    @staticmethod
    def _to_response(automation: ChannelAutomation) -> ChannelAutomationResponse:
        phase = (
            "shorts_only"
            if automation.cumulative_active_days <= settings.automation_shorts_only_days
            else "shorts_and_long"
        )
        next_long: date | None = None
        if automation.automation_status == AutomationStatus.RUNNING:
            if automation.last_long_pipeline_date is not None:
                next_long = date.fromordinal(
                    automation.last_long_pipeline_date.toordinal()
                    + automation.long_video_interval_days
                )
        return ChannelAutomationResponse(
            id=automation.id,
            channel_id=automation.channel_id,
            automation_status=automation.automation_status,
            started_at=automation.started_at,
            paused_at=automation.paused_at,
            cumulative_active_days=automation.cumulative_active_days,
            last_run_date=automation.last_run_date,
            last_long_pipeline_date=automation.last_long_pipeline_date,
            long_video_interval_days=automation.long_video_interval_days,
            phase=phase,
            next_expected_long_video_date=next_long,
            created_at=automation.created_at,
            updated_at=automation.updated_at,
        )