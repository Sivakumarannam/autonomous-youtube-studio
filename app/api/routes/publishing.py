from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import SuccessResponse
from app.api.schemas.publishing import (
    UploadPublishResponse,
    RejectRequest,
    ScheduleRequest,
)
from app.api.services.publishing_service import PublishingService
from app.database.connection import get_db
from app.database.models.upload import PublishStatus

router = APIRouter()


def get_publishing_service(
    session: AsyncSession = Depends(get_db),
) -> PublishingService:
    return PublishingService(session)


@router.get(
    "",
    response_model=SuccessResponse[list[UploadPublishResponse]],
    summary="List uploads with publish status",
)
async def list_uploads(
    publish_status: Optional[PublishStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: PublishingService = Depends(get_publishing_service),
) -> SuccessResponse[list[UploadPublishResponse]]:
    uploads = await service.list_uploads(
        publish_status=publish_status, limit=limit, offset=offset
    )
    return SuccessResponse(
        data=[UploadPublishResponse.model_validate(u) for u in uploads],
        message=f"{len(uploads)} upload(s) returned.",
    )


@router.get(
    "/{upload_id}",
    response_model=SuccessResponse[UploadPublishResponse],
    summary="Get upload publish status",
)
async def get_upload(
    upload_id: UUID,
    service: PublishingService = Depends(get_publishing_service),
) -> SuccessResponse[UploadPublishResponse]:
    upload = await service.get(upload_id)
    return SuccessResponse(data=UploadPublishResponse.model_validate(upload))


@router.post(
    "/{upload_id}/approve",
    response_model=SuccessResponse[UploadPublishResponse],
    summary="Approve a draft upload (manual mode)",
    description=(
        "Advances publish_status from DRAFT to APPROVED. "
        "Used when auto_publish_enabled=False and a human reviewer has signed off. "
        "Follow up with POST /{id}/schedule to set scheduled_at and trigger the Scheduler."
    ),
)
async def approve_upload(
    upload_id: UUID,
    service: PublishingService = Depends(get_publishing_service),
) -> SuccessResponse[UploadPublishResponse]:
    upload = await service.approve(upload_id)
    return SuccessResponse(
        data=UploadPublishResponse.model_validate(upload),
        message="Upload approved. Call /schedule to set a publish time.",
    )


@router.post(
    "/{upload_id}/reject",
    response_model=SuccessResponse[UploadPublishResponse],
    summary="Reject an approved/scheduled upload",
    description=(
        "Flips publish_status to REJECTED for any upload in APPROVED or SCHEDULED "
        "state. Use this during the delay window to halt an upload before the "
        "Scheduler fires. Uploads already UPLOADING or PUBLISHED cannot be rejected."
    ),
)
async def reject_upload(
    upload_id: UUID,
    body: RejectRequest = RejectRequest(),
    service: PublishingService = Depends(get_publishing_service),
) -> SuccessResponse[UploadPublishResponse]:
    upload = await service.reject(upload_id, reason=body.reason)
    return SuccessResponse(
        data=UploadPublishResponse.model_validate(upload),
        message="Upload rejected. The Scheduler will not process it.",
    )


@router.post(
    "/{upload_id}/schedule",
    response_model=SuccessResponse[UploadPublishResponse],
    summary="Manually schedule an approved upload",
    description=(
        "Sets scheduled_at on an APPROVED upload and moves publish_status to "
        "SCHEDULED. The Scheduler will trigger the YouTube upload once "
        "scheduled_at passes."
    ),
)
async def schedule_upload(
    upload_id: UUID,
    body: ScheduleRequest,
    service: PublishingService = Depends(get_publishing_service),
) -> SuccessResponse[UploadPublishResponse]:
    upload = await service.schedule(upload_id, scheduled_at=body.scheduled_at)
    return SuccessResponse(
        data=UploadPublishResponse.model_validate(upload),
        message=f"Upload scheduled for {body.scheduled_at.isoformat()}.",
    )