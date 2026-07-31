from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.channel import ChannelCreate, ChannelResponse, ChannelUpdate
from app.api.schemas.common import MessageResponse, PaginatedResponse, SuccessResponse
from app.api.services.channel_service import ChannelService
from app.database.connection import get_db
from app.database.models.channel import ChannelStatus

router = APIRouter()


def get_channel_service(session: AsyncSession = Depends(get_db)) -> ChannelService:
    return ChannelService(session)


@router.post("", response_model=SuccessResponse[ChannelResponse], status_code=201)
async def create_channel(
    data: ChannelCreate,
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[ChannelResponse]:
    channel = await service.create(data)
    return SuccessResponse(data=ChannelResponse.model_validate(channel), message="Channel created")


@router.get("", response_model=PaginatedResponse[ChannelResponse])
async def list_channels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ChannelService = Depends(get_channel_service),
) -> PaginatedResponse[ChannelResponse]:
    channels, total = await service.get_all(limit=limit, offset=offset)
    return PaginatedResponse.build(
        data=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/active", response_model=SuccessResponse[list[ChannelResponse]])
async def list_active_channels(
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[list[ChannelResponse]]:
    channels = await service.get_active()
    return SuccessResponse(data=[ChannelResponse.model_validate(c) for c in channels])


@router.get("/{channel_id}", response_model=SuccessResponse[ChannelResponse])
async def get_channel(
    channel_id: UUID,
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[ChannelResponse]:
    channel = await service.get_by_id(channel_id)
    return SuccessResponse(data=ChannelResponse.model_validate(channel))


@router.patch("/{channel_id}", response_model=SuccessResponse[ChannelResponse])
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdate,
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[ChannelResponse]:
    channel = await service.update(channel_id, data)
    return SuccessResponse(data=ChannelResponse.model_validate(channel), message="Channel updated")


@router.delete("/{channel_id}", response_model=MessageResponse)
async def delete_channel(
    channel_id: UUID,
    service: ChannelService = Depends(get_channel_service),
) -> MessageResponse:
    await service.delete(channel_id)
    return MessageResponse(message="Channel deleted")


@router.post("/{channel_id}/pause", response_model=SuccessResponse[ChannelResponse])
async def pause_channel(
    channel_id: UUID,
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[ChannelResponse]:
    channel = await service.set_status(channel_id, ChannelStatus.PAUSED)
    return SuccessResponse(data=ChannelResponse.model_validate(channel), message="Channel paused")


@router.post("/{channel_id}/activate", response_model=SuccessResponse[ChannelResponse])
async def activate_channel(
    channel_id: UUID,
    service: ChannelService = Depends(get_channel_service),
) -> SuccessResponse[ChannelResponse]:
    channel = await service.set_status(channel_id, ChannelStatus.ACTIVE)
    return SuccessResponse(data=ChannelResponse.model_validate(channel), message="Channel activated")