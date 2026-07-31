from __future__ import annotations

import json
from typing import Any, TypedDict
from uuid import UUID

from app.agents.topic_agent.agent import TopicAgent
from app.agents.topic_agent.models import GeneratedTopic
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


# ---------- State ----------

class TopicWorkflowState(TypedDict):
    channel_id: str
    niche: str
    language: str
    count: int
    sources: list[str]
    content_type: str
    raw_topics: list[dict]
    validated_topics: list[dict]
    error: str | None
    status: str  # "running" | "complete" | "failed"


# ---------- Nodes ----------

async def discover_topics_node(state: TopicWorkflowState, llm: BaseLLMProvider) -> TopicWorkflowState:
    logger.info("Node: discover_topics", channel_id=state["channel_id"])
    try:
        agent = TopicAgent(llm_provider=llm)
        raw = await agent.run(
            channel_id=UUID(state["channel_id"]),
            count=state["count"],
            sources=state["sources"],
            content_type=state["content_type"],
            niche=state["niche"],
            language=state["language"],
        )
        return {**state, "raw_topics": raw, "status": "running"}
    except Exception as e:
        return {**state, "error": str(e), "status": "failed"}


async def validate_topics_node(state: TopicWorkflowState) -> TopicWorkflowState:
    logger.info("Node: validate_topics", count=len(state.get("raw_topics", [])))
    if state["status"] == "failed":
        return state

    valid: list[dict] = []
    for item in state.get("raw_topics", []):
        try:
            validated = GeneratedTopic(**item)
            valid.append(validated.model_dump())
        except Exception as e:
            logger.warning("Invalid topic skipped", error=str(e), topic=item)

    return {**state, "validated_topics": valid, "status": "complete" if valid else "failed"}


def should_retry(state: TopicWorkflowState) -> str:
    if state["status"] == "failed":
        return "failed"
    return "complete"


# ---------- Workflow Builder ----------

class TopicDiscoveryWorkflow:
    """
    LangGraph-style topic discovery workflow.
    Executes: discover → validate → done
    """

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        channel_id: str,
        niche: str,
        language: str = "en",
        count: int = 5,
        sources: list[str] | None = None,
        content_type: str = "long",
    ) -> TopicWorkflowState:
        state: TopicWorkflowState = {
            "channel_id": channel_id,
            "niche": niche,
            "language": language,
            "count": count,
            "sources": sources or ["google_trends", "youtube_trends"],
            "content_type": content_type,
            "raw_topics": [],
            "validated_topics": [],
            "error": None,
            "status": "running",
        }

        # Node 1: Discover
        state = await discover_topics_node(state, self._llm)

        # Early exit on failure
        if state["status"] == "failed":
            logger.error("TopicWorkflow failed at discovery", error=state.get("error"))
            return state

        # Node 2: Validate
        state = await validate_topics_node(state)

        logger.info(
            "TopicWorkflow complete",
            validated=len(state["validated_topics"]),
            status=state["status"],
        )
        return state