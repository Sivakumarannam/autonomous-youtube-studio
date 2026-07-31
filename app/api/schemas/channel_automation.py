from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.database.models.channel_automation import AutomationStatus


class ChannelAutomationResponse(BaseModel):
    id: UUID
    channel_id: UUID
    automation_status: AutomationStatus
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    cumulative_active_days: int
    last_run_date: Optional[date] = None
    last_long_pipeline_date: Optional[date] = None
    long_video_interval_days: int
    # Derived, dashboard-friendly fields — not stored columns.
    phase: str  # "shorts_only" | "shorts_and_long"
    next_expected_long_video_date: Optional[date] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}