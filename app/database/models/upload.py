import uuid
import enum
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean, Integer
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database.connection import Base


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"
    SCHEDULED = "scheduled"


class PublishStatus(str, enum.Enum):
    """Editorial / workflow state — separate from the technical UploadStatus.

    Lifecycle:
        DRAFT     → created, awaiting quality approval
        APPROVED  → passed quality gate; pipeline sets scheduled_at
        SCHEDULED → scheduled_at is set; Scheduler will trigger the upload
        REJECTED  → terminal; will not be uploaded

    The Scheduler queries for SCHEDULED rows where scheduled_at <= now()
    and then delegates to UploadAgentService.run_upload_for_video().
    UploadStatus tracks the technical YouTube upload progress independently.
    """
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    REJECTED = "rejected"


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False, unique=True
    )
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    privacy_status: Mapped[str] = mapped_column(String(20), default="public")
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        SqlEnum(UploadStatus), default=UploadStatus.PENDING
    )
    # Editorial workflow state — managed by the pipeline and publishing endpoints.
    publish_status: Mapped[PublishStatus] = mapped_column(
        SqlEnum(PublishStatus), default=PublishStatus.DRAFT
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    # ------------------------------------------------------------------
    # Retry state — scoped strictly per-row.  Every new record starts at
    # retry_count=0 regardless of history for the same video.
    # ------------------------------------------------------------------
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ── Instagram cross-post tracking ──────────────────────────────────────
    instagram_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    instagram_posted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    instagram_posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    instagram_media_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Retry cap — incremented on each failed/no-media_id attempt; when it
    # reaches INSTAGRAM_MAX_RETRIES (3) the row is marked permanently failed
    # and excluded from future scheduler ticks to prevent infinite loops.
    instagram_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    instagram_failed_permanently: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # ───────────────────────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    video: Mapped["Video"] = relationship("Video", back_populates="upload")
    analytics: Mapped[list["Analytics"]] = relationship(
        "Analytics", back_populates="upload"
    )

    def __repr__(self) -> str:
        return (
            f"<Upload(id={self.id}, youtube_id={self.youtube_video_id}, "
            f"status={self.status}, publish_status={self.publish_status}, "
            f"retry={self.retry_count}/{self.max_retries})>"
        )