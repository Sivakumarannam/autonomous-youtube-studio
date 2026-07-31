from __future__ import annotations

import json
import re
from typing import TypedDict

from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class LongVideoWorkflowState(TypedDict):
    topic_id: str
    topic_title: str
    topic_description: str | None
    channel_id: str
    niche: str
    research_summary: str | None
    key_facts: list[str]
    talking_points: list[str]
    script_content: str | None
    word_count: int
    duration_seconds: int
    seo_title: str | None
    seo_description: str | None
    tags: list[str]
    hashtags: list[str]
    thumbnail_concept: str | None
    error: str | None
    status: str


async def generate_long_script_node(
    state: LongVideoWorkflowState,
    llm: BaseLLMProvider,
) -> LongVideoWorkflowState:
    logger.info("Node: generate_long_script", topic_id=state["topic_id"])
    try:
        from app.agents.long_script_agent.prompts import (
            LONG_SCRIPT_SYSTEM_PROMPT,
            build_long_script_prompt,
        )

        prompt = build_long_script_prompt(
            topic_title=state["topic_title"],
            research_summary=state.get("research_summary"),
            key_facts=state.get("key_facts", []),
            talking_points=state.get("talking_points", []),
            niche=state["niche"],
            language="en",
        )

        response = await llm.generate_text(
            prompt=prompt,
            system=LONG_SCRIPT_SYSTEM_PROMPT,
            temperature=0.75,
            max_tokens=8192,
        )

        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        data = json.loads(match.group(0)) if match else {"full_script": response}

        full_script = data.get("full_script", response)
        word_count = len(full_script.split())

        return {
            **state,
            "script_content": full_script,
            "word_count": data.get("word_count", word_count),
            "duration_seconds": data.get("estimated_duration_seconds", int(word_count / 2.2)),
            "seo_title": data.get("seo_title"),
            "seo_description": data.get("seo_description"),
            "tags": data.get("tags", []),
            "hashtags": data.get("hashtags", []),
            "thumbnail_concept": data.get("thumbnail_concept"),
            "status": "complete",
        }
    except Exception as e:
        return {**state, "error": str(e), "status": "failed"}


class LongVideoWorkflow:
    """LangGraph-style long video script workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        topic_id: str,
        topic_title: str,
        channel_id: str,
        niche: str = "technology",
        topic_description: str | None = None,
        research_summary: str | None = None,
        key_facts: list[str] | None = None,
        talking_points: list[str] | None = None,
    ) -> LongVideoWorkflowState:
        state: LongVideoWorkflowState = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "topic_description": topic_description,
            "channel_id": channel_id,
            "niche": niche,
            "research_summary": research_summary,
            "key_facts": key_facts or [],
            "talking_points": talking_points or [],
            "script_content": None,
            "word_count": 0,
            "duration_seconds": 480,
            "seo_title": None,
            "seo_description": None,
            "tags": [],
            "hashtags": [],
            "thumbnail_concept": None,
            "error": None,
            "status": "running",
        }

        state = await generate_long_script_node(state, self._llm)

        logger.info("LongVideoWorkflow complete", topic_id=topic_id, status=state["status"])
        return state