from __future__ import annotations

from typing import TypedDict

from app.agents.upload_agent.agent import UploadAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class UploadWorkflowState(TypedDict):
    video_title: str
    description: str
    status: str
    error: str | None


class UploadWorkflow:
    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, video_title: str, description: str = "") -> UploadWorkflowState:
        try:
            agent = UploadAgent(llm_provider=self._llm)
            output = await agent.prepare_upload(video_title=video_title, description=description)
            return {"video_title": output.video_title, "description": description, "status": output.status, "error": None}
        except Exception as exc:
            logger.error("Upload workflow failed", error=str(exc))
            return {"video_title": video_title, "description": description, "status": "failed", "error": str(exc)}
