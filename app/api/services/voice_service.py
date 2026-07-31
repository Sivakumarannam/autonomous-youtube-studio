from uuid import UUID

from app.agents.voice_agent.models import VoiceSettings
from app.agents.voice_agent.service import VoiceAgentService
from app.core.exceptions import NotFoundError
from app.database.models.voice import Voice
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.voice_repository import VoiceRepository


class VoiceService:
    """
    Voice API Service.

    Responsibilities:
    - Validate Script
    - Prevent duplicate Voice records
    - Call VoiceAgent
    - Return ORM objects
    """

    def __init__(self, session):
        self.session = session

        self.script_repository = ScriptRepository(session)
        self.voice_repository = VoiceRepository(session)

        self.voice_agent = VoiceAgentService(session)

    async def generate_voice(
        self,
        script_id: UUID,
        provider: str = "mock",
        language: str = "en",
        speed: float = 1.0,
        pitch: float = 0.0,
        volume: float = 1.0,
    ) -> Voice:
        """
        Generate voice for a script.
        """

        script = await self.script_repository.get_by_id(script_id)

        if script is None:
            raise NotFoundError("Script", script_id)

        existing_voice = await self.voice_repository.get_by_script_id(
            script_id
        )

        if existing_voice is not None:
            return existing_voice

        settings = VoiceSettings(
            provider=provider,
            language=language,
            speed=speed,
            pitch=pitch,
            volume=volume,
        )

        await self.voice_agent.run_for_script(
            script=script,
            voice_settings=settings,
        )

        voice = await self.voice_repository.get_by_script_id(
            script_id
        )

        if voice is None:
            raise RuntimeError(
                "Voice generation completed but Voice record was not created."
            )

        return voice

    async def regenerate_voice(
        self,
        script_id: UUID,
        provider: str = "mock",
        language: str = "en",
        speed: float = 1.0,
        pitch: float = 0.0,
        volume: float = 1.0,
    ) -> Voice:
        """
        Force regenerate voice.
        """

        script = await self.script_repository.get_by_id(script_id)

        if script is None:
            raise NotFoundError("Script", script_id)

        existing = await self.voice_repository.get_by_script_id(
            script_id
        )

        if existing is not None:
            await self.voice_repository.delete_voice(existing)

        settings = VoiceSettings(
            provider=provider,
            language=language,
            speed=speed,
            pitch=pitch,
            volume=volume,
        )

        await self.voice_agent.run_for_script(
            script=script,
            voice_settings=settings,
        )

        voice = await self.voice_repository.get_by_script_id(
            script_id
        )

        if voice is None:
            raise RuntimeError(
                "Voice regeneration failed."
            )

        return voice

    async def get_voice(
        self,
        voice_id: UUID,
    ) -> Voice:
        """
        Get voice by id.
        """

        return await self.voice_repository.get_or_raise(
            voice_id
        )

    async def get_by_script(
        self,
        script_id: UUID,
    ) -> Voice:
        """
        Get voice by script id.
        """

        voice = await self.voice_repository.get_by_script_id(
            script_id
        )

        if voice is None:
            raise NotFoundError(
                "Voice",
                script_id,
            )

        return voice

    async def list_completed(
        self,
        limit: int = 20,
    ) -> list[Voice]:
        """
        List completed voices.
        """

        return await self.voice_repository.get_completed(
            limit=limit
        )

    async def batch_generate(
        self,
        limit: int = 5,
    ) -> list:
        """
        Generate voices for approved scripts.
        """

        return await self.voice_agent.run_for_approved_scripts(
            limit=limit
        )

    async def delete_voice(
        self,
        voice_id: UUID,
    ) -> None:
        """
        Delete voice.
        """

        voice = await self.voice_repository.get_or_raise(
            voice_id
        )

        await self.voice_repository.delete_voice(
            voice
        )