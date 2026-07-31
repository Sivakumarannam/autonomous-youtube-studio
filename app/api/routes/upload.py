from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.upload import (
    UploadDeleteResponse,
    UploadListResponse,
    UploadRequest,
    UploadResponse,
    UploadTriggerResponse,
)
from app.api.services.upload_service import UploadService
from app.core.exceptions import NotFoundError, UploadError
from app.database.connection import get_db
from app.database.models.upload import UploadStatus

router = APIRouter()


@router.post(
    "/",
    response_model=UploadTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_upload(
    request: UploadRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Trigger a YouTube upload for a completed video.

    Idempotent for PUBLISHED uploads (returns existing record).
    Returns 422 if the video is not yet complete or an upload is already running.
    """
    service = UploadService(session)
    try:
        upload = await service.trigger_upload(
            video_id=request.video_id,
            title=request.title,
            description=request.description,
            tags=request.tags,
            privacy_status=request.privacy_status,
        )
        return UploadTriggerResponse(
            success=True,
            message="Upload triggered successfully.",
            upload=UploadResponse.model_validate(upload),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except UploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )


@router.get(
    "/video/{video_id}",
    response_model=UploadResponse,
)
async def get_upload_by_video(
    video_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return the Upload record for a given video."""
    service = UploadService(session)
    try:
        upload = await service.get_by_video(video_id)
        return UploadResponse.model_validate(upload)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{upload_id}",
    response_model=UploadResponse,
)
async def get_upload(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Return an Upload record by its own ID."""
    service = UploadService(session)
    try:
        upload = await service.get_upload(upload_id)
        return UploadResponse.model_validate(upload)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/",
    response_model=UploadListResponse,
)
async def list_uploads(
    status_filter: Optional[UploadStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """List uploads, optionally filtered by status."""
    service = UploadService(session)
    uploads = await service.list_uploads(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return UploadListResponse(
        total=len(uploads),
        items=[UploadResponse.model_validate(u) for u in uploads],
    )


@router.delete(
    "/{upload_id}",
    response_model=UploadDeleteResponse,
)
async def delete_upload(
    upload_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    """Delete an Upload record."""
    service = UploadService(session)
    try:
        await service.delete_upload(upload_id)
        return UploadDeleteResponse(success=True, message="Upload deleted successfully.")
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))