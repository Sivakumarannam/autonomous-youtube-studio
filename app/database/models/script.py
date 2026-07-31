import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database.connection import Base


class ScriptType(str, enum.Enum):
    SHORT = "short"
    LONG = "long"


class ScriptStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PRODUCING = "producing"
    COMPLETE = "complete"


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=False
    )
    script_type: Mapped[ScriptType] = mapped_column(
        SqlEnum(ScriptType),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_duration: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    hook: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seo_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    seo_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seo_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    hashtags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    # Convenience mirror of Voice.voice_gender, kept in sync by
    # VoiceAgentService when the Voice record is created/updated. Nullable
    # because it isn't known until the voice stage runs — Voice.voice_gender
    # remains the authoritative source if this is ever out of sync.
    voice_gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    seo_gate_score: Mapped[float] = mapped_column(Float, default=0.0)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[ScriptStatus] = mapped_column(
        SqlEnum(ScriptStatus),
        default=ScriptStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    topic: Mapped["Topic"] = relationship("Topic", back_populates="scripts")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="scripts")
    video: Mapped[Optional["Video"]] = relationship(
        "Video", back_populates="script", uselist=False
    )
    thumbnail: Mapped[Optional["Thumbnail"]] = relationship(
        "Thumbnail",
        back_populates="script",
        uselist=False,
    )
    voice : Mapped[Optional["Voice"]] = relationship(
        "Voice",
        back_populates="script",
        uselist=False,
    )
    quality_reports: Mapped[list["QualityReport"]] = relationship(
        "QualityReport", back_populates="script"
    )

    def __repr__(self) -> str:
        return f"<Script(id={self.id}, type={self.script_type}, words={self.word_count})>"