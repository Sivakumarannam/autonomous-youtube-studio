"""Instagram 24-hour cross-post scheduler.

Runs every 10 minutes. Picks up Upload rows where:
  - status = PUBLISHED
  - instagram_posted = False
  - instagram_scheduled_at <= now()

Then posts the Reel via the Meta Graph API and marks the row posted.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import _get_session_factory
from app.database.repositories.upload_repository import UploadRepository

logger = get_logger(__name__)


class InstagramCrossPostScheduler:
    """Periodic job that posts Reels when their 24-h window has elapsed."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._tick,
            trigger=IntervalTrigger(minutes=10),
            id="instagram_cross_post",
            replace_existing=True,
            max_instances=1,
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Instagram cross-post scheduler started.")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Instagram cross-post scheduler stopped.")

    async def _tick(self) -> None:
        if not settings.instagram_enabled:
            return

        session_factory = _get_session_factory()
        async with session_factory() as session:
            repo = UploadRepository(session)
            due = await repo.get_due_for_instagram()
            if not due:
                return

            logger.info("Instagram scheduler tick: due uploads.", count=len(due))

            for upload in due:
                await self._post_one(session, upload)

    async def _post_one(self, session, upload) -> None:
        from app.integrations.instagram import build_ig_caption, post_to_instagram
        from app.notifications.service import notify
        from app.database.models.video import Video
        from sqlalchemy import select

        yt_url = (
            f"https://youtu.be/{upload.youtube_video_id}"
            if upload.youtube_video_id
            else upload.youtube_url or ""
        )
        if not yt_url:
            logger.warning("Instagram skip — no YouTube URL", upload_id=str(upload.id))
            return

        caption = build_ig_caption(
            title=upload.title or "",
            description=upload.description or "",
            yt_url=yt_url,
        )

        # Instagram Graph API requires a *direct* publicly accessible MP4 URL —
        # YouTube watch URLs (youtu.be/…) are web pages, not raw video files, and
        # Meta's servers will reject them.  Serve the local MP4 via our /storage
        # static mount instead, using the Replit public dev domain.
        video_file_url: str = yt_url  # fallback if we can't build a direct link
        dev_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
        if dev_domain:
            result = await session.execute(
                select(Video).where(Video.id == upload.video_id)
            )
            video = result.scalar_one_or_none()
            if video and video.video_path:
                filename = os.path.basename(video.video_path)
                video_file_url = f"https://{dev_domain}/storage/videos/{filename}"
                logger.info(
                    "Instagram: using direct video URL",
                    url=video_file_url,
                    upload_id=str(upload.id),
                )

        try:
            media_id = await post_to_instagram(video_url=video_file_url, caption=caption)
            if media_id:
                repo = UploadRepository(session)
                await repo.mark_instagram_posted(upload, media_id)
                await session.commit()
                logger.info(
                    "Instagram Reel posted",
                    media_id=media_id,
                    youtube_id=upload.youtube_video_id,
                )
                try:
                    await notify(
                        title="📸 Instagram Reel Published",
                        body=f'"{upload.title or "Untitled"}" is now live on Instagram!',
                        level="success",
                        extra={
                            "🔗 YouTube URL": yt_url,
                            "📸 IG Media ID": media_id,
                        },
                    )
                except Exception:
                    pass
            else:
                logger.warning(
                    "Instagram post returned no media_id — will retry next tick.",
                    upload_id=str(upload.id),
                )
        except Exception as exc:
            logger.error(
                "Instagram post failed",
                upload_id=str(upload.id),
                error=str(exc),
            )
            try:
                await notify(
                    title="❌ Instagram Post Failed",
                    body=f'Could not post "{upload.title or "Untitled"}" to Instagram.',
                    level="error",
                    extra={"💥 Error": str(exc)},
                )
            except Exception:
                pass


# Module-level singleton
_ig_scheduler = InstagramCrossPostScheduler()


def get_instagram_scheduler() -> InstagramCrossPostScheduler:
    return _ig_scheduler
