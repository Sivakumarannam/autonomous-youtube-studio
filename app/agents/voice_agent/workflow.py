from __future__ import annotations

from typing import TypedDict

from app.agents.voice_agent.models import VoiceSettings
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class VoiceWorkflowState(TypedDict):
    script_id: str
    script_content: str
    script_type: str
    language: str
    provider: str
    speed: float
    # outputs
    audio_file_path: str | None
    duration_seconds: float
    word_count: int
    provider_used: str
    file_size_bytes: int
    success: bool
    error_message: str | None
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def synthesise_voice_node(
    state: VoiceWorkflowState,
    llm: BaseLLMProvider,
) -> VoiceWorkflowState:
    logger.info("Node: synthesise_voice", script_id=state["script_id"])
    try:
        from app.agents.voice_agent.agent import VoiceAgent

        voice_settings = VoiceSettings(
            language=state["language"],
            speed=state["speed"],
            provider=state["provider"],
        )

        agent = VoiceAgent(llm_provider=llm)
        output = await agent.synthesise(
            script_content=state["script_content"],
            script_id=state["script_id"],
            script_type=state["script_type"],
            voice_settings=voice_settings,
        )

        return {
            **state,
            "audio_file_path": output.audio_file_path,
            "duration_seconds": output.duration_seconds,
            "word_count": output.word_count,
            "provider_used": output.provider_used,
            "file_size_bytes": output.file_size_bytes,
            "success": output.success,
            "error_message": output.error_message,
            "status": "complete",
        }
    except Exception as exc:
        return {**state, "error": str(exc), "success": False, "status": "failed"}


class VoiceWorkflow:
    """LangGraph-style voice synthesis workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script_id: str,
        script_content: str,
        script_type: str = "long",
        language: str = "en",
        provider: str = "mock",
        speed: float = 1.0,
    ) -> VoiceWorkflowState:
        state: VoiceWorkflowState = {
            "script_id": script_id,
            "script_content": script_content,
            "script_type": script_type,
            "language": language,
            "provider": provider,
            "speed": speed,
            "audio_file_path": None,
            "duration_seconds": 0.0,
            "word_count": 0,
            "provider_used": "",
            "file_size_bytes": 0,
            "success": False,
            "error_message": None,
            "error": None,
            "status": "running",
        }

        state = await synthesise_voice_node(state, self._llm)

        logger.info(
            "VoiceWorkflow complete",
            script_id=script_id,
            status=state["status"],
            duration=state["duration_seconds"],
            provider=state["provider_used"],
        )
        return state