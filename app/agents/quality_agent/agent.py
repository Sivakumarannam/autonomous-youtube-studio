import json
import re
import time
from typing import Optional

from app.agents.quality_agent.models import (
    QualityAgentOutput,
    QualityScores,
)
from app.agents.quality_agent.prompts import (
    QUALITY_SYSTEM_PROMPT,
    build_quality_prompt,
)
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class QualityAgent:
    """
    Quality Control Agent.

    Evaluates a script across seven dimensions:
    grammar, fact consistency, engagement, retention,
    SEO alignment, uniqueness, and readability.

    Rejects content below the configured minimum threshold.
    """

    AGENT_NAME = "QualityAgent"

    def __init__(self, llm_provider: BaseLLMProvider, script_type: str = "long") -> None:
        self._llm = llm_provider
        # Short scripts (≤90 seconds, often < 100 words) naturally score lower
        # because there is less content for the LLM to evaluate.  Use a separate,
        # lower threshold so good short scripts aren't incorrectly rejected.
        if script_type == "short":
            self._min_score = settings.quality_min_score_short
        else:
            self._min_score = settings.quality_min_score

    async def run(
        self,
        script: Script,
        topic_title: str = "",
        niche: str = "technology",
    ) -> QualityAgentOutput:
        """Evaluate a Script ORM object."""
        logger.info("QualityAgent starting", script_id=str(script.id))
        start = time.monotonic()

        try:
            output = await self._evaluate(
                script_content=script.content,
                script_type=str(script.script_type),
                topic_title=topic_title or "",
                niche=niche,
                word_count=script.word_count,
            )
        except Exception as exc:
            logger.error("QualityAgent failed", script_id=str(script.id), error=str(exc))
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

        elapsed = time.monotonic() - start
        logger.info(
            "QualityAgent complete",
            script_id=str(script.id),
            overall=output.overall_score,
            passed=output.passed,
            elapsed=round(elapsed, 2),
        )
        return output

    async def evaluate_content(
        self,
        script_content: str,
        script_type: str = "long",
        topic_title: str = "",
        niche: str = "technology",
        word_count: int = 0,
    ) -> QualityAgentOutput:
        """Evaluate raw content without a Script ORM object."""
        try:
            return await self._evaluate(
                script_content=script_content,
                script_type=script_type,
                topic_title=topic_title,
                niche=niche,
                word_count=word_count,
            )
        except Exception as exc:
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    async def _evaluate(
        self,
        script_content: str,
        script_type: str,
        topic_title: str,
        niche: str,
        word_count: int,
    ) -> QualityAgentOutput:
        prompt = build_quality_prompt(
            script_content=script_content,
            script_type=script_type,
            topic_title=topic_title,
            niche=niche,
            word_count=word_count,
            min_score=self._min_score,
        )
        response = await self._llm.generate_text(
            prompt=prompt,
            system=QUALITY_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2048,
        )
        return self._parse(response)

    def _parse(self, raw: str) -> QualityAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("QualityAgent JSON parse failed — using fallback")
            return self._fallback()

        def _clamp(key: str, default: float = 0.0) -> float:
            try:
                return max(0.0, min(100.0, float(data.get(key, default))))
            except (TypeError, ValueError):
                return default

        scores = QualityScores(
            grammar_score=_clamp("grammar_score"),
            fact_consistency_score=_clamp("fact_consistency_score"),
            engagement_score=_clamp("engagement_score"),
            retention_score=_clamp("retention_score"),
            seo_score=_clamp("seo_score"),
            uniqueness_score=_clamp("uniqueness_score"),
            readability_score=_clamp("readability_score"),
        )

        overall = _clamp("overall_score") or scores.overall()
        # Numeric threshold is always authoritative — ignore the LLM's own
        # "passed" field which can be calibrated against a different threshold.
        passed = overall >= self._min_score
        logger.info(
            "quality_parse_decision",
            overall=overall,
            min_score=self._min_score,
            passed=passed,
        )

        suggestions = data.get("improvement_suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = []

        rejection_reason: Optional[str] = data.get("rejection_reason") or None
        if not passed and not rejection_reason:
            rejection_reason = f"Overall score {overall:.1f} below threshold {self._min_score}"

        return QualityAgentOutput(
            scores=scores,
            overall_score=overall,
            passed=passed,
            feedback=str(data.get("feedback", "")),
            improvement_suggestions=[str(s) for s in suggestions],
            rejection_reason=rejection_reason,
        )

    def _fallback(self) -> QualityAgentOutput:
        scores = QualityScores(
            grammar_score=70.0,
            fact_consistency_score=70.0,
            engagement_score=70.0,
            retention_score=70.0,
            seo_score=70.0,
            uniqueness_score=70.0,
            readability_score=70.0,
        )
        overall = scores.overall()
        passed = overall >= self._min_score
        return QualityAgentOutput(
            scores=scores,
            overall_score=overall,
            passed=passed,
            feedback="Quality evaluation completed with default scores due to parse error.",
            improvement_suggestions=["Review the script manually before publishing."],
            rejection_reason=None if passed else f"Score {overall} below threshold {self._min_score}",
        )