from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import PaginatedResponse, SuccessResponse
from app.api.schemas.research import ResearchDetail, ResearchRequest, ResearchResponse
from app.api.services.research_service import ResearchService
from app.database.connection import get_db

router = APIRouter()


def get_research_service(session: AsyncSession = Depends(get_db)) -> ResearchService:
    return ResearchService(session)


@router.post("", response_model=SuccessResponse[ResearchResponse])
async def run_research(
    data: ResearchRequest,
    session: AsyncSession = Depends(get_db),
) -> SuccessResponse[ResearchResponse]:
    """Trigger the Research Agent for a specific topic."""
    from app.agents.research_agent.agent import ResearchAgent
    from app.llm_providers.factory import get_llm_provider
    from app.database.repositories.topic_repository import TopicRepository

    topic_repo = TopicRepository(session)
    topic = await topic_repo.get_by_id_or_raise(data.topic_id)

    agent = ResearchAgent(llm_provider=get_llm_provider())
    result = await agent.run(topic=topic)

    service = ResearchService(session)
    import json
    research = await service.create_or_update(
        topic_id=data.topic_id,
        summary=result.get("summary", ""),
        key_facts=json.dumps(result.get("key_facts", [])),
        references=json.dumps(result.get("references", [])),
        raw_data=json.dumps(result),
    )

    return SuccessResponse(
        data=ResearchResponse.model_validate(research),
        message="Research completed",
    )


@router.get("", response_model=PaginatedResponse[ResearchResponse])
async def list_research(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ResearchService = Depends(get_research_service),
) -> PaginatedResponse[ResearchResponse]:
    research_list, total = await service.get_all(limit=limit, offset=offset)
    return PaginatedResponse.build(
        data=[ResearchResponse.model_validate(r) for r in research_list],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/topic/{topic_id}", response_model=SuccessResponse[ResearchDetail])
async def get_research_for_topic(
    topic_id: UUID,
    service: ResearchService = Depends(get_research_service),
) -> SuccessResponse[ResearchDetail]:
    from app.core.exceptions import NotFoundError
    research = await service.get_by_topic_id(topic_id)
    if research is None:
        raise NotFoundError("Research", topic_id)
    return SuccessResponse(data=ResearchDetail.model_validate(research))


@router.get("/{research_id}", response_model=SuccessResponse[ResearchDetail])
async def get_research(
    research_id: UUID,
    service: ResearchService = Depends(get_research_service),
) -> SuccessResponse[ResearchDetail]:
    research = await service.get_by_id(research_id)
    return SuccessResponse(data=ResearchDetail.model_validate(research))