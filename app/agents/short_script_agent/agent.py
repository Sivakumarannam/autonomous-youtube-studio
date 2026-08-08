import json
import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.short_script_agent.models import ShortScriptAgentOutput
from app.agents.short_script_agent.prompts import (
    SHORT_SCRIPT_SYSTEM_PROMPT,
    build_short_script_prompt,
)
from app.agents.short_script_agent.hook_utils import strengthen_hook, EXTRA_LEAK_PATTERNS
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.research import Research
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.topic import Topic
from app.database.repositories.script_repository import ScriptRepository
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


_INSTRUCTION_LEAK_PATTERNS: list[str] = [
    r"opening \d",
    r"first \d[-–]\d seconds",
    r"main content explaining",
    r"the closing call to action",
    r"the key point",
    r"\(first \d",
    r"seconds\)",
    r"section\s*[:,]",
    r"purpose\s*[:,]",
    r"duration\s*[:,]",
    r"grab attention immediately",
    r"briefly explain what",
    r"wrap up with",
    r"deliver the key value",
    *EXTRA_LEAK_PATTERNS,
]
_LEAK_PATTERN = re.compile("|".join(_INSTRUCTION_LEAK_PATTERNS), re.IGNORECASE)


def _strip_instruction_leaks(text: str) -> str:
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not _LEAK_PATTERN.search(s)]
    if not kept:
        return text.strip()
    result = " ".join(kept).strip()
    return re.sub(r"  +", " ", result)


class ShortScriptAgent:
    AGENT_NAME = "ShortScriptAgent"
    TARGET_MIN_WORDS = 65
    TARGET_MAX_WORDS = 75
    WORDS_PER_SECOND = 2.63

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        topic: Topic,
        research: Optional[Research] = None,
        session: Optional[AsyncSession] = None,
        niche: str = "technology",
        rag_context: Optional[str] = None,
    ) -> Script:
        logger.info("ShortScriptAgent starting", topic_id=str(topic.id))
        start = time.monotonic()

        summary, key_facts = self._extract_research(research)

        try:
            raw = await self._generate(
                topic_title=topic.title,
                research_summary=summary,
                key_facts=key_facts,
                niche=niche,
                language=getattr(topic, "language", None) or "en",
                rag_context=rag_context,
            )
            output = self._parse_response(raw, topic.title)
            output = self._apply_script_qa(output)
        except Exception as exc:
            logger.exception("ShortScriptAgent failed", topic_id=str(topic.id))
            raise AgentError(f"ShortScriptAgent failed: {exc}") from exc

        elapsed = time.monotonic() - start
        logger.info(
            "ShortScriptAgent done",
            topic_id=str(topic.id),
            words=output.word_count,
            elapsed_s=round(elapsed, 2),
        )

        file_path = self._save_script_file(str(topic.id), output.full_script)

        script = Script(
            topic_id=topic.id,
            script_type=ScriptType.SHORT,
            status=ScriptStatus.READY,
            title=output.seo_title or topic.title,
            hook=output.hook,
            body=output.full_script,
            cta=output.cta,
            full_text=output.full_script,
            word_count=output.word_count,
            estimated_duration_seconds=output.estimated_duration_seconds,
            seo_title=output.seo_title,
            seo_description=output.seo_description,
            tags=json.dumps(output.tags) if output.tags else None,
            hashtags=json.dumps(output.hashtags) if output.hashtags else None,
            file_path=file_path,
        )

        if session is not None:
            repo = ScriptRepository(session)
            script = await repo.create(script)

        return script

    async def _generate(
        self,
        topic_title: str,
        research_summary: Optional[str],
        key_facts: list[str],
        niche: str,
        language: str,
        rag_context: Optional[str],
    ) -> str:
        user_prompt = build_short_script_prompt(
            topic_title=topic_title,
            research_summary=research_summary,
            key_facts=key_facts,
            niche=niche,
            language=language,
            rag_context=rag_context,
        )
        return await self._llm.generate(
            system_prompt=SHORT_SCRIPT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.75,
            max_tokens=2048,
        )

    def _parse_response(self, raw: str, topic_title: str) -> ShortScriptAgentOutput:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("ShortScriptAgent non-JSON response; wrapping as full_script")
            data = {"full_script": text, "hook": text[:80], "cta": "Subscribe for more!"}

        if not isinstance(data, dict):
            data = {}

        hook = _strip_instruction_leaks(str(data.get("hook", "") or "").strip())
        intro = _strip_instruction_leaks(str(data.get("intro", "") or "").strip())
        main = _strip_instruction_leaks(str(data.get("main", "") or "").strip())
        outro = _strip_instruction_leaks(str(data.get("outro", "") or "").strip())
        cta = self._sanitize_cta(str(data.get("cta", "Subscribe for more!") or "").strip())
        full_script = _strip_instruction_leaks(str(data.get("full_script", "") or "").strip())

        if not full_script:
            parts = [p for p in (hook, intro, main, outro, cta) if p]
            full_script = " ".join(parts)

        # Strengthen weak hooks
        try:
            hook = strengthen_hook(hook) or hook
        except Exception:
            pass

        seo_title = str(data.get("seo_title") or topic_title or "").strip()
        seo_description = str(data.get("seo_description") or "").strip()
        tags = data.get("tags") or []
        hashtags = data.get("hashtags") or []
        if not isinstance(tags, list):
            tags = []
        if not isinstance(hashtags, list):
            hashtags = []
        tags = [str(t).strip() for t in tags if str(t).strip()][:28]
        hashtags = [str(h).strip() for h in hashtags if str(h).strip()]
        if not any(h.lower() == "#shorts" for h in hashtags):
            hashtags = ["#Shorts"] + hashtags
        hashtags = hashtags[:12]

        # Align cta at end of full_script
        if cta and cta not in full_script:
            full_script = (full_script + " " + cta).strip()

        word_count = len(full_script.split())
        duration = round(word_count / self.WORDS_PER_SECOND, 1)

        seo_description = self._enrich_description(seo_description or full_script[:140], hashtags, cta)

        return ShortScriptAgentOutput(
            hook=hook,
            intro=intro,
            main=main,
            outro=outro,
            cta=cta,
            full_script=full_script,
            word_count=word_count,
            estimated_duration_seconds=duration,
            seo_title=seo_title,
            seo_description=seo_description,
            tags=tags,
            hashtags=hashtags,
        )

    def _apply_script_qa(self, output: ShortScriptAgentOutput) -> ShortScriptAgentOutput:
        promised = self._extract_promised_count(output.hook, output.seo_title)
        items = self._count_main_items(output.main)
        if promised and items and promised != items:
            logger.info(
                "count_qa_rewrite",
                promised=promised,
                items=items,
                title_before=output.seo_title,
            )
            output.seo_title = self._rewrite_count_in_title(output.seo_title, items)
            output.hook = self._rewrite_count_in_title(output.hook, items)
            # soft-align opening of full_script
            output.full_script = self._rewrite_count_in_title(output.full_script, items)
        return output

    @staticmethod
    def _extract_promised_count(hook: str, seo_title: str) -> int | None:
        """Find the count promised in hook/title (any niche)."""
        blob = f"{hook or ''} {seo_title or ''}"
        matches = re.findall(
            r"\b([2-9]|1[0-2])\s+(?:phones?|apps?|tips?|hacks?|tricks?|ways?|tools?|ideas?|facts?|steps?|secrets?|reasons?|things?|features?|upgrades?|builds?|pcs?|laptops?|cars?|gadgets?|devices?|options?|picks?|methods?|habits?|rules?|mistakes?|fixes?|changes?|game\s*changers?|trends?)\b",
            blob,
            flags=re.I,
        )
        if matches:
            try:
                return int(matches[0])
            except ValueError:
                pass
        m = re.search(r"\b([2-9])\b", (seo_title or "")[:60])
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _count_main_items(main: str) -> int:
        if not main:
            return 0
        ordinals = re.findall(
            r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\b",
            main,
            flags=re.I,
        )
        if ordinals:
            return len({o.lower() for o in ordinals})
        soft = re.findall(r"(?:^|[\s.])(?:number\s+)?([1-9]|10)[.):]\s", main, flags=re.I)
        if soft:
            return len(soft) + 1
        return 0

    @staticmethod
    def _rewrite_count_in_title(text: str, new_count: int) -> str:
        if not text or new_count < 1:
            return text
        return re.sub(r"\b([2-9])\b", str(new_count), text, count=1)

    @staticmethod
    def _sanitize_cta(cta: str) -> str:
        """Keep end-card / spoken CTA short; prefer Subscribe for YouTube."""
        c = (cta or "").strip()
        if not c:
            return "Subscribe for more"
        low = c.lower()
        if any(x in low for x in ("shocked you", "which change", "change shocked")):
            return "Subscribe for more"
        # YouTube growth: Follow → Subscribe
        c = re.sub(r"\bfollow\b", "Subscribe", c, flags=re.I)
        if len(c) > 60:
            c = c[:57].rstrip() + "..."
        return c

    def _enrich_description(
        self,
        description: str,
        hashtags: list[str],
        cta: str,
    ) -> str:
        desc = description.strip()

        existing_inline = set(re.findall(r"#\w+", desc))
        missing = [h for h in hashtags if h not in existing_inline]
        needed = max(0, 7 - len(existing_inline))
        if needed > 0 and missing:
            desc = desc.rstrip() + " " + " ".join(missing[:needed])

        cta_lower = cta.lower()
        desc_lower = desc.lower()
        if (
            cta
            and cta_lower not in desc_lower
            and "subscribe" not in desc_lower
            and "follow" not in desc_lower
        ):
            desc = desc.rstrip() + " " + cta.strip()

        if len(desc) < 100 and cta and cta not in desc:
            desc = desc.rstrip() + " " + cta.strip()

        return desc

    def _extract_research(self, research: Optional[Research]) -> tuple[Optional[str], list[str]]:
        if not research:
            return None, []
        summary = research.summary
        key_facts: list[str] = []
        if research.key_facts:
            try:
                key_facts = json.loads(research.key_facts)
            except json.JSONDecodeError:
                key_facts = []
        return summary, key_facts

    def _save_script_file(self, topic_id: str, content: str) -> str:
        scripts_dir = Path(settings.storage_local_path) / "scripts" / "short"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        file_path = scripts_dir / f"{topic_id}_short.txt"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
