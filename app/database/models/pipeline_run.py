import uuid
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.enums import SqlEnum
from app.database.connection import Base


class PipelineStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETE = "complete"


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False
    )
    # "short" | "long" — stored as plain string to avoid re-creating the
    # existing scripttype enum in a second table.
    script_type: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[PipelineStatus] = mapped_column(
        SqlEnum(PipelineStatus), default=PipelineStatus.PENDING
    )
    # Name of the stage currently executing, e.g. "script", "quality",
    # "video", "upload", "analytics". Null when not running.
    current_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Set when the pipeline halts with status=FAILED.
    failed_stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # IDs of artefacts created during the run (populated as stages complete).
    script_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id"), nullable=True
    )
    video_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id"), nullable=True
    )
    upload_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploads.id"), nullable=True
    )
    # ------------------------------------------------------------------
    # Retry state — scoped strictly per-row.  Every new record starts at
    # retry_count=0 regardless of history for the same topic/channel/video.
    # ------------------------------------------------------------------
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    topic: Mapped["Topic"] = relationship("Topic")
    channel: Mapped["Channel"] = relationship("Channel")
    # lazy="noload" — never lazy-loaded (async sessions don't support implicit
    # lazy loads). Use selectinload() in any query that needs score data.
    script: Mapped[Optional["Script"]] = relationship("Script", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<PipelineRun(id={self.id}, status={self.status}, "
            f"stage={self.current_stage}, retry={self.retry_count}/{self.max_retries})>"
        )