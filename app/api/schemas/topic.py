from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.database.models.topic import TopicStatus, TopicSource


class TopicGenerateRequest(BaseModel):
    channel_id: UUID
    count: int = Field(default=5, ge=1, le=20)
    sources: list[TopicSource] = Field(
        default=[TopicSource.GOOGLE_TRENDS, TopicSource.YOUTUBE_TRENDS]
    )
    content_type: str = Field(default="long", pattern="^(short|long|both)$")


class TopicCreate(BaseModel):
    channel_id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    reason: Optional[str] = None
    source: TopicSource = TopicSource.MANUAL
    keywords: Optional[list[str]] = None
    content_type: str = Field(default="long", pattern="^(short|long|both)$")


class TopicUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    status: Optional[TopicStatus] = None
    content_type: Optional[str] = Field(None, pattern="^(short|long|both)$")


class TopicResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    channel_id: UUID
    title: str
    description: Optional[str]
    score: float
    reason: Optional[str]
    source: str
    keywords: Optional[str]
    status: str
    content_type: str
    created_at: datetime
    updated_at: datetime


class GeneratedTopic(BaseModel):
    topic: str
    score: float = Field(ge=0.0, le=100.0)
    reason: str
    keywords: list[str] = Field(default_factory=list)
    content_type: str = "long"


class TopicGenerateResponse(BaseModel):
    generated: int
    topics: list[TopicResponse]