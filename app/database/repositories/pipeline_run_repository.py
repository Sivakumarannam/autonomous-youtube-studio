from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.models.pipeline_run import PipelineRun, PipelineStatus
from app.database.repositories.base_repository import BaseRepository
from app.monitoring.metrics import PIPELINE_RUNS_TOTAL
from app.websocket.manager import broadcast_safe


class PipelineRunRepository(BaseRepository[PipelineRun]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PipelineRun, session)

    async def update(self, obj: PipelineRun, **kwargs: Any) -> PipelineRun:
        """Update a PipelineRun and broadcast the change over WebSocket.

        Every stage/status transition in PipelineAgentService goes through
        this single method, so hooking the broadcast + metric here covers
        all live-update cases without scattering WebSocket/metrics calls
        across the agent's stage logic.
        """
        updated = await super().update(obj, **kwargs)

        if "status" in kwargs:
            PIPELINE_RUNS_TOTAL.labels(status=updated.status.value).inc()

        await broadcast_safe(
            {
                "type": "pipeline_run",
                "event": "updated",
                "id": str(updated.id),
                "status": updated.status.value,
                "current_stage": updated.current_stage,
                "failed_stage": updated.failed_stage,
                "retry_count": updated.retry_count,
            }
        )
        return updated

    async def get_or_raise(self, run_id: UUID) -> PipelineRun:
        run = await self.get_by_id(run_id)
        if run is None:
            raise NotFoundError("PipelineRun", run_id)
        return run

    async def get_by_topic_id(
        self, topic_id: UUID, limit: int = 20
    ) -> Sequence[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun)
            .where(PipelineRun.topic_id == topic_id)
            .order_by(desc(PipelineRun.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_status(
        self,
        status: PipelineStatus,
        limit: int = 50,
    ) -> Sequence[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun)
            .where(PipelineRun.status == status)
            .order_by(desc(PipelineRun.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_latest(self, limit: int = 20) -> Sequence[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.script))
            .order_by(desc(PipelineRun.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def has_running_for_channel(self, channel_id: UUID) -> bool:
        """Overlap protection for the Daily Automation Scheduler.

        Mirrors the existing max_instances=1 philosophy of the Publish
        Scheduler: never create a second concurrent PipelineRun for the
        same channel.
        """
        result = await self.session.execute(
            select(PipelineRun.id)
            .where(
                PipelineRun.channel_id == channel_id,
                PipelineRun.status == PipelineStatus.RUNNING,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None