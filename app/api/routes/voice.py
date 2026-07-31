from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.voice import (
    VoiceGenerateRequest,
    VoiceGenerationResponse,
    VoiceListResponse,
    VoiceResponse,
    VoiceDeleteResponse,
)
from app.api.services.voice_service import VoiceService
from app.core.exceptions import NotFoundError
from app.database.connection import get_db

router = APIRouter()


@router.post(
    "/generate",
    response_model=VoiceGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_voice(
    request: VoiceGenerateRequest,
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    try:
        voice = await service.generate_voice(
            script_id=request.script_id,
            provider=request.provider.value,
            language=request.language,
            speed=request.speed,
        )

        return VoiceGenerationResponse(
            success=True,
            message="Voice generated successfully.",
            voice=VoiceResponse.model_validate(voice),
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
    response_model=VoiceGenerationResponse,
)
async def regenerate_voice(
    script_id: UUID,
    provider: str = Query(default="mock"),
    language: str = Query(default="en"),
    speed: float = Query(default=1.0),
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    try:
        voice = await service.regenerate_voice(
            script_id=script_id,
            provider=provider,
            language=language,
            speed=speed,
        )

        return VoiceGenerationResponse(
            success=True,
            message="Voice regenerated successfully.",
            voice=VoiceResponse.model_validate(voice),
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
    "/{voice_id}",
    response_model=VoiceResponse,
)
async def get_voice(
    voice_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    try:
        voice = await service.get_voice(voice_id)

        return VoiceResponse.model_validate(voice)

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/script/{script_id}",
    response_model=VoiceResponse,
)
async def get_voice_by_script(
    script_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    try:
        voice = await service.get_by_script(script_id)

        return VoiceResponse.model_validate(voice)

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/",
    response_model=VoiceListResponse,
)
async def list_completed_voices(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    voices = await service.list_completed(limit=limit)

    return VoiceListResponse(
        total=len(voices),
        items=[
            VoiceResponse.model_validate(v)
            for v in voices
        ],
    )


@router.post(
    "/batch",
)
async def batch_generate_voices(
    limit: int = Query(default=5, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    results = await service.batch_generate(limit=limit)

    return {
        "success": True,
        "count": len(results),
        "results": results,
    }


@router.delete(
    "/{voice_id}",
    response_model=VoiceDeleteResponse,
)
async def delete_voice(
    voice_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    service = VoiceService(session)

    try:
        await service.delete_voice(voice_id)

        return VoiceDeleteResponse(
            success=True,
            message="Voice deleted successfully.",
        )

    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )