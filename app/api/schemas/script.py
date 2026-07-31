from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.database.models.script import ScriptType, ScriptStatus


class ScriptGenerateRequest(BaseModel):
    topic_id: UUID
    channel_id: UUID
    script_type: ScriptType = ScriptType.LONG


class ScriptResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    topic_id: UUID
    channel_id: UUID
    script_type: str
    content: str
    word_count: int
    estimated_duration: int
    hook: Optional[str]
    cta: Optional[str]
    seo_title: Optional[str]
    seo_description: Optional[str]
    seo_tags: Optional[str]
    hashtags: Optional[str]
    quality_score: float
    seo_gate_score: float
    file_path: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class ScriptUpdate(BaseModel):
    status: Optional[ScriptStatus] = None
    content: Optional[str] = None
    seo_title: Optional[str] = Field(None, max_length=500)
    seo_description: Optional[str] = None