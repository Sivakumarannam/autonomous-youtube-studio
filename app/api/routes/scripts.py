from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import MessageResponse, PaginatedResponse, SuccessResponse
from app.api.schemas.script import ScriptGenerateRequest, ScriptResponse, ScriptUpdate
from app.api.services.script_service import ScriptService
from app.database.connection import get_db
from app.database.models.script import ScriptStatus, ScriptType

router = APIRouter()


def get_script_service(session: AsyncSession = Depends(get_db)) -> ScriptService:
    return ScriptService(session)


@router.post("/short", response_model=SuccessResponse[ScriptResponse], status_code=201)
async def generate_short_script(
    data: ScriptGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> SuccessResponse[ScriptResponse]:
    """Generate a Shorts script (9:16, 15-30s) for a topic."""
    from app.agents.short_script_agent.agent import ShortScriptAgent
    from app.llm_providers.factory import get_llm_provider
    from app.database.repositories.topic_repository import TopicRepository
    from app.database.repositories.research_repository import ResearchRepository

    topic_repo = TopicRepository(session)
    research_repo = ResearchRepository(session)

    topic = await topic_repo.get_by_id_or_raise(data.topic_id)
    research = await research_repo.get_by_topic_id(data.topic_id)

    agent = ShortScriptAgent(llm_provider=get_llm_provider())
    script = await agent.run(topic=topic, research=research, session=session)

    return SuccessResponse(
        data=ScriptResponse.model_validate(script),
        message="Short script generated",
    )


@router.post("/long", response_model=SuccessResponse[ScriptResponse], status_code=201)
async def generate_long_script(
    data: ScriptGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> SuccessResponse[ScriptResponse]:
    """Generate a long-form script (16:9, 8-10 min) for a topic."""
    from app.agents.long_script_agent.agent import LongScriptAgent
    from app.llm_providers.factory import get_llm_provider
    from app.database.repositories.topic_repository import TopicRepository
    from app.database.repositories.research_repository import ResearchRepository

    topic_repo = TopicRepository(session)
    research_repo = ResearchRepository(session)

    topic = await topic_repo.get_by_id_or_raise(data.topic_id)
    research = await research_repo.get_by_topic_id(data.topic_id)

    agent = LongScriptAgent(llm_provider=get_llm_provider())
    script = await agent.run(topic=topic, research=research, session=session)

    return SuccessResponse(
        data=ScriptResponse.model_validate(script),
        message="Long script generated",
    )


@router.get("", response_model=PaginatedResponse[ScriptResponse])
async def list_scripts(
    channel_id: Optional[UUID] = Query(None),
    script_type: Optional[ScriptType] = Query(None),
    status: Optional[ScriptStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ScriptService = Depends(get_script_service),
) -> PaginatedResponse[ScriptResponse]:
    if channel_id:
        scripts, total = await service.get_by_channel(channel_id, script_type, limit, offset)
    else:
        scripts, total = await service.get_all(limit, offset, script_type, status)

    return PaginatedResponse.build(
        data=[ScriptResponse.model_validate(s) for s in scripts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{script_id}", response_model=SuccessResponse[ScriptResponse])
async def get_script(
    script_id: UUID,
    service: ScriptService = Depends(get_script_service),
) -> SuccessResponse[ScriptResponse]:
    script = await service.get_by_id(script_id)
    return SuccessResponse(data=ScriptResponse.model_validate(script))


@router.patch("/{script_id}", response_model=SuccessResponse[ScriptResponse])
async def update_script(
    script_id: UUID,
    data: ScriptUpdate,
    service: ScriptService = Depends(get_script_service),
) -> SuccessResponse[ScriptResponse]:
    script = await service.update(script_id, data)
    return SuccessResponse(data=ScriptResponse.model_validate(script), message="Script updated")


@router.post("/{script_id}/approve", response_model=SuccessResponse[ScriptResponse])
async def approve_script(
    script_id: UUID,
    service: ScriptService = Depends(get_script_service),
) -> SuccessResponse[ScriptResponse]:
    script = await service.set_status(script_id, ScriptStatus.APPROVED)
    return SuccessResponse(data=ScriptResponse.model_validate(script), message="Script approved")


@router.post("/{script_id}/reject", response_model=SuccessResponse[ScriptResponse])
async def reject_script(
    script_id: UUID,
    service: ScriptService = Depends(get_script_service),
) -> SuccessResponse[ScriptResponse]:
    script = await service.set_status(script_id, ScriptStatus.REJECTED)
    return SuccessResponse(data=ScriptResponse.model_validate(script), message="Script rejected")


@router.delete("/{script_id}", response_model=MessageResponse)
async def delete_script(
    script_id: UUID,
    service: ScriptService = Depends(get_script_service),
) -> MessageResponse:
    await service.delete(script_id)
    return MessageResponse(message="Script deleted")