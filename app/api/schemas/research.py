from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.database.models.research import ResearchStatus


class ResearchRequest(BaseModel):
    topic_id: UUID


class ResearchResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    topic_id: UUID
    summary: Optional[str]
    key_facts: Optional[str]
    references: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class ResearchDetail(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    topic_id: UUID
    summary: Optional[str]
    key_facts: Optional[str]
    references: Optional[str]
    raw_data: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime