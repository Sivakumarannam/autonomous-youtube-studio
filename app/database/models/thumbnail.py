import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database.connection import Base


class ThumbnailStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETE = "complete"
    FAILED = "failed"


class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id"),
        nullable=False,
        unique=True,
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    concept: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ThumbnailStatus] = mapped_column(
        SqlEnum(ThumbnailStatus),
        default=ThumbnailStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    script: Mapped["Script"] = relationship(
        "Script",
        back_populates="thumbnail",
    )

    def __repr__(self) -> str:
        return f"<Thumbnail(id={self.id}, status={self.status})>"