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
                language="en",
                rag_context=rag_context,
            )
        except Exception as e:
            logger.error("ShortScriptAgent failed", error=str(e))
            raise AgentError(self.AGENT_NAME, str(e)) from e

        file_path = self._save_script_file(topic_id=str(topic.id), content=raw.full_script)

        script_record = Script(
            topic_id=topic.id,
            channel_id=topic.channel_id,
            script_type=ScriptType.SHORT,
            content=raw.full_script,
            word_count=raw.word_count,
            estimated_duration=raw.estimated_duration_seconds,
            hook=raw.hook,
            cta=raw.cta,
            seo_title=raw.seo_title,
            seo_description=raw.seo_description,
            seo_tags=json.dumps(raw.tags),
            hashtags=json.dumps(raw.hashtags),
            file_path=file_path,
            status=ScriptStatus.DRAFT,
        )

        if session:
            repo = ScriptRepository(session)
            script_record = await repo.create(script_record)

        elapsed = time.monotonic() - start
        logger.info(
            "ShortScriptAgent complete",
            topic_id=str(topic.id),
            words=raw.word_count,
            elapsed=round(elapsed, 2),
        )

        return script_record

    async def _generate(
        self,
        topic_title: str,
        research_summary: Optional[str],
        key_facts: list[str],
        niche: str,
        language: str,
        rag_context: Optional[str] = None,
    ) -> ShortScriptAgentOutput:
        prompt = build_short_script_prompt(
            topic_title=topic_title,
            research_summary=research_summary,
            key_facts=key_facts,
            niche=niche,
            language=language,
            rag_context=rag_context,
        )

        response = await self._llm.generate_text(
            prompt=prompt,
            system=SHORT_SCRIPT_SYSTEM_PROMPT,
            temperature=0.85,
            max_tokens=2048,
        )

        return self._parse_response(response, topic_title)

    def _parse_response(self, raw: str, topic_title: str) -> ShortScriptAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            word_count = len(raw.split())
            return ShortScriptAgentOutput(
                hook=raw[:100],
                body=raw,
                cta="Follow for more tips!",
                full_script=raw,
                word_count=word_count,
                estimated_duration_seconds=max(15, min(60, int(word_count / self.WORDS_PER_SECOND))),
                seo_title=topic_title[:60],
                seo_description=topic_title,
                tags=[],
                hashtags=["#Shorts"],
            )

        hook = _strip_instruction_leaks(str(data.get("hook", "")).strip())
        intro = _strip_instruction_leaks(str(data.get("intro", "")).strip())
        main = _strip_instruction_leaks(
            str(data.get("main", data.get("body", ""))).strip()
        )
        outro = _strip_instruction_leaks(str(data.get("outro", "")).strip())
        cta = _strip_instruction_leaks(
            str(data.get("cta", "Follow for more tips!")).strip()
        )

        full_script = str(data.get("full_script", "")).strip()
        if not full_script:
            parts = [hook, intro, main, outro, cta]
            full_script = " ".join(p for p in parts if p)
        else:
            full_script = _strip_instruction_leaks(full_script)

        hook = strengthen_hook(hook, full_script)

        actual_word_count = len(full_script.split())

        if actual_word_count > self.TARGET_MAX_WORDS:
            sentences = re.split(r"(?<=[.!?])\s+", full_script)
            rebuilt: list[str] = []
            running_words = 0
            for sentence in sentences:
                sw = len(sentence.split())
                if running_words + sw > self.TARGET_MAX_WORDS and rebuilt:
                    break
                rebuilt.append(sentence)
                running_words += sw
            truncated = " ".join(rebuilt).strip()
            logger.warning(
                "Script exceeded max word count; truncated to fit Shorts duration.",
                original_words=actual_word_count,
                truncated_words=len(truncated.split()),
                max_words=self.TARGET_MAX_WORDS,
            )
            full_script = truncated
            actual_word_count = len(full_script.split())

        word_count = actual_word_count
        duration = int(word_count / self.WORDS_PER_SECOND)
        duration = max(25, min(28, duration))

        tags = list(data.get("tags", []))
        hashtags = list(data.get("hashtags", ["#Shorts"]))

        base_keywords = [w.lower() for w in re.findall(r"\w+", topic_title) if len(w) > 2] or ["video", "content"]
        modifiers = ["explained", "tips", "guide", "tutorial", "how to", "best", "breakdown", "summary", "viral", "trending", "review", "analysis", "top", "update", "secrets", "hacks", "facts", "new"]

        if len(tags) < 22:
            for mod in modifiers:
                for kw in base_keywords:
                    new_tag = f"{kw} {mod}"
                    if new_tag not in tags:
                        tags.append(new_tag)
                    if len(tags) >= 22:
                        break
                if len(tags) >= 22:
                    break
            while len(tags) < 22:
                tags.append(f"{base_keywords[0]} info {len(tags)}")

        if len(hashtags) < 8:
            for kw in base_keywords:
                new_ht = f"#{kw.capitalize()}"
                if new_ht not in hashtags:
                    hashtags.append(new_ht)
                if len(hashtags) >= 8:
                    break
            for mod in modifiers:
                new_ht = f"#{mod.capitalize()}"
                if new_ht not in hashtags:
                    hashtags.append(new_ht)
                if len(hashtags) >= 8:
                    break
            while len(hashtags) < 8:
                hashtags.append(f"#Trend{len(hashtags)}")

        seo_title = str(data.get("seo_title", topic_title[:60])).strip() or topic_title[:60]

        hook, cta, full_script, seo_title = self._apply_script_qa(
            hook=hook,
            main=main,
            cta=cta,
            full_script=full_script,
            seo_title=seo_title,
        )

        seo_description = self._enrich_description(
            description=str(data.get("seo_description", "")),
            hashtags=hashtags,
            cta=cta,
        )

        actual_word_count = len(full_script.split())
        word_count = actual_word_count
        duration = int(word_count / self.WORDS_PER_SECOND)
        duration = max(25, min(28, duration))

        return ShortScriptAgentOutput(
            hook=hook,
            body=main,
            cta=cta,
            full_script=full_script,
            word_count=word_count,
            estimated_duration_seconds=duration,
            seo_title=seo_title,
            seo_description=seo_description,
            tags=tags,
            hashtags=hashtags,
        )

    def _apply_script_qa(
        self,
        hook: str,
        main: str,
        cta: str,
        full_script: str,
        seo_title: str,
    ) -> tuple[str, str, str, str]:
        """Enforce count honesty and CTA = last spoken line.

        Returns (hook, cta, full_script, seo_title) possibly adjusted.
        """
        cta_clean = (cta or "").strip()
        fs = (full_script or "").strip()
        if cta_clean:
            if cta_clean not in fs:
                fs = (fs + " " + cta_clean).strip()
                logger.info("Script QA: appended cta onto full_script for voice/caption match")
            else:
                if not fs.rstrip(".!?").endswith(cta_clean.rstrip(".!?")):
                    fs_wo = fs.replace(cta_clean, " ").strip()
                    fs_wo = re.sub(r"\s{2,}", " ", fs_wo)
                    fs = (fs_wo + " " + cta_clean).strip()
                    logger.info("Script QA: moved cta to end of full_script")

        promised = self._extract_promised_count(hook, seo_title)
        if promised is not None and promised >= 2:
            items = self._count_main_items(main)
            if items and items < promised:
                logger.warning(
                    "Script QA: hook/title promises more items than MAIN delivers",
                    promised=promised,
                    delivered=items,
                )
                seo_title = self._rewrite_count_in_title(seo_title, items)
                hook = self._rewrite_count_in_title(hook, items)
                logger.info(
                    "Script QA: rewrote promised count to match MAIN",
                    new_count=items,
                )

        return hook, cta_clean, fs, seo_title

    @staticmethod
    def _extract_promised_count(hook: str, seo_title: str) -> int | None:
        blob = f"{hook or ''} {seo_title or ''}"
        matches = re.findall(
            r"(?:top\s*)?(\d)\s+(?:best |new |free |secret )?(?:\w+\s+){0,2}"
            r"(?:phones?|apps?|tips?|hacks?|tricks?|ways?|tools?|ideas?|facts?|steps?|secrets?)",
            blob,
            flags=re.I,
        )
        if matches:
            n = int(matches[0])
            if 2 <= n <= 9:
                return n
        m = re.search(r"\b([2-9])\b", (seo_title or hook or "")[:40])
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _count_main_items(main: str) -> int:
        if not main:
            return 0
        ordinals = re.findall(
            r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|"
            r"1st|2nd|3rd|4th|5th|6th|7th|8th|9th)\b",
            main,
            flags=re.I,
        )
        if ordinals:
            return len(ordinals)
        numbered = re.findall(r"(?:^|[\s])([1-9])[\.\)]\s", main)
        if numbered:
            return len(numbered)
        soft = re.findall(r"\b(Next|Then|Also|Plus)\b", main, flags=re.I)
        if soft:
            return len(soft) + 1
        return 0

    @staticmethod
    def _rewrite_count_in_title(text: str, new_count: int) -> str:
        if not text or new_count < 1:
            return text
        return re.sub(r"\b([2-9])\b", str(new_count), text, count=1)

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
        if cta and cta_lower not in desc_lower and "subscribe" not in desc_lower and "follow" not in desc_lower:
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
