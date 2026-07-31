import json
import re
import time
from typing import Optional

from app.agents.seo_agent.models import SEOAgentInput, SEOAgentOutput
from app.agents.seo_agent.prompts import SEO_SYSTEM_PROMPT, build_seo_prompt
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class SEOAgent:
    """
    SEO Agent.

    Generates YouTube-optimised title, description, tags, and hashtags
    for a given script. Also scores each element 0-100.
    """

    AGENT_NAME = "SEOAgent"

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script: Script,
        topic_title: str,
        niche: str = "technology",
        language: str = "en",
    ) -> SEOAgentOutput:
        """
        Generate SEO metadata for a script.

        Returns an SEOAgentOutput with title, description, tags, hashtags,
        keywords, and quality scores.
        """
        logger.info(
            "SEOAgent starting",
            script_id=str(script.id),
            script_type=script.script_type,
        )
        start = time.monotonic()

        try:
            output = await self._generate(
                topic_title=topic_title,
                script_content=script.content,
                script_type=str(script.script_type),
                niche=niche,
                language=language,
            )
        except Exception as exc:
            logger.error("SEOAgent failed", script_id=str(script.id), error=str(exc))
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

        elapsed = time.monotonic() - start
        logger.info(
            "SEOAgent complete",
            script_id=str(script.id),
            seo_score=output.overall_seo_score,
            elapsed=round(elapsed, 2),
        )
        return output

    async def run_for_content(
        self,
        topic_title: str,
        script_content: str,
        script_type: str = "long",
        niche: str = "technology",
        language: str = "en",
    ) -> SEOAgentOutput:
        """Run without a Script ORM object — useful in workflows."""
        try:
            return await self._generate(
                topic_title=topic_title,
                script_content=script_content,
                script_type=script_type,
                niche=niche,
                language=language,
            )
        except Exception as exc:
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    async def _generate(
        self,
        topic_title: str,
        script_content: str,
        script_type: str,
        niche: str,
        language: str,
    ) -> SEOAgentOutput:
        prompt = build_seo_prompt(
            topic_title=topic_title,
            script_excerpt=script_content,
            script_type=script_type,
            niche=niche,
            language=language,
        )
        response = await self._llm.generate_text(
            prompt=prompt,
            system=SEO_SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=2048,
        )
        return self._parse(response, topic_title, niche=niche)

    def _parse(self, raw: str, topic_title: str, niche: str = "general") -> SEOAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("SEOAgent JSON parse failed — using fallback", raw=raw[:300])
            return self._fallback(topic_title, niche=niche)

        title = str(data.get("title", topic_title[:70]))
        description = str(data.get("description", topic_title))
        tags = [str(t) for t in data.get("tags", [])]
        hashtags = [str(h) for h in data.get("hashtags", [])]
        secondary_keywords = [str(k) for k in data.get("secondary_keywords", [])]

        def _score(key: str) -> float:
            raw_val = data.get(key, 0.0)
            try:
                return max(0.0, min(100.0, float(raw_val)))
            except (TypeError, ValueError):
                return 0.0

        return SEOAgentOutput(
            title=title,
            description=description,
            tags=tags,
            hashtags=hashtags,
            primary_keyword=str(data.get("primary_keyword", "")),
            secondary_keywords=secondary_keywords,
            title_score=_score("title_score"),
            description_score=_score("description_score"),
            tags_score=_score("tags_score"),
            overall_seo_score=_score("overall_seo_score"),
        )

    def _fallback(self, topic_title: str, niche: str = "general") -> SEOAgentOutput:
        short_title = topic_title[:70]
        # Derive niche-aware hashtags from the niche and topic words
        niche_tag = "#" + niche.replace("-", "").replace("_", "").replace(" ", "").title()
        topic_words = [
            "#" + w.capitalize()
            for w in topic_title.split()
            if len(w) > 3 and w.isalpha()
        ][:2]
        hashtags = [niche_tag, "#Shorts", "#LearnOnYouTube"] + topic_words
        niche_label = niche.replace("-", " ").replace("_", " ")
        return SEOAgentOutput(
            title=short_title,
            description=(
                f"{topic_title} — everything you need to know about {niche_label}. "
                "Watch until the end and follow for more!"
            ),
            tags=[
                topic_title.lower(),
                niche_label.lower(),
                "tutorial",
                "guide",
                "how to",
                "tips",
            ],
            hashtags=hashtags,
            primary_keyword=topic_title.lower(),
            secondary_keywords=[niche_label.lower(), "tutorial", "guide"],
            title_score=60.0,
            description_score=60.0,
            tags_score=60.0,
            overall_seo_score=60.0,
        )