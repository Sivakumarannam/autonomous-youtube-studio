"""ChannelAutomation model (Phase 6).

One row per channel, tracking the state of fully autonomous, indefinite
channel-level automation. The user clicks Start ONCE; from then on the
Daily Automation Scheduler (app/scheduler/automation_scheduler.py) generates,
scores, renders, schedules, and publishes content daily until the user
explicitly Pauses or Deletes (archives) the channel.
"""
import enum
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SqlEnum
from app.database.connection import Base


class AutomationStatus(str, enum.Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class ChannelAutomation(Base):
    __tablename__ = "channel_automations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    automation_status: Mapped[AutomationStatus] = mapped_column(
        SqlEnum(AutomationStatus),
        default=AutomationStatus.STOPPED,
        nullable=False,
    )
    # When Start was first ever clicked for this channel. Not reset by
    # subsequent Pause -> Start cycles.
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Count of calendar days the automation was actually RUNNING (not
    # paused) — NOT wall-clock days since started_at. Incremented once per
    # day the scheduler processes this channel while RUNNING. Drives the
    # day-16 Shorts -> Shorts+Long transition. Pausing FREEZES this count;
    # it is never reset by Pause, and paused time never counts toward it.
    cumulative_active_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    # Last date (in the channel's timezone) a PipelineRun was created for
    # this channel. Used for the "already ran today" skip and the
    # never-backfill missed-day policy.
    last_run_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_long_pipeline_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    long_video_interval_days: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    channel: Mapped["Channel"] = relationship("Channel")

    def __repr__(self) -> str:
        return (
            f"<ChannelAutomation(channel_id={self.channel_id}, "
            f"status={self.automation_status}, "
            f"cumulative_active_days={self.cumulative_active_days})>"
        )