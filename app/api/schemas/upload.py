import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.database.models.upload import UploadStatus


class UploadRequest(BaseModel):
    video_id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = []
    privacy_status: str = "private"


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    youtube_video_id: Optional[str]
    youtube_url: Optional[str]
    title: Optional[str]
    description: Optional[str]
    tags: Optional[list[str]] = None
    privacy_status: str
    status: UploadStatus
    error_message: Optional[str]
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        return v


class UploadTriggerResponse(BaseModel):
    success: bool = True
    message: str
    upload: UploadResponse


class UploadListResponse(BaseModel):
    total: int
    items: list[UploadResponse]


class UploadDeleteResponse(BaseModel):
    success: bool = True
    message: str