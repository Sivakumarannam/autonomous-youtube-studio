from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.video import (
    VideoBatchGenerationResponse,
    VideoDeleteResponse,
    VideoGenerateRequest,
    VideoGenerationResponse,
    VideoListResponse,
    VideoResponse,
)
from app.api.services.video_service import VideoService
from app.core.exceptions import NotFoundError
from app.database.connection import get_db

router = APIRouter()


@router.post(
    "/generate",
    response_model=VideoGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_video(
    request: VideoGenerateRequest,
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    try:
        video = await service.generate_video(
            script_id=request.script_id,
        )

        return VideoGenerationResponse(
            success=True,
            message="Video generated successfully.",
            video=VideoResponse.model_validate(video),
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post(
    "/{script_id}/regenerate",
    response_model=VideoGenerationResponse,
)
async def regenerate_video(
    script_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    try:
        video = await service.regenerate_video(
            script_id=script_id,
        )

        return VideoGenerationResponse(
            success=True,
            message="Video regenerated successfully.",
            video=VideoResponse.model_validate(video),
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get(
    "/script/{script_id}",
    response_model=VideoResponse,
)
async def get_video_by_script(
    script_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    try:
        video = await service.get_by_script(script_id)

        return VideoResponse.model_validate(video)

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/",
    response_model=VideoListResponse,
)
async def list_completed_videos(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    videos = await service.list_completed(limit=limit)

    return VideoListResponse(
        total=len(videos),
        items=[
            VideoResponse.model_validate(v)
            for v in videos
        ],
    )


@router.post(
    "/batch",
    response_model=VideoBatchGenerationResponse,
)
async def batch_generate_videos(
    limit: int = Query(default=5, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    results = await service.batch_generate(limit=limit)

    return VideoBatchGenerationResponse(
        success=True,
        message=f"Batch video generation completed for {len(results)} script(s).",
        generated_count=len(results),
    )


@router.get(
    "/{video_id}",
    response_model=VideoResponse,
)
async def get_video(
    video_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    try:
        video = await service.get_video(video_id)

        return VideoResponse.model_validate(video)

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.delete(
    "/{video_id}",
    response_model=VideoDeleteResponse,
)
async def delete_video(
    video_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VideoService(session)

    try:
        await service.delete_video(video_id)

        return VideoDeleteResponse(
            success=True,
            message="Video deleted successfully.",
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )