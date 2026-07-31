from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.database.models.upload import PublishStatus, UploadStatus


class UploadPublishResponse(BaseModel):
    """Upload record with both technical and editorial status fields."""
    model_config = {"from_attributes": True}

    id: UUID
    video_id: UUID
    title: Optional[str]
    description: Optional[str]
    tags: Optional[str]
    privacy_status: str
    status: str          # UploadStatus — technical YouTube upload progress
    publish_status: str  # PublishStatus — editorial workflow state
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    youtube_video_id: Optional[str]
    youtube_url: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class ScheduleRequest(BaseModel):
    """Body for the manual /schedule endpoint."""
    scheduled_at: datetime = Field(
        ...,
        description="UTC datetime at which the Scheduler should trigger the YouTube upload.",
    )


class RejectRequest(BaseModel):
    """Optional body for the /reject endpoint."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Human-readable reason for rejection (stored in error_message).",
    )
