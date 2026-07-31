from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.models.voice import Voice, VoiceStatus
from app.database.repositories.base_repository import BaseRepository


class VoiceRepository(BaseRepository[Voice]):
    """
    Repository for Voice model.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Voice, session)

    async def get_by_script_id(
        self,
        script_id: UUID,
    ) -> Voice | None:
        """
        Return the voice record for a script.
        """
        result = await self.session.execute(
            select(Voice).where(
                Voice.script_id == script_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_raise(
        self,
        voice_id: UUID,
    ) -> Voice:
        """
        Return a voice or raise NotFoundError.
        """
        voice = await self.get_by_id(voice_id)

        if voice is None:
            raise NotFoundError("Voice", voice_id)

        return voice

    async def get_pending(
        self,
        limit: int = 10,
    ) -> list[Voice]:
        """
        Get pending voice generation jobs.
        """
        result = await self.session.execute(
            select(Voice)
            .where(
                Voice.status == VoiceStatus.PENDING
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_generating(
        self,
        limit: int = 10,
    ) -> list[Voice]:
        """
        Get currently generating voices.
        """
        result = await self.session.execute(
            select(Voice)
            .where(
                Voice.status == VoiceStatus.GENERATING
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_completed(
        self,
        limit: int = 20,
    ) -> list[Voice]:
        """
        Get completed voices.
        """
        result = await self.session.execute(
            select(Voice)
            .where(
                Voice.status == VoiceStatus.COMPLETE
            )
            .order_by(
                Voice.created_at.desc()
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_voice(
        self,
        voice: Voice,
        **kwargs,
    ) -> Voice:
        """
        Update a voice record.
        """
        return await self.update(
            voice,
            **kwargs,
        )

    async def mark_generating(
        self,
        voice: Voice,
    ) -> Voice:
        return await self.update(
            voice,
            status=VoiceStatus.GENERATING,
        )

    async def mark_complete(
        self,
        voice: Voice,
        audio_path: str,
        duration: float,
        file_size: int,
        word_count: int,
    ) -> Voice:
        return await self.update(
            voice,
            status=VoiceStatus.COMPLETE,
            audio_path=audio_path,
            duration=duration,
            file_size=file_size,
            word_count=word_count,
            error_message=None,
        )

    async def mark_failed(
        self,
        voice: Voice,
        error_message: str,
    ) -> Voice:
        return await self.update(
            voice,
            status=VoiceStatus.FAILED,
            error_message=error_message,
        )

    async def delete_voice(
        self,
        voice: Voice,
    ) -> None:
        """
        Delete a voice record.
        """
        await self.delete(voice)