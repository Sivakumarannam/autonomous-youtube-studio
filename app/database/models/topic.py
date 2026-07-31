import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database.connection import Base


class TopicStatus(str, enum.Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    PRODUCING = "producing"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class TopicSource(str, enum.Enum):
    GOOGLE_TRENDS = "google_trends"
    YOUTUBE_TRENDS = "youtube_trends"
    REDDIT = "reddit"
    NEWS = "news"
    MANUAL = "manual"
    FEEDBACK = "feedback"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[TopicSource] = mapped_column(
        SqlEnum(TopicSource),
        default=TopicSource.GOOGLE_TRENDS,
    )
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[TopicStatus] = mapped_column(
        SqlEnum(TopicStatus),
        default=TopicStatus.PENDING,
    )
    content_type: Mapped[str] = mapped_column(String(50), default="long")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="topics")
    research: Mapped[Optional["Research"]] = relationship(
        "Research", back_populates="topic", uselist=False
    )
    scripts: Mapped[list["Script"]] = relationship("Script", back_populates="topic")

    def __repr__(self) -> str:
        return f"<Topic(id={self.id}, title={self.title[:50]}, score={self.score})>"