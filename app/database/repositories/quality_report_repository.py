from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.quality_report import QualityReport, QualityStatus
from app.database.repositories.base_repository import BaseRepository


class QualityReportRepository(BaseRepository[QualityReport]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(QualityReport, session)

    async def get_by_script_id(self, script_id: UUID) -> Sequence[QualityReport]:
        result = await self.session.execute(
            select(QualityReport)
            .where(QualityReport.script_id == script_id)
            .order_by(desc(QualityReport.created_at))
        )
        return result.scalars().all()

    async def get_latest_for_script(self, script_id: UUID) -> Optional[QualityReport]:
        result = await self.session.execute(
            select(QualityReport)
            .where(QualityReport.script_id == script_id)
            .order_by(
                QualityReport.created_at.desc(),
                QualityReport.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_status(self, status: QualityStatus, limit: int = 50) -> Sequence[QualityReport]:
        result = await self.session.execute(
            select(QualityReport)
            .where(QualityReport.status == status)
            .order_by(desc(QualityReport.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_failed(self, limit: int = 50) -> Sequence[QualityReport]:
        return await self.get_by_status(QualityStatus.FAILED, limit)

    async def get_passed(self, limit: int = 50) -> Sequence[QualityReport]:
        return await self.get_by_status(QualityStatus.PASSED, limit)

    async def script_has_passed(self, script_id: UUID) -> bool:
        result = await self.session.execute(
            select(QualityReport).where(
                and_(
                    QualityReport.script_id == script_id,
                    QualityReport.passed.is_(True),
                )
            )
        )
        return result.scalar_one_or_none() is not None