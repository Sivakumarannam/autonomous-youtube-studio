import json
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.voice_agent.agent import VoiceAgent
from app.agents.voice_agent.models import VoiceAgentOutput, VoiceSettings
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.script import Script
from app.database.models.video import Video, VideoStatus
from app.database.models.voice import (
    Voice,
    VoiceProvider,
    VoiceStatus,
)
from app.database.repositories.script_repository import ScriptRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


class VoiceAgentService:
    """
    Orchestrates the Voice Agent with DB persistence.

    Generates audio for a Script, creates/updates the Voice record,
    updates the linked Video record, and logs execution.
    """

    AGENT_NAME = "VoiceAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._script_repo = ScriptRepository(session)

    async def run_for_script(
        self,
        script: Script,
        voice_settings: VoiceSettings | None = None,
    ) -> VoiceAgentOutput:
        start = time.monotonic()

        agent = VoiceAgent(
            llm_provider=get_llm_provider(),
        )

        if voice_settings is None:
            voice_settings = VoiceSettings()

        try:
            output = await agent.run(
                script=script,
                voice_settings=voice_settings,
            )

        except Exception as exc:
            await self._log(
                AgentLogLevel.ERROR,
                f"Voice generation failed: {exc}",
                entity_id=str(script.id),
                execution_time=time.monotonic() - start,
            )
            raise

        # ---------------------------------------------------------
        # Upsert Voice record
        # ---------------------------------------------------------

        result = await self._session.execute(
            select(Voice).where(
                Voice.script_id == script.id
            )
        )

        voice = result.scalar_one_or_none()

        if voice is None:
            voice = Voice(
                script_id=script.id,
                provider=VoiceProvider(output.provider_used),
                status=VoiceStatus.COMPLETE,
                language=voice_settings.language,
                voice_gender=voice_settings.gender,
                speaker="default",
                audio_path=output.audio_file_path,
                duration=output.duration_seconds,
                word_count=output.word_count,
                file_size=output.file_size_bytes,
                sample_rate=44100,
                bitrate="128k",
                transcript=script.content,
            )
        else:
            voice.provider = VoiceProvider(output.provider_used)
            voice.status = VoiceStatus.COMPLETE
            voice.language = voice_settings.language
            voice.voice_gender = voice_settings.gender
            voice.audio_path = output.audio_file_path
            voice.duration = output.duration_seconds
            voice.word_count = output.word_count
            voice.file_size = output.file_size_bytes
            voice.sample_rate = 44100
            voice.bitrate = "128k"
            voice.transcript = script.content

        self._session.add(voice)

        # Mirror the actual narrated gender onto Script for convenience —
        # Voice.voice_gender above remains the authoritative source.
        script.voice_gender = voice_settings.gender
        self._session.add(script)   

        # ---------------------------------------------------------
        # Upsert Video record
        # ---------------------------------------------------------

        result = await self._session.execute(
            select(Video).where(
                Video.script_id == script.id
            )
        )

        video = result.scalar_one_or_none()

        if video:
            video.audio_path = output.audio_file_path
            video.status = VideoStatus.GENERATING
            self._session.add(video)

        else:
            video = Video(
                script_id=script.id,
                audio_path=output.audio_file_path,
                status=VideoStatus.GENERATING,
                resolution=(
                    "1920x1080"
                    if str(script.script_type) == "long"
                    else "1080x1920"
                ),
            )

            self._session.add(video)

        await self._session.flush()

        elapsed = time.monotonic() - start

        await self._log(
            AgentLogLevel.INFO,
            (
                f"Audio generated "
                f"({output.duration_seconds:.1f}s, "
                f"provider={output.provider_used})"
            ),
            context=json.dumps(
                {
                    "script_id": str(script.id),
                    "audio_path": output.audio_file_path,
                    "duration": output.duration_seconds,
                    "provider": output.provider_used,
                }
            ),
            entity_id=str(script.id),
            execution_time=elapsed,
        )

        return output

    async def run_for_approved_scripts(
        self,
        limit: int = 5,
    ) -> list[VoiceAgentOutput]:

        scripts = await self._script_repo.get_approved(
            limit=limit,
        )

        results: list[VoiceAgentOutput] = []

        for script in scripts:
            try:
                output = await self.run_for_script(
                    script,
                )

                results.append(output)

            except Exception as exc:
                logger.error(
                    "Voice batch failed",
                    script_id=str(script.id),
                    error=str(exc),
                )

        return results

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:

        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type="script",
            entity_id=entity_id,
            execution_time=execution_time,
        )

        self._session.add(entry)
        await self._session.flush()