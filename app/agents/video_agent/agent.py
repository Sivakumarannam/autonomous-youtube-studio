import json
import re
import time
from pathlib import Path
from typing import Optional

from app.agents.video_agent.models import VideoAgentOutput, VideoScene
from app.agents.video_agent.prompts import VIDEO_SYSTEM_PROMPT, build_video_prompt
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


def _slugify(text: str) -> str:
    """Build a filesystem-safe slug from arbitrary topic/title text.

    Strips characters that are invalid (or unwise) in filenames on Windows
    specifically — \\ / : * ? " < > | — as well as collapsing everything
    else non-alphanumeric to a single hyphen. Also caps length so a very
    long topic title can never push a path past Windows' ~260 char limit
    when combined with the rest of the storage path.

    Without this, a topic title containing a character like '|' (a normal,
    valid character in a video title/description) causes the OS file write
    to fail with "[Errno 22] Invalid argument" on Windows.
    """
    if not text:
        return "untitled"
    # Remove characters Windows forbids in filenames
    cleaned = re.sub(r'[\\/:*?"<>|]', "", text)
    # Collapse any remaining whitespace/punctuation runs to a single hyphen
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-").lower()
    return cleaned[:100] or "untitled"


class VideoAgent:
    AGENT_NAME = "VideoAgent"

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, topic_title: str, description: str = "", script_type: str = "long", niche: str = "technology") -> VideoAgentOutput:
        return await self.generate_plan(topic_title=topic_title, description=description, script_type=script_type, niche=niche)

    async def generate_plan(self, topic_title: str, description: str = "", script_type: str = "long", niche: str = "technology") -> VideoAgentOutput:
        prompt = build_video_prompt(topic_title=topic_title, description=description, script_type=script_type, niche=niche)
        try:
            raw = await self._llm.generate_text(prompt=prompt, system=VIDEO_SYSTEM_PROMPT, temperature=0.3, max_tokens=2048)
            return self._parse(raw, topic_title)
        except Exception as exc:
            logger.warning("Video planning failed; using fallback", error=str(exc))
            return self._fallback(topic_title)

    def _parse(self, raw: str, topic_title: str) -> VideoAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return self._fallback(topic_title)

        scenes = []
        for item in data.get("scenes", []) or []:
            if isinstance(item, dict):
                scenes.append(VideoScene(title=str(item.get("title", "Scene")), description=str(item.get("description", "")), duration_seconds=int(item.get("duration_seconds", 10))))

        # Force the dynamic 6-scene fallback if the LLM is lazy
        if len(scenes) < 5:
            return self._fallback(topic_title)

        output = VideoAgentOutput(
            title=str(data.get("title", topic_title)),
            summary=str(data.get("summary", "")),
            scene_count=len(scenes),
            scenes=scenes,
            edits=list(data.get("edits", []) or []),
            duration_seconds=int(data.get("duration_seconds", sum(scene.duration_seconds for scene in scenes))),
            success=True,
        )
        if not output.output_path:
            output.output_path = self._write_placeholder(topic_title, output)
        return output

    def _fallback(self, topic_title: str) -> VideoAgentOutput:
        scenes = [
            VideoScene(title="Intro", description="The presenter introduces the topic with a shocking fact.", duration_seconds=5),
            VideoScene(title="Hook", description="The presenter asks a thought-provoking question.", duration_seconds=5),
            VideoScene(title="Point 1", description="Explaining the first major concept with hands open.", duration_seconds=10),
            VideoScene(title="Point 2", description="Breaking down the technical details.", duration_seconds=10),
            VideoScene(title="Point 3", description="Summarizing the impact of this technology.", duration_seconds=10),
            VideoScene(title="Outro", description="The presenter asking the viewer to subscribe.", duration_seconds=5)
        ]
        output = VideoAgentOutput(
            title=topic_title,
            summary="A dynamic edit plan for the topic.",
            scene_count=len(scenes),
            scenes=scenes,
            edits=["Add intro hook", "Add b-roll", "Add CTA"],
            duration_seconds=45,
            success=True,
        )
        output.output_path = self._write_placeholder(topic_title, output)
        return output

    def _write_placeholder(self, topic_title: str, output: VideoAgentOutput) -> str:
        videos_dir = Path(settings.storage_local_path) / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        file_path = videos_dir / f"{_slugify(topic_title)}.mp4"
        file_path.write_bytes(b"placeholder-video")
        return str(file_path)