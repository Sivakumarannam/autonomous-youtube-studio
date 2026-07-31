import json
import re
import time
from typing import Any, Optional
from uuid import UUID

from app.agents.topic_agent.models import GeneratedTopic, TopicAgentInput, TopicAgentOutput
from app.agents.topic_agent.prompts import (
    TOPIC_SYSTEM_PROMPT,
    build_topic_generation_prompt,
)
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider
from app.database.models.topic import TopicSource

logger = get_logger(__name__)


class TopicAgent:
    """
    Topic Discovery Agent.

    Finds trending topics from multiple sources and scores them
    for YouTube performance potential.
    """

    AGENT_NAME = "TopicAgent"

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        channel_id: UUID,
        count: int = 5,
        sources: Optional[list] = None,
        content_type: str = "long",
        niche: str = "technology",
        language: str = "en",
    ) -> list[dict]:
        """
        Run the Topic Agent.

        Returns a list of raw topic dicts ready to be saved to the database.
        """
        sources = sources or [TopicSource.GOOGLE_TRENDS, TopicSource.YOUTUBE_TRENDS]
        source_strings = [s.value if hasattr(s, "value") else str(s) for s in sources]

        logger.info(
            "TopicAgent starting",
            channel_id=str(channel_id),
            count=count,
            sources=source_strings,
        )

        start = time.monotonic()

        try:
            raw_topics = await self._generate_topics(
                niche=niche,
                count=count,
                language=language,
                content_type=content_type,
                sources=source_strings,
            )
        except Exception as e:
            logger.error("TopicAgent failed", error=str(e))
            raise AgentError(self.AGENT_NAME, str(e)) from e

        elapsed = time.monotonic() - start
        logger.info(
            "TopicAgent complete",
            topics_generated=len(raw_topics),
            elapsed_seconds=round(elapsed, 2),
        )

        return raw_topics

    async def _generate_topics(
        self,
        niche: str,
        count: int,
        language: str,
        content_type: str,
        sources: list[str],
    ) -> list[dict]:
        prompt = build_topic_generation_prompt(
            niche=niche,
            count=count,
            language=language,
            content_type=content_type,
            sources=sources,
        )

        response = await self._llm.generate_text(
            prompt=prompt,
            system=TOPIC_SYSTEM_PROMPT,
            temperature=0.8,
            max_tokens=4096,
        )

        return self._parse_topics(response, count, niche=niche)

    def _parse_topics(self, raw: str, expected_count: int, niche: str = "general") -> list[dict]:
        """Parse LLM JSON response into a list of topic dicts."""

        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = cleaned.replace("```", "").strip()

        # If response is already JSON, leave it alone.
        # Otherwise try to extract JSON from surrounding text.
        if not (cleaned.startswith("{") or cleaned.startswith("[")):
            array_match = re.search(r"\[[\s\S]*\]", cleaned)
            object_match = re.search(r"\{[\s\S]*\}", cleaned)

            if array_match:
                cleaned = array_match.group(0)
            elif object_match:
                cleaned = object_match.group(0)

        try:
            data = json.loads(cleaned)

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse topic JSON",
                error=str(e),
                raw=raw[:500],
            )

            # Return niche-aware fallback topic instead of breaking pipeline
            niche_label = niche.replace("-", " ").replace("_", " ").title()
            return [
                {
                    "topic": f"Amazing {niche_label} Facts You Need to Know",
                    "score": 70.0,
                    "reason": "Fallback topic due to parse error",
                    "keywords": [niche.lower(), "facts", "tips"],
                    "content_type": "long",
                }
            ]

        # Handle single object
        if not isinstance(data, list):
            data = [data]

        validated: list[dict] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            topic_title = str(item.get("topic", "")).strip()

            if not topic_title:
                continue

            validated.append(
                {
                    "topic": topic_title,
                    "score": float(item.get("score", 70.0)),
                    "reason": str(item.get("reason", "")),
                    "keywords": item.get("keywords", []),
                    "content_type": item.get("content_type", "long"),
                }
            )

        return validated[:expected_count]