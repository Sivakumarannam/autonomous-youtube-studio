import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey
from app.core.enums import SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database.connection import Base


class ResearchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class Research(Base):
    __tablename__ = "research"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id"), nullable=False, unique=True
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_facts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    references: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ResearchStatus] = mapped_column(
        SqlEnum(ResearchStatus),
        default=ResearchStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    topic: Mapped["Topic"] = relationship("Topic", back_populates="research")

    def __repr__(self) -> str:
        return f"<Research(id={self.id}, topic_id={self.topic_id})>"