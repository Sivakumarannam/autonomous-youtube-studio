import json
import re
import time
from typing import Optional

from app.agents.moderation_agent.models import (
    ModerationAgentOutput,
    ModerationFlags,
    ModerationRisk,
)
from app.agents.moderation_agent.prompts import (
    MODERATION_SYSTEM_PROMPT,
    build_moderation_prompt,
)
from app.core.exceptions import AgentError, ModerationError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ModerationAgent:
    """
    Content Moderation Agent.

    Checks scripts for copyright risk, duplicate content, spam,
    policy violations, and monetization safety before upload.

    Raises ModerationError if the content fails and raise_on_failure=True.
    """

    AGENT_NAME = "ModerationAgent"
    RISK_THRESHOLD = 70.0

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script: Script,
        topic_title: str = "",
        niche: str = "technology",
        seo_title: str = "",
        seo_description: str = "",
        tags: Optional[list[str]] = None,
        raise_on_failure: bool = False,
    ) -> ModerationAgentOutput:
        """Moderate a Script ORM object."""
        logger.info("ModerationAgent starting", script_id=str(script.id))
        start = time.monotonic()

        # Resolve SEO fields from the script if not explicitly provided
        resolved_title = seo_title or script.seo_title or topic_title
        resolved_desc = seo_description or script.seo_description or ""
        resolved_tags: list[str] = tags or []
        if not resolved_tags and script.seo_tags:
            try:
                resolved_tags = json.loads(script.seo_tags)
            except (json.JSONDecodeError, TypeError):
                resolved_tags = []

        try:
            output = await self._moderate(
                script_content=script.content,
                script_type=str(script.script_type),
                topic_title=topic_title or "",
                niche=niche,
                seo_title=resolved_title,
                seo_description=resolved_desc,
                tags=resolved_tags,
            )
        except AgentError:
            raise
        except Exception as exc:
            logger.error("ModerationAgent failed", script_id=str(script.id), error=str(exc))
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

        elapsed = time.monotonic() - start
        logger.info(
            "ModerationAgent complete",
            script_id=str(script.id),
            approved=output.approved,
            risk=output.overall_risk_score,
            elapsed=round(elapsed, 2),
        )

        if raise_on_failure and not output.approved:
            reasons = "; ".join(output.rejection_reasons) or "content failed moderation"
            raise ModerationError(reasons)

        return output

    async def moderate_content(
        self,
        script_content: str,
        script_type: str = "long",
        topic_title: str = "",
        niche: str = "technology",
        seo_title: str = "",
        seo_description: str = "",
        tags: Optional[list[str]] = None,
    ) -> ModerationAgentOutput:
        """Moderate raw content without a Script ORM object."""
        try:
            return await self._moderate(
                script_content=script_content,
                script_type=script_type,
                topic_title=topic_title,
                niche=niche,
                seo_title=seo_title,
                seo_description=seo_description,
                tags=tags or [],
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    async def _moderate(
        self,
        script_content: str,
        script_type: str,
        topic_title: str,
        niche: str,
        seo_title: str,
        seo_description: str,
        tags: list[str],
    ) -> ModerationAgentOutput:
        prompt = build_moderation_prompt(
            script_content=script_content,
            script_type=script_type,
            topic_title=topic_title,
            niche=niche,
            seo_title=seo_title,
            seo_description=seo_description,
            tags=tags,
        )
        response = await self._llm.generate_text(
            prompt=prompt,
            system=MODERATION_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2048,
        )
        return self._parse(response)

    def _parse(self, raw: str) -> ModerationAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("ModerationAgent JSON parse failed — approving with caution")
            return self._safe_fallback()

        def _risk(key: str) -> float:
            try:
                return max(0.0, min(100.0, float(data.get(key, 0.0))))
            except (TypeError, ValueError):
                return 0.0

        risk = ModerationRisk(
            copyright_risk_score=_risk("copyright_risk_score"),
            duplicate_risk_score=_risk("duplicate_risk_score"),
            spam_risk_score=_risk("spam_risk_score"),
            policy_risk_score=_risk("policy_risk_score"),
            monetization_risk_score=_risk("monetization_risk_score"),
        )

        flags = ModerationFlags(
            copyright_risk=bool(data.get("copyright_risk", risk.copyright_risk_score >= self.RISK_THRESHOLD)),
            duplicate_content=bool(data.get("duplicate_content", risk.duplicate_risk_score >= self.RISK_THRESHOLD)),
            spam_risk=bool(data.get("spam_risk", risk.spam_risk_score >= self.RISK_THRESHOLD)),
            policy_violation=bool(data.get("policy_violation", risk.policy_risk_score >= self.RISK_THRESHOLD)),
            monetization_unsafe=bool(data.get("monetization_unsafe", risk.monetization_risk_score >= self.RISK_THRESHOLD)),
        )

        overall_risk = _risk("overall_risk_score") or risk.overall_risk()
        approved = bool(data.get("approved", not flags.any_flagged()))

        rejection_reasons = data.get("rejection_reasons", [])
        if not isinstance(rejection_reasons, list):
            rejection_reasons = []
        if not approved and not rejection_reasons and flags.any_flagged():
            rejection_reasons = [f"Flagged for: {', '.join(flags.flagged_list())}"]

        recommendations = data.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = []

        return ModerationAgentOutput(
            approved=approved,
            flags=flags,
            risk_scores=risk,
            overall_risk_score=overall_risk,
            rejection_reasons=[str(r) for r in rejection_reasons],
            recommendations=[str(r) for r in recommendations],
            reviewer_notes=str(data.get("reviewer_notes", "")),
        )

    def _safe_fallback(self) -> ModerationAgentOutput:
        """Fallback when JSON parse fails — reject conservatively (safe direction)."""
        return ModerationAgentOutput(
            approved=False,
            flags=ModerationFlags(),
            risk_scores=ModerationRisk(),
            overall_risk_score=50.0,
            rejection_reasons=["Automated moderation check inconclusive — manual review required."],
            recommendations=["Review content manually before publishing."],
            reviewer_notes="Moderation parse failed; content rejected pending human review.",
        )