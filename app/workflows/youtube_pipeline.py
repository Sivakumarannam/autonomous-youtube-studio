from __future__ import annotations

from app.agents.video_agent.agent import VideoAgent
from app.agents.upload_agent.agent import UploadAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class YouTubePipeline:
    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, topic_title: str, description: str = "", niche: str = "technology") -> dict:
        try:
            video_agent = VideoAgent(llm_provider=self._llm)
            upload_agent = UploadAgent(llm_provider=self._llm)
            video_output = await video_agent.generate_plan(topic_title=topic_title, description=description, niche=niche)
            upload_output = await upload_agent.prepare_upload(video_title=topic_title, description=description)
            return {
                "topic_title": topic_title,
                "status": "complete",
                "video_output": video_output.model_dump() if hasattr(video_output, "model_dump") else video_output.dict(),
                "upload_output": upload_output.model_dump() if hasattr(upload_output, "model_dump") else upload_output.dict(),
            }
        except Exception as exc:
            logger.error("YouTube pipeline failed", error=str(exc))
            return {"topic_title": topic_title, "status": "failed", "error": str(exc)}
