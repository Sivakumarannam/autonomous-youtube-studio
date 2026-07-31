from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.database.models.channel import (
    AspectRatio,
    ChannelStatus,
    ContentType,
)


class ChannelBase(BaseModel):
    name: str
    niche: str
    language: str = "en"

    description: Optional[str] = None

    content_type: ContentType = ContentType.BOTH
    aspect_ratio: AspectRatio = AspectRatio.LONG

    target_duration: int = 600
    upload_schedule: str = "daily"

    # IANA timezone name (e.g. "Asia/Kolkata"). Drives peak-upload-window
    # scheduling. Was missing from this schema entirely, so it silently
    # defaulted to "UTC" with no way to change it via the API.
    timezone: str = "UTC"

    youtube_channel_id: Optional[str] = None


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    niche: Optional[str] = None
    language: Optional[str] = None

    description: Optional[str] = None

    content_type: Optional[ContentType] = None
    aspect_ratio: Optional[AspectRatio] = None

    target_duration: Optional[int] = None
    upload_schedule: Optional[str] = None

    timezone: Optional[str] = None

    youtube_channel_id: Optional[str] = None

    status: Optional[ChannelStatus] = None


class ChannelResponse(ChannelBase):
    id: UUID
    status: ChannelStatus

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }