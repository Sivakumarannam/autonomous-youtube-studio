from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.analytics import (
    AnalyticsFetchResponse,
    AnalyticsListResponse,
    AnalyticsResponse,
)
from app.api.services.analytics_service import AnalyticsService
from app.core.exceptions import NotFoundError
from app.database.connection import get_db

router = APIRouter()


@router.post(
    "/{video_id}",
    response_model=AnalyticsFetchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Fetch analytics from YouTube and save a snapshot",
)
async def fetch_analytics(
    video_id: UUID,
    start_date: Optional[date] = Query(default=None, description="Inclusive start date (YYYY-MM-DD). Defaults to 28 days before end_date."),
    end_date: Optional[date] = Query(default=None, description="Inclusive end date (YYYY-MM-DD). Defaults to today."),
    session: AsyncSession = Depends(get_db),
):
    """
    Call the YouTube Analytics API for the given internal video and persist
    the result as a new snapshot.  Date range defaults to the last 28 days.
    """
    svc = AnalyticsService(session)
    try:
        snapshot = await svc.fetch_for_video(
            video_id=video_id,
            start_date=start_date,
            end_date=end_date,
        )
        return AnalyticsFetchResponse(
            success=True,
            message="Analytics snapshot fetched and saved.",
            analytics=AnalyticsResponse.model_validate(snapshot),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch analytics from YouTube. Check server logs.",
        )


@router.get(
    "/{video_id}/latest",
    response_model=AnalyticsResponse,
    summary="Return the most recent analytics snapshot for a video",
)
async def get_latest_analytics(
    video_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return the most recently stored Analytics snapshot for this video."""
    svc = AnalyticsService(session)
    try:
        snapshot = await svc.get_latest(video_id)
        return AnalyticsResponse.model_validate(snapshot)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{video_id}",
    response_model=AnalyticsListResponse,
    summary="List all analytics snapshots for a video",
)
async def list_analytics(
    video_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return all Analytics snapshots for this video, newest first."""
    svc = AnalyticsService(session)
    try:
        snapshots = await svc.list_for_video(video_id)
        return AnalyticsListResponse(
            total=len(snapshots),
            items=[AnalyticsResponse.model_validate(s) for s in snapshots],
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
