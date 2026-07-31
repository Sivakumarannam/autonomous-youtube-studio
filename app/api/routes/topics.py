from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import MessageResponse, PaginatedResponse, SuccessResponse
from app.api.schemas.topic import (
    TopicCreate,
    TopicGenerateRequest,
    TopicGenerateResponse,
    TopicResponse,
    TopicUpdate,
)
from app.api.services.topic_service import TopicService
from app.database.connection import get_db
from app.database.models.topic import TopicStatus

router = APIRouter()


def get_topic_service(session: AsyncSession = Depends(get_db)) -> TopicService:
    return TopicService(session)


@router.post("/generate", response_model=SuccessResponse[TopicGenerateResponse])
async def generate_topics(
    data: TopicGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> SuccessResponse[TopicGenerateResponse]:
    """Trigger the Topic Agent to discover and store trending topics."""
    from app.agents.topic_agent.agent import TopicAgent
    from app.llm_providers.factory import get_llm_provider

    service = TopicService(session)
    agent = TopicAgent(llm_provider=get_llm_provider())

    generated_raw = await agent.run(
        channel_id=data.channel_id,
        count=data.count,
        sources=data.sources,
        content_type=data.content_type,
    )

    topics = await service.save_generated_topics(
        channel_id=data.channel_id,
        generated=generated_raw,
        source=data.sources[0] if data.sources else "google_trends",
        content_type=data.content_type,
    )

    return SuccessResponse(
        data=TopicGenerateResponse(
            generated=len(topics),
            topics=[TopicResponse.model_validate(t) for t in topics],
        ),
        message=f"Generated and saved {len(topics)} topics",
    )


@router.post("", response_model=SuccessResponse[TopicResponse], status_code=201)
async def create_topic(
    data: TopicCreate,
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[TopicResponse]:
    topic = await service.create(data)
    return SuccessResponse(data=TopicResponse.model_validate(topic), message="Topic created")


@router.get("", response_model=PaginatedResponse[TopicResponse])
async def list_topics(
    channel_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: TopicService = Depends(get_topic_service),
) -> PaginatedResponse[TopicResponse]:
    if channel_id:
        topics, total = await service.get_by_channel(channel_id, limit=limit, offset=offset)
    else:
        topics, total = await service.get_all(limit=limit, offset=offset)

    return PaginatedResponse.build(
        data=[TopicResponse.model_validate(t) for t in topics],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/pending", response_model=SuccessResponse[list[TopicResponse]])
async def list_pending_topics(
    channel_id: Optional[UUID] = Query(None),
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[list[TopicResponse]]:
    topics = await service.get_pending(channel_id=channel_id)
    return SuccessResponse(data=[TopicResponse.model_validate(t) for t in topics])


@router.get("/{topic_id}", response_model=SuccessResponse[TopicResponse])
async def get_topic(
    topic_id: UUID,
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[TopicResponse]:
    topic = await service.get_by_id(topic_id)
    return SuccessResponse(data=TopicResponse.model_validate(topic))


@router.patch("/{topic_id}", response_model=SuccessResponse[TopicResponse])
async def update_topic(
    topic_id: UUID,
    data: TopicUpdate,
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[TopicResponse]:
    topic = await service.update(topic_id, data)
    return SuccessResponse(data=TopicResponse.model_validate(topic), message="Topic updated")


@router.post("/{topic_id}/approve", response_model=SuccessResponse[TopicResponse])
async def approve_topic(
    topic_id: UUID,
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[TopicResponse]:
    topic = await service.set_status(topic_id, TopicStatus.RESEARCHING)
    return SuccessResponse(data=TopicResponse.model_validate(topic), message="Topic approved for research")


@router.post("/{topic_id}/reject", response_model=SuccessResponse[TopicResponse])
async def reject_topic(
    topic_id: UUID,
    service: TopicService = Depends(get_topic_service),
) -> SuccessResponse[TopicResponse]:
    topic = await service.set_status(topic_id, TopicStatus.REJECTED)
    return SuccessResponse(data=TopicResponse.model_validate(topic), message="Topic rejected")


@router.delete("/{topic_id}", response_model=MessageResponse)
async def delete_topic(
    topic_id: UUID,
    service: TopicService = Depends(get_topic_service),
) -> MessageResponse:
    await service.delete(topic_id)
    return MessageResponse(message="Topic deleted")