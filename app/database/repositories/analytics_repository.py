from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.models.analytics import Analytics
from app.database.repositories.base_repository import BaseRepository


class AnalyticsRepository(BaseRepository[Analytics]):
    """Repository for Analytics snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Analytics, session)

    async def get_by_upload_id(self, upload_id: UUID) -> list[Analytics]:
        result = await self.session.execute(
            select(Analytics)
            .where(Analytics.upload_id == upload_id)
            .order_by(Analytics.snapshot_date.desc())
        )
        return list(result.scalars().all())

    async def get_latest_by_upload_id(self, upload_id: UUID) -> Analytics | None:
        result = await self.session.execute(
            select(Analytics)
            .where(Analytics.upload_id == upload_id)
            .order_by(Analytics.snapshot_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, analytics_id: UUID) -> Analytics:
        obj = await self.get_by_id(analytics_id)
        if obj is None:
            raise NotFoundError("Analytics", analytics_id)
        return obj