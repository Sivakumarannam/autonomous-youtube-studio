from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.thumbnail import (
    DeleteResponse,
    ThumbnailGenerateRequest,
    ThumbnailGenerateResponse,
    ThumbnailResponse,
    ThumbnailUpdateRequest,
)
from app.api.services.thumbnail_service import ThumbnailAPIService
from app.database.connection import get_db

router = APIRouter()


@router.post(
    "/generate",
    response_model=ThumbnailGenerateResponse,
)
async def generate_thumbnail(
    request: ThumbnailGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    service = ThumbnailAPIService(db)
    return await service.generate(
        script_id=request.script_id,
    )


@router.get(
    "/script/{script_id}",
    response_model=ThumbnailResponse,
)
async def get_thumbnail_by_script(
    script_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ThumbnailAPIService(db)
    return await service.get_by_script(script_id)


@router.get(
    "/{thumbnail_id}",
    response_model=ThumbnailResponse,
)
async def get_thumbnail(
    thumbnail_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ThumbnailAPIService(db)
    return await service.get(thumbnail_id)


@router.put(
    "/{thumbnail_id}",
    response_model=ThumbnailResponse,
)
async def update_thumbnail(
    thumbnail_id: UUID,
    request: ThumbnailUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    service = ThumbnailAPIService(db)
    return await service.update(
        thumbnail_id,
        concept=request.concept,
        file_path=request.file_path,
        status=request.status,
    )


@router.delete(
    "/{thumbnail_id}",
    response_model=DeleteResponse,
)
async def delete_thumbnail(
    thumbnail_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = ThumbnailAPIService(db)
    return await service.delete(thumbnail_id)