from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.database.models.pipeline_run import PipelineStatus


class PipelineRunRequest(BaseModel):
    topic_id: UUID
    channel_id: UUID
    script_type: str = Field(default="long", pattern="^(short|long)$")

    @model_validator(mode="after")
    def _channel_matches_topic(self) -> "PipelineRunRequest":
        # channel_id / topic_id cross-validation happens in the service layer
        # where we have DB access.
        return self


class PipelineRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    topic_id: UUID
    channel_id: UUID
    script_type: str
    status: str
    current_stage: Optional[str]
    failed_stage: Optional[str]
    error_message: Optional[str]
    script_id: Optional[UUID]
    video_id: Optional[UUID]
    upload_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class PipelineRunListResponse(BaseModel):
    model_config = {"from_attributes": True}

    runs: list[PipelineRunResponse]
    total: int
