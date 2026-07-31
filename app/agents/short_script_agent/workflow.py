from __future__ import annotations

from typing import TypedDict

from app.agents.short_script_agent.agent import ShortScriptAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ShortsWorkflowState(TypedDict):
    topic_id: str
    topic_title: str
    topic_description: str | None
    channel_id: str
    niche: str
    research_summary: str | None
    key_facts: list[str]
    script_content: str | None
    word_count: int
    duration_seconds: int
    seo_title: str | None
    seo_description: str | None
    tags: list[str]
    hashtags: list[str]
    error: str | None
    status: str


async def generate_short_script_node(
    state: ShortsWorkflowState,
    llm: BaseLLMProvider,
) -> ShortsWorkflowState:
    logger.info("Node: generate_short_script", topic_id=state["topic_id"])
    try:
        from app.agents.short_script_agent.prompts import (
            SHORT_SCRIPT_SYSTEM_PROMPT,
            build_short_script_prompt,
        )
        import json, re

        prompt = build_short_script_prompt(
            topic_title=state["topic_title"],
            research_summary=state.get("research_summary"),
            key_facts=state.get("key_facts", []),
            niche=state["niche"],
            language="en",
        )

        response = await llm.generate_text(
            prompt=prompt,
            system=SHORT_SCRIPT_SYSTEM_PROMPT,
            temperature=0.85,
            max_tokens=2048,
        )

        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = {"full_script": response, "word_count": len(response.split())}

        full_script = data.get("full_script", response)
        return {
            **state,
            "script_content": full_script,
            "word_count": data.get("word_count", len(full_script.split())),
            "duration_seconds": data.get("estimated_duration_seconds", 30),
            "seo_title": data.get("seo_title"),
            "seo_description": data.get("seo_description"),
            "tags": data.get("tags", []),
            "hashtags": data.get("hashtags", ["#Shorts"]),
            "status": "complete",
        }
    except Exception as e:
        return {**state, "error": str(e), "status": "failed"}


class ShortsWorkflow:
    """LangGraph-style Shorts generation workflow."""

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
    ) -> ShortsWorkflowState:
        state: ShortsWorkflowState = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "topic_description": topic_description,
            "channel_id": channel_id,
            "niche": niche,
            "research_summary": research_summary,
            "key_facts": key_facts or [],
            "script_content": None,
            "word_count": 0,
            "duration_seconds": 30,
            "seo_title": None,
            "seo_description": None,
            "tags": [],
            "hashtags": [],
            "error": None,
            "status": "running",
        }

        state = await generate_short_script_node(state, self._llm)

        logger.info("ShortsWorkflow complete", topic_id=topic_id, status=state["status"])
        return state