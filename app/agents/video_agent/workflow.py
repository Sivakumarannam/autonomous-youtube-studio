from __future__ import annotations

from typing import TypedDict

from app.agents.video_agent.agent import VideoAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class VideoWorkflowState(TypedDict):
    topic_title: str
    description: str
    script_type: str
    status: str
    output_path: str | None
    error: str | None


class VideoWorkflow:
    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, topic_title: str, description: str = "", script_type: str = "long") -> VideoWorkflowState:
        try:
            agent = VideoAgent(llm_provider=self._llm)
            output = await agent.generate_plan(topic_title=topic_title, description=description, script_type=script_type)
            return {"topic_title": topic_title, "description": description, "script_type": script_type, "status": "complete", "output_path": output.output_path, "error": None}
        except Exception as exc:
            logger.error("Video workflow failed", error=str(exc))
            return {"topic_title": topic_title, "description": description, "script_type": script_type, "status": "failed", "output_path": None, "error": str(exc)}