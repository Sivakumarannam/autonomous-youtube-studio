from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.storyboard import (
    DeleteResponse,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
    StoryboardResponse,
    StoryboardUpdateRequest,
)
from app.api.services.storyboard_service import StoryboardAPIService
from app.database.connection import get_db

router = APIRouter(
    prefix="/storyboards",
)


@router.post(
    "/generate",
    response_model=StoryboardGenerateResponse,
)
async def generate_storyboard(
    request: StoryboardGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    service = StoryboardAPIService(db)

    return await service.generate(
        script_id=request.script_id,
        script=request.script,
    )


@router.get(
    "/{storyboard_id}",
    response_model=StoryboardResponse,
)
async def get_storyboard(
    storyboard_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = StoryboardAPIService(db)

    return await service.get(storyboard_id)


@router.put(
    "/{storyboard_id}",
    response_model=StoryboardResponse,
)
async def update_storyboard(
    storyboard_id: UUID,
    request: StoryboardUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    service = StoryboardAPIService(db)

    return await service.update(
        storyboard_id,
        request.scenes,
    )


@router.delete(
    "/{storyboard_id}",
    response_model=DeleteResponse,
)
async def delete_storyboard(
    storyboard_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = StoryboardAPIService(db)

    return await service.delete(storyboard_id)