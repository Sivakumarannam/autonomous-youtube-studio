from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    upload_id: UUID
    snapshot_date: datetime
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_minutes: float
    average_view_duration: float
    average_view_percentage: float
    ctr: float
    impressions: int
    subscribers_gained: int
    subscribers_lost: int
    revenue: float
    created_at: datetime


class AnalyticsFetchResponse(BaseModel):
    success: bool = True
    message: str
    analytics: AnalyticsResponse


class AnalyticsListResponse(BaseModel):
    total: int
    items: list[AnalyticsResponse]