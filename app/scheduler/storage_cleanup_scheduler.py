"""Storage Cleanup Scheduler.

Runs once daily via APScheduler and removes old generated files from
storage/videos, storage/audio, and storage/cache once they're past the
configured retention window (settings.storage_retention_days, default 14).

Wires up the existing-but-previously-unused app/storage/cleanup.py
functions (cleanup_old_files, cleanup_empty_directories) — nothing in
those functions changed except cleanup_old_files gaining an optional
`exclude` set, which this scheduler uses for the DB-awareness below.

DB-awareness / safety guard
────────────────────────────
cleanup_old_files() only knows about file mtimes — it has no idea whether
a file is still needed. Before sweeping storage/videos and storage/audio,
this scheduler builds a set of "protected" file paths from the DB: any
Video that isn't yet status=COMPLETE, and any Video whose Upload isn't yet
status=PUBLISHED. Those paths are excluded from deletion regardless of
age, so a file belonging to an in-progress or scheduled-but-unpublished
pipeline run is never removed out from under it.

storage/cache is not tied to a specific Video/Upload record (it holds
provider-level caches — music, stock photos), so it is swept purely by
age, same as before this file existed (i.e. never — it just grew forever).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.database.connection import _get_session_factory
from app.database.models.upload import Upload, UploadStatus
from app.database.models.video import Video, VideoStatus
from app.storage.cleanup import cleanup_empty_directories, cleanup_old_files

logger = get_logger(__name__)


def _dir_size(directory: Path) -> int:
    """Best-effort total size in bytes of all files under directory."""
    total = 0
    for item in directory.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                # File could vanish mid-scan (e.g. deleted concurrently) —
                # not worth failing the whole sweep over.
                pass
    return total


class StorageCleanupScheduler:
    """Wraps AsyncIOScheduler with a once-daily storage retention sweep."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_cleanup,
            trigger=IntervalTrigger(hours=24),
            id="storage_cleanup",
            replace_existing=True,
            max_instances=1,  # prevent overlapping sweeps
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info(
                "Storage cleanup scheduler started.",
                retention_days=settings.storage_retention_days,
            )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Storage cleanup scheduler stopped.")

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    async def _protected_paths(self, session) -> set[str]:
        """Absolute file paths that must never be deleted regardless of
        age: video/audio files belonging to a Video that isn't COMPLETE
        yet, or whose Upload hasn't reached PUBLISHED yet."""
        protected: set[str] = set()

        in_progress_videos = await session.execute(
            select(Video).where(Video.status != VideoStatus.COMPLETE)
        )
        for video in in_progress_videos.scalars().all():
            for raw_path in (video.video_path, video.audio_path):
                if raw_path:
                    protected.add(str(Path(raw_path).resolve()))

        unpublished = await session.execute(
            select(Video)
            .join(Upload, Upload.video_id == Video.id)
            .where(Upload.status != UploadStatus.PUBLISHED)
        )
        for video in unpublished.scalars().all():
            for raw_path in (video.video_path, video.audio_path):
                if raw_path:
                    protected.add(str(Path(raw_path).resolve()))

        return protected

    async def _run_cleanup(self) -> None:
        session_factory = _get_session_factory()
        retention_seconds = settings.storage_retention_days * 86400
        base = Path(settings.storage_local_path)

        try:
            async with session_factory() as session:
                protected = await self._protected_paths(session)
        except Exception as exc:
            logger.error(
                "Storage cleanup: failed to load protected paths from DB — "
                "skipping this sweep to avoid deleting anything unsafely.",
                error=str(exc),
            )
            return

        targets: dict[str, Optional[set[str]]] = {
            "videos": protected,
            "audio": protected,
            "cache": None,
        }

        total_files_removed = 0
        total_bytes_removed = 0

        for label, exclude in targets.items():
            directory = base / label
            if not directory.exists():
                continue

            before_bytes = _dir_size(directory)
            removed = await cleanup_old_files(
                directory, retention_seconds, exclude=exclude
            )
            after_bytes = _dir_size(directory)
            bytes_removed = max(0, before_bytes - after_bytes)

            total_files_removed += removed
            total_bytes_removed += bytes_removed

            logger.info(
                "Storage cleanup: directory swept.",
                directory=str(directory),
                files_removed=removed,
                bytes_removed=bytes_removed,
                retention_days=settings.storage_retention_days,
            )

        empty_dirs_removed = 0
        for label in targets:
            directory = base / label
            if directory.exists():
                empty_dirs_removed += await cleanup_empty_directories(directory)

        logger.info(
            "Storage cleanup: daily sweep complete.",
            total_files_removed=total_files_removed,
            total_bytes_removed=total_bytes_removed,
            empty_dirs_removed=empty_dirs_removed,
        )


# Module-level singleton used by the FastAPI lifespan.
_storage_cleanup_scheduler: StorageCleanupScheduler | None = None


def get_storage_cleanup_scheduler() -> StorageCleanupScheduler:
    global _storage_cleanup_scheduler
    if _storage_cleanup_scheduler is None:
        _storage_cleanup_scheduler = StorageCleanupScheduler()
    return _storage_cleanup_scheduler
