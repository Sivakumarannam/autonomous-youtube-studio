from __future__ import annotations

from typing import TypedDict

from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class QualityWorkflowState(TypedDict):
    script_id: str
    script_content: str
    script_type: str
    topic_title: str
    niche: str
    word_count: int
    # outputs
    grammar_score: float
    fact_consistency_score: float
    engagement_score: float
    retention_score: float
    seo_score: float
    uniqueness_score: float
    readability_score: float
    overall_score: float
    passed: bool
    feedback: str
    improvement_suggestions: list[str]
    rejection_reason: str | None
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def evaluate_quality_node(
    state: QualityWorkflowState,
    llm: BaseLLMProvider,
) -> QualityWorkflowState:
    logger.info("Node: evaluate_quality", script_id=state["script_id"])
    try:
        from app.agents.quality_agent.agent import QualityAgent

        agent = QualityAgent(llm_provider=llm)
        output = await agent.evaluate_content(
            script_content=state["script_content"],
            script_type=state["script_type"],
            topic_title=state["topic_title"],
            niche=state["niche"],
            word_count=state["word_count"],
        )
        return {
            **state,
            "grammar_score": output.scores.grammar_score,
            "fact_consistency_score": output.scores.fact_consistency_score,
            "engagement_score": output.scores.engagement_score,
            "retention_score": output.scores.retention_score,
            "seo_score": output.scores.seo_score,
            "uniqueness_score": output.scores.uniqueness_score,
            "readability_score": output.scores.readability_score,
            "overall_score": output.overall_score,
            "passed": output.passed,
            "feedback": output.feedback,
            "improvement_suggestions": output.improvement_suggestions,
            "rejection_reason": output.rejection_reason,
            "status": "complete",
        }
    except Exception as exc:
        return {**state, "error": str(exc), "status": "failed"}


class QualityWorkflow:
    """LangGraph-style quality evaluation workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script_id: str,
        script_content: str,
        script_type: str = "long",
        topic_title: str = "",
        niche: str = "technology",
        word_count: int = 0,
    ) -> QualityWorkflowState:
        state: QualityWorkflowState = {
            "script_id": script_id,
            "script_content": script_content,
            "script_type": script_type,
            "topic_title": topic_title,
            "niche": niche,
            "word_count": word_count,
            "grammar_score": 0.0,
            "fact_consistency_score": 0.0,
            "engagement_score": 0.0,
            "retention_score": 0.0,
            "seo_score": 0.0,
            "uniqueness_score": 0.0,
            "readability_score": 0.0,
            "overall_score": 0.0,
            "passed": False,
            "feedback": "",
            "improvement_suggestions": [],
            "rejection_reason": None,
            "error": None,
            "status": "running",
        }

        state = await evaluate_quality_node(state, self._llm)

        logger.info(
            "QualityWorkflow complete",
            script_id=script_id,
            status=state["status"],
            passed=state["passed"],
            overall=state["overall_score"],
        )
        return state