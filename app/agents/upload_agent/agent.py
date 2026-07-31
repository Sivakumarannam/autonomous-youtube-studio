import json
import re
import time
from typing import Optional

from app.agents.upload_agent.models import UploadAgentOutput, UploadSettings
from app.agents.upload_agent.prompts import UPLOAD_SYSTEM_PROMPT, build_upload_prompt
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class UploadAgent:
    AGENT_NAME = "UploadAgent"

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, video_title: str, description: str = "", settings: Optional[UploadSettings] = None, script_type: str = "long") -> UploadAgentOutput:
        return await self.prepare_upload(video_title=video_title, description=description, settings=settings, script_type=script_type)

    async def prepare_upload(self, video_title: str, description: str = "", settings: Optional[UploadSettings] = None, script_type: str = "long") -> UploadAgentOutput:
        if settings is None:
            settings = UploadSettings()
        prompt = build_upload_prompt(video_title=video_title, description=description, tags=settings.tags, script_type=script_type)
        try:
            raw = await self._llm.generate_text(prompt=prompt, system=UPLOAD_SYSTEM_PROMPT, temperature=0.2, max_tokens=1024)
            return self._parse(raw, video_title, settings)
        except Exception as exc:
            logger.warning("Upload planning failed; using fallback", error=str(exc))
            return UploadAgentOutput(video_title=video_title, description=description, tags=settings.tags, status="ready", provider_used="mock", success=True)

    def _parse(self, raw: str, video_title: str, settings: UploadSettings) -> UploadAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return UploadAgentOutput(video_title=video_title, description=settings.description or "", tags=settings.tags, status="ready", provider_used="mock", success=True)
        return UploadAgentOutput(
            video_title=str(data.get("title", video_title)),
            description=str(data.get("description", settings.description or "")),
            tags=list(data.get("tags", settings.tags)),
            pinned_comment=str(data.get("pinned_comment", "")),
            status=str(data.get("status", "ready")),
            provider_used="mock",
            success=True,
        )
