from __future__ import annotations

from typing import TypedDict

from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ModerationWorkflowState(TypedDict):
    script_id: str
    script_content: str
    script_type: str
    topic_title: str
    niche: str
    seo_title: str
    seo_description: str
    tags: list[str]
    # outputs
    approved: bool
    copyright_risk: bool
    duplicate_content: bool
    spam_risk: bool
    policy_violation: bool
    monetization_unsafe: bool
    copyright_risk_score: float
    duplicate_risk_score: float
    spam_risk_score: float
    policy_risk_score: float
    monetization_risk_score: float
    overall_risk_score: float
    rejection_reasons: list[str]
    recommendations: list[str]
    reviewer_notes: str
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def run_moderation_node(
    state: ModerationWorkflowState,
    llm: BaseLLMProvider,
) -> ModerationWorkflowState:
    logger.info("Node: run_moderation", script_id=state["script_id"])
    try:
        from app.agents.moderation_agent.agent import ModerationAgent

        agent = ModerationAgent(llm_provider=llm)
        output = await agent.moderate_content(
            script_content=state["script_content"],
            script_type=state["script_type"],
            topic_title=state["topic_title"],
            niche=state["niche"],
            seo_title=state["seo_title"],
            seo_description=state["seo_description"],
            tags=state["tags"],
        )
        return {
            **state,
            "approved": output.approved,
            "copyright_risk": output.flags.copyright_risk,
            "duplicate_content": output.flags.duplicate_content,
            "spam_risk": output.flags.spam_risk,
            "policy_violation": output.flags.policy_violation,
            "monetization_unsafe": output.flags.monetization_unsafe,
            "copyright_risk_score": output.risk_scores.copyright_risk_score,
            "duplicate_risk_score": output.risk_scores.duplicate_risk_score,
            "spam_risk_score": output.risk_scores.spam_risk_score,
            "policy_risk_score": output.risk_scores.policy_risk_score,
            "monetization_risk_score": output.risk_scores.monetization_risk_score,
            "overall_risk_score": output.overall_risk_score,
            "rejection_reasons": output.rejection_reasons,
            "recommendations": output.recommendations,
            "reviewer_notes": output.reviewer_notes,
            "status": "complete",
        }
    except Exception as exc:
        return {**state, "error": str(exc), "status": "failed"}


class ModerationWorkflow:
    """LangGraph-style content moderation workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script_id: str,
        script_content: str,
        script_type: str = "long",
        topic_title: str = "",
        niche: str = "technology",
        seo_title: str = "",
        seo_description: str = "",
        tags: list[str] | None = None,
    ) -> ModerationWorkflowState:
        state: ModerationWorkflowState = {
            "script_id": script_id,
            "script_content": script_content,
            "script_type": script_type,
            "topic_title": topic_title,
            "niche": niche,
            "seo_title": seo_title,
            "seo_description": seo_description,
            "tags": tags or [],
            "approved": False,
            "copyright_risk": False,
            "duplicate_content": False,
            "spam_risk": False,
            "policy_violation": False,
            "monetization_unsafe": False,
            "copyright_risk_score": 0.0,
            "duplicate_risk_score": 0.0,
            "spam_risk_score": 0.0,
            "policy_risk_score": 0.0,
            "monetization_risk_score": 0.0,
            "overall_risk_score": 0.0,
            "rejection_reasons": [],
            "recommendations": [],
            "reviewer_notes": "",
            "error": None,
            "status": "running",
        }

        state = await run_moderation_node(state, self._llm)

        logger.info(
            "ModerationWorkflow complete",
            script_id=script_id,
            status=state["status"],
            approved=state["approved"],
            risk=state["overall_risk_score"],
        )
        return state