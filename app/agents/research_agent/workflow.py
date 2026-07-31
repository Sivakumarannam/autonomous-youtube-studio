from __future__ import annotations

import json
from typing import TypedDict

from app.agents.research_agent.agent import ResearchAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ResearchWorkflowState(TypedDict):
    topic_id: str
    topic_title: str
    topic_description: str | None
    niche: str
    language: str
    research_result: dict | None
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def fetch_and_research_node(
    state: ResearchWorkflowState,
    llm: BaseLLMProvider,
) -> ResearchWorkflowState:
    logger.info("Node: fetch_and_research", topic_id=state["topic_id"])
    try:
        from app.database.models.topic import Topic
        import uuid

        # Create a minimal Topic-like object for the agent
        class _FakeTopic:
            def __init__(self, id_: str, title: str, description: str | None) -> None:
                self.id = uuid.UUID(id_)
                self.title = title
                self.description = description

        fake_topic = _FakeTopic(
            id_=state["topic_id"],
            title=state["topic_title"],
            description=state["topic_description"],
        )

        agent = ResearchAgent(llm_provider=llm)
        result = await agent.run(
            topic=fake_topic,  # type: ignore[arg-type]
            niche=state["niche"],
            language=state["language"],
        )
        return {**state, "research_result": result, "status": "complete"}

    except Exception as e:
        return {**state, "error": str(e), "status": "failed"}


class ResearchWorkflow:
    """LangGraph-style research workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        topic_id: str,
        topic_title: str,
        topic_description: str | None = None,
        niche: str = "technology",
        language: str = "en",
    ) -> ResearchWorkflowState:
        state: ResearchWorkflowState = {
            "topic_id": topic_id,
            "topic_title": topic_title,
            "topic_description": topic_description,
            "niche": niche,
            "language": language,
            "research_result": None,
            "error": None,
            "status": "running",
        }

        state = await fetch_and_research_node(state, self._llm)

        logger.info(
            "ResearchWorkflow complete",
            topic_id=topic_id,
            status=state["status"],
        )
        return state