from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.common import SuccessResponse, MessageResponse
from app.api.schemas.pipeline import PipelineRunRequest, PipelineRunResponse
from app.api.services.pipeline_service import PipelineService
from app.database.connection import get_db
from app.database.models.pipeline_run import PipelineStatus

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def get_pipeline_service(session: AsyncSession = Depends(get_db)) -> PipelineService:
    return PipelineService(session)


@router.post(
    "/run",
    response_model=SuccessResponse[PipelineRunResponse],
    status_code=202,
    summary="Start a full pipeline run",
    description=(
        "Accepts a topic and produces a published (or scheduled) YouTube video "
        "in one call by sequencing: script → quality gate → video render → "
        "upload scheduling. Returns immediately with a pipeline_run_id; "
        "use GET /pipeline/{run_id} to poll progress."
    ),
)
@limiter.limit("5/minute")
async def start_pipeline(
    request: Request,
    data: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> SuccessResponse[PipelineRunResponse]:
    svc = PipelineService(session)
    run = await svc.start(
        topic_id=data.topic_id,
        channel_id=data.channel_id,
        script_type=data.script_type,
        background_tasks=background_tasks,
    )
    return SuccessResponse(
        data=PipelineRunResponse.model_validate(run),
        message=(
            "Pipeline run queued. Poll GET /api/v1/pipeline/{id} for progress."
        ),
    )


@router.get(
    "/{run_id}",
    response_model=SuccessResponse[PipelineRunResponse],
    summary="Get pipeline run status",
)
async def get_pipeline_run(
    run_id: UUID,
    service: PipelineService = Depends(get_pipeline_service),
) -> SuccessResponse[PipelineRunResponse]:
    run = await service.get(run_id)
    return SuccessResponse(data=PipelineRunResponse.model_validate(run))


@router.get(
    "",
    response_model=SuccessResponse[list[PipelineRunResponse]],
    summary="List pipeline runs",
)
async def list_pipeline_runs(
    status: Optional[PipelineStatus] = Query(None),
    topic_id: Optional[UUID] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    service: PipelineService = Depends(get_pipeline_service),
) -> SuccessResponse[list[PipelineRunResponse]]:
    runs = await service.list_runs(status=status, topic_id=topic_id, limit=limit)
    return SuccessResponse(
        data=[PipelineRunResponse.model_validate(r) for r in runs],
        message=f"{len(runs)} pipeline run(s) returned.",
    )