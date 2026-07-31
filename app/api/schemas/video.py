from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.database.models.video import VideoStatus


class VideoGenerateRequest(BaseModel):
    script_id: UUID


class VideoUpdateRequest(BaseModel):
    video_path: Optional[str] = None
    resolution: Optional[str] = None
    status: Optional[VideoStatus] = None


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    script_id: UUID

    audio_path: Optional[str]
    video_path: Optional[str]
    resolution: str

    duration: float
    file_size: int

    status: VideoStatus
    error_message: Optional[str]

    created_at: datetime
    updated_at: datetime


class VideoListResponse(BaseModel):
    total: int
    items: list[VideoResponse]


class VideoGenerationResponse(BaseModel):
    success: bool = True
    message: str
    video: VideoResponse


class VideoBatchGenerationResponse(BaseModel):
    success: bool = True
    message: str
    generated_count: int


class VideoDeleteResponse(BaseModel):
    success: bool = True
    message: str