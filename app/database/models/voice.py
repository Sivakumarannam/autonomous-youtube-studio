import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.enums import SqlEnum
from app.database.connection import Base


class VoiceStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


class VoiceProvider(str, enum.Enum):
    GTTS = "gtts"
    PYTTSX3 = "pyttsx3"
    KOKORO = "kokoro"
    MOCK = "mock"
    GOOGLE = "google"
    AZURE = "azure"
    ELEVENLABS = "elevenlabs"


class Voice(Base):
    __tablename__ = "voices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id"),
        nullable=False,
        unique=True,
    )

    provider: Mapped[str] = mapped_column(
        SqlEnum(VoiceProvider),
        default=VoiceProvider.GTTS,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        SqlEnum(VoiceStatus),
        default=VoiceStatus.PENDING,
        nullable=False,
    )

    language: Mapped[str] = mapped_column(
        String(20),
        default="en",
        nullable=False,
    )
    # Narrator gender actually used for this voice synthesis ("male" or
    # "female"). Set from VoiceSettings.gender at synthesis time — this is
    # the authoritative source for anything downstream that needs to know
    # which gender narrated the script (e.g. presenter/avatar selection).
    voice_gender: Mapped[str] = mapped_column(
        String(20),
        default="female",
        nullable=False,
    )

    speaker: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    audio_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    duration: Mapped[float] = mapped_column(
        Float,
        default=0.0,
    )

    word_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    file_size: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    sample_rate: Mapped[int] = mapped_column(
        Integer,
        default=24000,
    )

    bitrate: Mapped[str] = mapped_column(
        String(20),
        default="128k",
    )

    transcript: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    script: Mapped["Script"] = relationship(
        "Script",
        back_populates="voice",
    )

    def __repr__(self) -> str:
        return (
            f"<Voice("
            f"id={self.id}, "
            f"provider={self.provider}, "
            f"status={self.status}"
            f")>"
        )
