from __future__ import annotations

from typing import TypedDict

from app.agents.analytics_agent.agent import AnalyticsAgent
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class AnalyticsWorkflowState(TypedDict):
    topic_title: str
    views: int
    likes: int
    comments: int
    status: str
    summary: str
    recommendations: list[str]
    error: str | None


class AnalyticsWorkflow:
    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(self, topic_title: str, views: int = 0, likes: int = 0, comments: int = 0, niche: str = "technology") -> AnalyticsWorkflowState:
        try:
            agent = AnalyticsAgent(llm_provider=self._llm)
            output = await agent.generate_report(topic_title=topic_title, views=views, likes=likes, comments=comments, niche=niche)
            return {"topic_title": topic_title, "views": views, "likes": likes, "comments": comments, "status": "complete", "summary": output.summary, "recommendations": output.recommendations, "error": None}
        except Exception as exc:
            logger.error("Analytics workflow failed", error=str(exc))
            return {"topic_title": topic_title, "views": views, "likes": likes, "comments": comments, "status": "failed", "summary": "", "recommendations": [], "error": str(exc)}
