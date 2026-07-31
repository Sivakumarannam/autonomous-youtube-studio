"""Video Publish Scheduler (Stage 3).

Uses APScheduler's AsyncIOScheduler to run a periodic tick that finds
uploads whose publish_status=SCHEDULED and scheduled_at <= now(), then
delegates the actual YouTube upload to UploadAgentService.run_upload_for_video().

Design rules:
  - One failure per video must NOT crash the loop or block other videos.
  - Scheduler starts/stops with the FastAPI lifespan.
  - Every tick is logged: due count, succeeded, failed.
  - APScheduler's clock is injectable for tests (via the trigger's `timezone`
    and by replacing the scheduler instance in tests).

Retry Manager — Surface B
─────────────────────────
Transient upload errors (httpx timeouts, network failures, YouTube 429/5xx)
are retried with exponential backoff up to upload.max_retries attempts.

Backoff sequence: scheduler_base_backoff_seconds × 1, × 2, × 4 …
Default base: 60 s (vs. pipeline's 30 s — rationale: the scheduler runs
unattended and large-file YouTube uploads benefit from a longer initial
cooldown before hammering a rate-limited or overloaded API endpoint.
The pipeline is user-initiated and its stage failures are typically faster,
so 30 s is appropriate there.)

Idempotency: at the start of every retry attempt the Upload row is re-fetched
from DB.  If youtube_video_id is set OR status is PUBLISHED (YouTube accepted
the upload but the response was lost before we could mark it), the upload is
marked PUBLISHED immediately without a new upload attempt.

Brand-new session per attempt: each retry opens a fresh AsyncSession so
there is no stale ORM state between attempts.

Brand-new upload session per call: run_upload_for_video() with raise_on_error=True
creates fresh YouTubeAuthManager / YouTubeApiClient / YouTubeUploader instances
on every invocation — a stale or expired resumable-upload session from a
previous failed attempt is never reused.

Retry state is scoped strictly to the Upload row — every new Upload record
starts at retry_count=0 regardless of history for the same video.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository
from app.database.repositories.video_repository import VideoRepository
from app.agents.upload_agent.service import UploadAgentService
from app.database.models.upload import UploadStatus, PublishStatus
from app.monitoring.metrics import (
    SCHEDULER_TICKS_TOTAL,
    SCHEDULER_UPLOAD_RESULTS_TOTAL,
    UPLOAD_RETRIES_TOTAL,
)
from app.utils.retry import is_retryable_error
from app.websocket.manager import broadcast_safe

logger = get_logger(__name__)

# Last-tick snapshot for the dashboard's Scheduler Status card. In-process
# only (no persistence needed — this is transient monitoring state, not a
# durable business record, so it does not warrant a DB migration).
_last_tick_info: dict | None = None


def get_last_tick_info() -> dict | None:
    """Return the most recent scheduler tick's stats, or None if it hasn't run yet."""
    return _last_tick_info


class VideoPublishScheduler:
    """Wraps AsyncIOScheduler with domain-specific publish logic."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._publish_due_videos,
            trigger=IntervalTrigger(minutes=settings.scheduler_interval_minutes),
            id="publish_due_videos",
            replace_existing=True,
            max_instances=1,  # prevent overlapping ticks
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info(
                "Publish scheduler started.",
                interval_minutes=settings.scheduler_interval_minutes,
            )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Publish scheduler stopped.")

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    async def _publish_due_videos(self) -> None:
        """Find and publish all uploads whose scheduled_at has passed."""
        global _last_tick_info
        session_factory = _get_session_factory()

        # Fetch the list of due uploads in a short-lived read session.
        async with session_factory() as session:
            upload_repo = UploadRepository(session)
            due = await upload_repo.get_due_for_publish()

        total = len(due)
        logger.info("Scheduler tick: due uploads found.", due_count=total)

        if total == 0:
            SCHEDULER_TICKS_TOTAL.inc()
            _last_tick_info = {
                "ran_at": datetime.now(timezone.utc),
                "due_count": 0,
                "succeeded": 0,
                "failed": 0,
            }
            await broadcast_safe(
                {"type": "scheduler_tick", "due_count": 0, "succeeded": 0, "failed": 0}
            )
            return

        succeeded = 0
        failed = 0

        for upload in due:
            upload_id = upload.id  # capture before sessions change

            # Inner retry loop: each iteration opens a fresh session so there is
            # no stale ORM state between attempts.
            while True:
                async with session_factory() as session:
                    try:
                        upload_repo = UploadRepository(session)
                        video_repo = VideoRepository(session)

                        # Re-fetch for a session-bound, up-to-date instance.
                        upload = await upload_repo.get_or_raise(upload_id)

                        # ── Idempotency guard ──────────────────────────────
                        # YouTube may have accepted the video but the response
                        # was lost before we could mark it PUBLISHED.  Detect
                        # this and promote the status without a duplicate upload.
                        if (
                            upload.youtube_video_id
                            or upload.status == UploadStatus.PUBLISHED
                        ):
                            logger.info(
                                "Scheduler: upload already published "
                                "(idempotency guard), marking PUBLISHED.",
                                upload_id=str(upload_id),
                                youtube_video_id=upload.youtube_video_id,
                            )
                            upload = await upload_repo.update(
                                upload, status=UploadStatus.PUBLISHED
                            )
                            await session.commit()
                            succeeded += 1
                            break  # exit retry loop → next upload

                        # ── Race-condition guard ───────────────────────────
                        # A concurrent /reject call could have flipped status.
                        if upload.publish_status != PublishStatus.SCHEDULED:
                            logger.info(
                                "Scheduler: skipping upload — publish_status "
                                "changed since list-fetch (likely rejected).",
                                upload_id=str(upload_id),
                                current_publish_status=upload.publish_status.value,
                            )
                            await session.commit()
                            break  # not a retry scenario; skip this upload

                        if upload.status in (
                            UploadStatus.PUBLISHED, UploadStatus.UPLOADING
                        ):
                            logger.info(
                                "Scheduler: skipping upload — already in "
                                "progress or done.",
                                upload_id=str(upload_id),
                                current_status=upload.status.value,
                            )
                            await session.commit()
                            break

                        video = await video_repo.get_by_id(upload.video_id)

                        if video is None:
                            logger.error(
                                "Scheduler: video not found for upload.",
                                upload_id=str(upload_id),
                                video_id=str(upload.video_id),
                            )
                            await upload_repo.mark_failed(
                                upload,
                                "Video record not found during scheduled publish.",
                            )
                            await session.commit()
                            failed += 1
                            break

                        # raise_on_error=True: retryable exceptions propagate so
                        # the retry loop below can handle backoff.  Non-retryable
                        # failures (missing creds, missing file, YouTube auth 4xx)
                        # are caught inside the service and returned as FAILED.
                        upload_agent = UploadAgentService(session)
                        result = await upload_agent.run_upload_for_video(
                            video=video, upload=upload, raise_on_error=True
                        )

                        if result.status == UploadStatus.PUBLISHED:
                            logger.info(
                                "Scheduler: upload published.",
                                upload_id=str(upload_id),
                                youtube_id=result.youtube_video_id,
                            )
                            succeeded += 1
                            # ── Notification ────────────────────────────
                            yt_url = f"https://youtu.be/{result.youtube_video_id}" if result.youtube_video_id else "N/A"
                            try:
                                from app.notifications import notify
                                import datetime as _dt
                                _ig_schedule = (_dt.datetime.utcnow() + _dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M UTC")
                                # `result` here is the Upload ORM object returned by
                                # run_upload_for_video(), which has a `title` field —
                                # not `video_title` (that attribute only lives on
                                # UploadAgentOutput, a different object). Using the
                                # wrong attribute raised AttributeError every time,
                                # which this try/except silently swallowed — the
                                # upload succeeded, but the notification never went
                                # out, and the logs filled with "Upload notification
                                # failed" warnings.
                                _vid_title = result.title or upload.title or "Untitled"
                                await notify(
                                    title="✅ YouTube Upload Successful",
                                    body=f'"{_vid_title}" is now live on YouTube!',
                                    level="success",
                                    extra={
                                        "🔗 YouTube URL": yt_url,
                                        "📹 Title": _vid_title,
                                        "📸 Instagram scheduled": _ig_schedule,
                                        "📌 Manual actions": "Pin the auto-posted comment & add end screen in YouTube Studio",
                                    },
                                )
                            except Exception as _ne:
                                logger.warning("Upload notification failed", error=str(_ne))
                            # ── Schedule Instagram cross-post for 24 h later ──
                            if result.youtube_video_id and settings.instagram_enabled:
                                try:
                                    _ig_time = datetime.now(timezone.utc) + timedelta(hours=24)
                                    await UploadRepository(session).update(
                                        upload,
                                        instagram_scheduled_at=_ig_time,
                                        instagram_posted=False,
                                    )
                                    logger.info(
                                        "Instagram cross-post scheduled",
                                        youtube_id=result.youtube_video_id,
                                        scheduled_at=_ig_time.isoformat(),
                                    )
                                except Exception as _ig_exc:
                                    logger.warning("Instagram schedule failed (non-fatal)", error=str(_ig_exc))
                        else:
                            # Non-retryable failure handled internally by the
                            # service (e.g., missing credentials, file not found).
                            logger.warning(
                                "Scheduler: upload did not reach PUBLISHED status.",
                                upload_id=str(upload_id),
                                status=str(result.status),
                                error=result.error_message,
                            )
                            # ── Notification ────────────────────────────
                            try:
                                from app.notifications import notify
                                _vid_title = upload.title or "Untitled"
                                await notify(
                                    title="❌ YouTube Upload Failed",
                                    body=f'"{_vid_title}" could not be uploaded.',
                                    level="error",
                                    extra={
                                        "💥 Error": result.error_message or "unknown error",
                                        "📹 Title": _vid_title,
                                        "🔁 Status": str(result.status),
                                    },
                                )
                            except Exception:
                                pass
                            failed += 1

                        await session.commit()
                        break  # done with this upload

                    except Exception as exc:
                        await session.rollback()
                        # upload was re-fetched at the top of this iteration;
                        # its retry_count reflects the DB state at that point.
                        retry_count_now = upload.retry_count
                        max_retries_now = upload.max_retries

                        if (
                            is_retryable_error(exc)
                            and retry_count_now < max_retries_now
                        ):
                            # ── Schedule a retry ──────────────────────────
                            new_count = retry_count_now + 1
                            delay = (
                                settings.scheduler_base_backoff_seconds
                                * (2 ** retry_count_now)
                            )
                            next_retry_at = datetime.now(timezone.utc) + timedelta(
                                seconds=delay
                            )

                            logger.warning(
                                "Scheduler: retryable error, backing off.",
                                upload_id=str(upload_id),
                                retry_count=new_count,
                                max_retries=max_retries_now,
                                delay_seconds=delay,
                                error_type=type(exc).__name__,
                            )
                            UPLOAD_RETRIES_TOTAL.inc()

                            # Persist retry metadata in a separate mini-session
                            # so it survives the rollback above.
                            async with session_factory() as retry_session:
                                try:
                                    repo = UploadRepository(retry_session)
                                    u = await repo.get_or_raise(upload_id)
                                    await repo.update(
                                        u,
                                        retry_count=new_count,
                                        next_retry_at=next_retry_at,
                                    )
                                    await retry_session.commit()
                                except Exception as meta_exc:
                                    await retry_session.rollback()
                                    logger.error(
                                        "Scheduler: failed to persist retry metadata.",
                                        upload_id=str(upload_id),
                                        error=str(meta_exc),
                                    )

                            await asyncio.sleep(delay)
                            # Loop continues → next attempt with fresh session.

                        else:
                            # ── Permanent failure ─────────────────────────
                            if is_retryable_error(exc):
                                err_msg = (
                                    f"Max retries ({max_retries_now}) exhausted. "
                                    f"Last: {type(exc).__name__}: {str(exc)[:400]}"
                                )
                            else:
                                err_msg = (
                                    f"{type(exc).__name__}: {str(exc)[:500]}"
                                )

                            logger.error(
                                "Scheduler: upload failed permanently.",
                                upload_id=str(upload_id),
                                retry_count=retry_count_now,
                                error=str(exc),
                            )

                            async with session_factory() as fail_session:
                                try:
                                    repo = UploadRepository(fail_session)
                                    u = await repo.get_or_raise(upload_id)
                                    await repo.mark_failed(u, err_msg)
                                    await fail_session.commit()
                                except Exception as fail_exc:
                                    await fail_session.rollback()
                                    logger.error(
                                        "Scheduler: failed to mark upload as FAILED.",
                                        upload_id=str(upload_id),
                                        error=str(fail_exc),
                                    )

                            failed += 1
                            break

        logger.info(
            "Scheduler tick complete.",
            total=total,
            succeeded=succeeded,
            failed=failed,
        )

        SCHEDULER_TICKS_TOTAL.inc()
        if succeeded:
            SCHEDULER_UPLOAD_RESULTS_TOTAL.labels(result="succeeded").inc(succeeded)
        if failed:
            SCHEDULER_UPLOAD_RESULTS_TOTAL.labels(result="failed").inc(failed)

        _last_tick_info = {
            "ran_at": datetime.now(timezone.utc),
            "due_count": total,
            "succeeded": succeeded,
            "failed": failed,
        }
        await broadcast_safe(
            {
                "type": "scheduler_tick",
                "due_count": total,
                "succeeded": succeeded,
                "failed": failed,
            }
        )


# Module-level singleton used by the FastAPI lifespan.
_scheduler: VideoPublishScheduler | None = None


def get_scheduler() -> VideoPublishScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = VideoPublishScheduler()
    return _scheduler