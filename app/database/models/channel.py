import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database.connection import Base


class ContentType(str, enum.Enum):
    SHORTS = "shorts"
    LONG = "long"
    BOTH = "both"


class AspectRatio(str, enum.Enum):
    SHORTS = "9:16"
    LONG = "16:9"


class ChannelStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    INACTIVE = "inactive"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    niche: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    content_type: Mapped[ContentType] = mapped_column(
        SqlEnum(ContentType),
        default=ContentType.BOTH,
    )
    aspect_ratio: Mapped[AspectRatio] = mapped_column(
        SqlEnum(AspectRatio),
        default=AspectRatio.LONG,
    )
    target_duration: Mapped[int] = mapped_column(default=600)  # seconds
    upload_schedule: Mapped[str] = mapped_column(String(100), default="daily")
    youtube_channel_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(
        SqlEnum(ChannelStatus),
        default=ChannelStatus.ACTIVE,
    )
    config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON config
    # IANA timezone name (e.g. "Asia/Kolkata"). All "what day is it for this
    # channel" logic in the Daily Automation Scheduler uses this, not server
    # time, so a channel's daily cadence is anchored to its own local day.
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    # Soft-delete/archive flag for the Channel Automation "Delete" action.
    # Archived channels are hidden from normal dashboard listing and are
    # never picked up by the Daily Automation Scheduler, but no related
    # rows (Topics/Scripts/Videos/Uploads/PipelineRuns/Analytics) are
    # touched — all historical data is preserved.
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    topics: Mapped[list["Topic"]] = relationship("Topic", back_populates="channel")
    scripts: Mapped[list["Script"]] = relationship("Script", back_populates="channel")

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, name={self.name})>"