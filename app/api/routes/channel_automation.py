from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.channel_automation import ChannelAutomationResponse
from app.api.schemas.common import SuccessResponse
from app.api.services.channel_automation_service import ChannelAutomationService
from app.database.connection import get_db

router = APIRouter()


def get_channel_automation_service(
    session: AsyncSession = Depends(get_db),
) -> ChannelAutomationService:
    return ChannelAutomationService(session)


@router.post(
    "/{channel_id}/automation/start",
    response_model=SuccessResponse[ChannelAutomationResponse],
)
async def start_automation(
    channel_id: UUID,
    service: ChannelAutomationService = Depends(get_channel_automation_service),
) -> SuccessResponse[ChannelAutomationResponse]:
    automation = await service.start(channel_id)
    return SuccessResponse(data=automation, message="Channel automation started")


@router.post(
    "/{channel_id}/automation/pause",
    response_model=SuccessResponse[ChannelAutomationResponse],
)
async def pause_automation(
    channel_id: UUID,
    service: ChannelAutomationService = Depends(get_channel_automation_service),
) -> SuccessResponse[ChannelAutomationResponse]:
    automation = await service.pause(channel_id)
    return SuccessResponse(data=automation, message="Channel automation paused")


@router.post(
    "/{channel_id}/automation/delete",
    response_model=SuccessResponse[ChannelAutomationResponse],
)
async def delete_automation(
    channel_id: UUID,
    service: ChannelAutomationService = Depends(get_channel_automation_service),
) -> SuccessResponse[ChannelAutomationResponse]:
    automation = await service.delete(channel_id)
    return SuccessResponse(data=automation, message="Channel archived and automation stopped")


@router.get(
    "/{channel_id}/automation",
    response_model=SuccessResponse[ChannelAutomationResponse],
)
async def get_automation(
    channel_id: UUID,
    service: ChannelAutomationService = Depends(get_channel_automation_service),
) -> SuccessResponse[ChannelAutomationResponse]:
    automation = await service.get(channel_id)
    return SuccessResponse(data=automation)