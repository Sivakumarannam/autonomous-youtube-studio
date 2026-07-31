from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel
from app.database.models.channel_automation import AutomationStatus, ChannelAutomation
from app.database.repositories.base_repository import BaseRepository


class ChannelAutomationRepository(BaseRepository[ChannelAutomation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ChannelAutomation, session)

    async def get_by_channel_id(
        self, channel_id: UUID
    ) -> Optional[ChannelAutomation]:
        result = await self.session.execute(
            select(ChannelAutomation).where(
                ChannelAutomation.channel_id == channel_id
            )
        )
        return result.scalar_one_or_none()

    async def get_running(self) -> Sequence[ChannelAutomation]:
        """Return automation rows for channels that are RUNNING and not archived.

        Joined against Channel.is_archived so an archived (soft-deleted)
        channel is never picked up by the Daily Automation Scheduler even
        if its automation row was somehow left RUNNING.
        """
        result = await self.session.execute(
            select(ChannelAutomation)
            .join(Channel, Channel.id == ChannelAutomation.channel_id)
            .where(
                ChannelAutomation.automation_status == AutomationStatus.RUNNING,
                Channel.is_archived.is_(False),
            )
        )
        return result.scalars().all()
