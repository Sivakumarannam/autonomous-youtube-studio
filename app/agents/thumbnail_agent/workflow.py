from __future__ import annotations

from typing import TypedDict

from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ThumbnailWorkflowState(TypedDict):
    script_id: str
    topic_title: str
    seo_title: str
    script_type: str
    niche: str
    script_excerpt: str
    # outputs
    concept: str | None
    title_text: str | None
    subtitle_text: str | None
    emoji: str | None
    background_color: str | None
    accent_color: str | None
    layout: str | None
    subject: str | None
    style_notes: str | None
    ctr_score: float
    file_path: str | None
    error: str | None
    status: str  # "running" | "complete" | "failed"


async def generate_thumbnail_node(
    state: ThumbnailWorkflowState,
    llm: BaseLLMProvider,
) -> ThumbnailWorkflowState:
    logger.info("Node: generate_thumbnail", script_id=state["script_id"])
    try:
        from app.agents.thumbnail_agent.agent import ThumbnailAgent

        agent = ThumbnailAgent(llm_provider=llm)
        output = await agent.generate_concept(
            topic_title=state["topic_title"],
            seo_title=state["seo_title"],
            script_type=state["script_type"],
            niche=state["niche"],
            script_excerpt=state["script_excerpt"],
        )
        return {
            **state,
            "concept": output.concept,
            "title_text": output.title_text,
            "subtitle_text": output.subtitle_text,
            "emoji": output.emoji,
            "background_color": output.design.background_color,
            "accent_color": output.design.accent_color,
            "layout": output.design.layout,
            "subject": output.design.subject,
            "style_notes": output.design.style_notes,
            "ctr_score": output.ctr_score,
            "file_path": output.file_path,
            "status": "complete",
        }
    except Exception as exc:
        return {**state, "error": str(exc), "status": "failed"}


class ThumbnailWorkflow:
    """LangGraph-style thumbnail generation workflow."""

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script_id: str,
        topic_title: str,
        script_type: str = "long",
        niche: str = "technology",
        seo_title: str = "",
        script_excerpt: str = "",
    ) -> ThumbnailWorkflowState:
        state: ThumbnailWorkflowState = {
            "script_id": script_id,
            "topic_title": topic_title,
            "seo_title": seo_title,
            "script_type": script_type,
            "niche": niche,
            "script_excerpt": script_excerpt,
            "concept": None,
            "title_text": None,
            "subtitle_text": None,
            "emoji": None,
            "background_color": None,
            "accent_color": None,
            "layout": None,
            "subject": None,
            "style_notes": None,
            "ctr_score": 0.0,
            "file_path": None,
            "error": None,
            "status": "running",
        }

        state = await generate_thumbnail_node(state, self._llm)

        logger.info(
            "ThumbnailWorkflow complete",
            script_id=script_id,
            status=state["status"],
            ctr_score=state["ctr_score"],
        )
        return state