from __future__ import annotations

import json
import re
from typing import TypedDict

from app.agents.seo_agent.models import SEOAgentOutput
from app.agents.seo_agent.prompts import build_seo_prompt, build_seo_system_prompt
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class SEOWorkflowState(TypedDict):
    script_id: str
    topic_title: str
    script_content: str
    script_type: str
    niche: str
    language: str
    # outputs
    seo_title: str | None
    seo_description: str | None
    tags: list[str]
    hashtags: list[str]
    primary_keyword: str
    secondary_keywords: list[str]
    title_score: float
    description_score: float
    tags_score: float
    overall_seo_score: float
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def generate_seo_node(
    state: SEOWorkflowState,
    llm: BaseLLMProvider,
) -> SEOWorkflowState:
    logger.info("Node: generate_seo", script_id=state["script_id"])
    try:
        from app.agents.seo_agent.agent import SEOAgent

        agent = SEOAgent(llm_provider=llm)
        output = await agent.run_for_content(
            topic_title=state["topic_title"],
            script_content=state["script_content"],
            script_type=state["script_type"],
            niche=state["niche"],
            language=state["language"],
        )
        return {
            **state,
            "seo_title": output.title,
            "seo_description": output.description,
            "tags": output.tags,
            "hashtags": output.hashtags,
            "primary_keyword": output.primary_keyword,
            "secondary_keywords": output.secondary_keywords,
            "title_score": output.title_score,
            "description_score": output.description_score,
            "tags_score": output.tags_score,
            "overall_seo_score": output.overall_seo_score,
            "status": "complete",
        }
    except Exception as exc:
        return {**state, "error": str(exc), "status": "failed"}


class SEOWorkflow:
    """LangGraph-style SEO metadata generation workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script_id: str,
        topic_title: str,
        script_content: str,
        script_type: str = "long",
        niche: str = "technology",
        language: str = "en",
    ) -> SEOWorkflowState:
        state: SEOWorkflowState = {
            "script_id": script_id,
            "topic_title": topic_title,
            "script_content": script_content,
            "script_type": script_type,
            "niche": niche,
            "language": language,
            "seo_title": None,
            "seo_description": None,
            "tags": [],
            "hashtags": [],
            "primary_keyword": "",
            "secondary_keywords": [],
            "title_score": 0.0,
            "description_score": 0.0,
            "tags_score": 0.0,
            "overall_seo_score": 0.0,
            "error": None,
            "status": "running",
        }

        state = await generate_seo_node(state, self._llm)

        logger.info(
            "SEOWorkflow complete",
            script_id=script_id,
            status=state["status"],
            score=state["overall_seo_score"],
        )
        return state
