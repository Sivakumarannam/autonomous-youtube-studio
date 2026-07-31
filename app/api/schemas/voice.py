from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.database.models.voice import VoiceProvider, VoiceStatus


class VoiceGenerateRequest(BaseModel):
    script_id: UUID
    provider: VoiceProvider = VoiceProvider.GTTS
    language: str = Field(default="en", min_length=2, max_length=20)
    speaker: Optional[str] = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class VoiceUpdateRequest(BaseModel):
    provider: Optional[VoiceProvider] = None
    language: Optional[str] = None
    speaker: Optional[str] = None
    status: Optional[VoiceStatus] = None


class VoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    script_id: UUID

    provider: VoiceProvider
    status: VoiceStatus

    language: str
    speaker: Optional[str]

    audio_path: Optional[str]

    duration: float
    word_count: int
    file_size: int

    sample_rate: int
    bitrate: str

    transcript: Optional[str]
    error_message: Optional[str]

    created_at: datetime
    updated_at: datetime


class VoiceListResponse(BaseModel):
    total: int
    items: list[VoiceResponse]


class VoiceGenerationResponse(BaseModel):
    success: bool = True
    message: str
    voice: VoiceResponse


class VoiceDeleteResponse(BaseModel):
    success: bool = True
    message: str