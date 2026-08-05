import json
import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.long_script_agent.models import ChapterTimestamp, LongScriptAgentOutput, ScriptSection
from app.agents.long_script_agent.prompts import (
    LONG_SCRIPT_SYSTEM_PROMPT,
    build_long_script_prompt,
)
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.research import Research
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.topic import Topic
from app.database.repositories.script_repository import ScriptRepository
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class LongScriptAgent:
    """
    Long Script Agent.

    Generates a 1000-1500 word YouTube long-form script (16:9, 8-10 minutes).
    """

    AGENT_NAME = "LongScriptAgent"
    TARGET_MIN_WORDS = 1050  # 1050 words @ 175 wpm ≈ 6 min
    TARGET_MAX_WORDS = 1400  # 1400 words @ 175 wpm ≈ 8 min
    WORDS_PER_SECOND = 2.92  # gTTS measured ~175 wpm on Replit

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
        """Generate and persist a long-form script for a topic.

        Args:
            rag_context: Optional web-research context string from
                RagResearchService.retrieve_context().  When provided it is
                appended to the generation prompt.  Pass None (default) to
                generate without RAG augmentation.
        """
        logger.info("LongScriptAgent starting", topic_id=str(topic.id))
        start = time.monotonic()

        summary, key_facts, talking_points = self._extract_research(research)

        try:
            output = await self._generate(
                topic_title=topic.title,
                research_summary=summary,
                key_facts=key_facts,
                talking_points=talking_points,
                niche=niche,
                language="en",
                rag_context=rag_context,
            )
        except Exception as e:
            logger.error("LongScriptAgent failed", error=str(e))
            raise AgentError(self.AGENT_NAME, str(e)) from e

        file_path = self._save_script_file(str(topic.id), output.full_script)

        script_record = Script(
            topic_id=topic.id,
            channel_id=topic.channel_id,
            script_type=ScriptType.LONG,
            content=output.full_script,
            word_count=output.word_count,
            estimated_duration=output.estimated_duration_seconds,
            hook=output.hook,
            cta=output.cta,
            seo_title=output.seo_title,
            seo_description=output.seo_description,
            seo_tags=json.dumps(output.tags),
            hashtags=json.dumps(output.hashtags),
            file_path=file_path,
            status=ScriptStatus.DRAFT,
        )

        if session:
            repo = ScriptRepository(session)
            script_record = await repo.create(script_record)

        elapsed = time.monotonic() - start
        logger.info(
            "LongScriptAgent complete",
            topic_id=str(topic.id),
            words=output.word_count,
            elapsed=round(elapsed, 2),
        )

        return script_record

    async def _generate(
        self,
        topic_title: str,
        research_summary: Optional[str],
        key_facts: list[str],
        talking_points: list[str],
        niche: str,
        language: str,
        rag_context: Optional[str] = None,
    ) -> LongScriptAgentOutput:
        prompt = build_long_script_prompt(
            topic_title=topic_title,
            research_summary=research_summary,
            key_facts=key_facts,
            talking_points=talking_points,
            niche=niche,
            language=language,
            rag_context=rag_context,
        )

        response = await self._llm.generate_text(
            prompt=prompt,
            system=LONG_SCRIPT_SYSTEM_PROMPT,
            temperature=0.75,
            max_tokens=8192,
        )

        output = self._parse_response(response, topic_title)

        if output.word_count < self.TARGET_MIN_WORDS:
            shortfall = self.TARGET_MIN_WORDS - output.word_count
            logger.warning(
                "Long script below minimum word count — running expansion pass.",
                words_generated=output.word_count,
                target_min=self.TARGET_MIN_WORDS,
                shortfall=shortfall,
            )
            expansion_prompt = (
                f"The following YouTube script for '{topic_title}' is {output.word_count} words "
                f"but must be at least {self.TARGET_MIN_WORDS} words (6-8 minutes at 165 wpm). "
                f"Expand it by adding approximately {shortfall + 100} more words. "
                f"Add more depth, examples, analogies, and data points to each section. "
                f"Keep the same JSON structure and all existing fields. "
                f"Return the COMPLETE expanded JSON with the updated full_script and word_count.\n\n"
                f"Current script:\n{response}"
            )
            try:
                expanded_response = await self._llm.generate_text(
                    prompt=expansion_prompt,
                    system=LONG_SCRIPT_SYSTEM_PROMPT,
                    temperature=0.7,
                    max_tokens=8192,
                )
                expanded_output = self._parse_response(expanded_response, topic_title)
                if expanded_output.word_count > output.word_count:
                    logger.info(
                        "Expansion pass succeeded.",
                        original_words=output.word_count,
                        expanded_words=expanded_output.word_count,
                    )
                    output = expanded_output
                else:
                    logger.warning(
                        "Expansion pass did not increase word count — using original.",
                        original_words=output.word_count,
                        expanded_words=expanded_output.word_count,
                    )
            except Exception as exc:
                logger.warning("Expansion pass failed — using original script.", error=str(exc))

        return output

    def _parse_response(self, raw: str, topic_title: str) -> LongScriptAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            word_count = len(raw.split())
            return LongScriptAgentOutput(
                introduction=raw[:500],
                sections=[ScriptSection(title="Main Content", content=raw, duration_seconds=480)],
                conclusion="",
                cta="Like, subscribe, and comment below!",
                full_script=raw,
                word_count=word_count,
                estimated_duration_seconds=max(490, int(word_count / self.WORDS_PER_SECOND)),
                hook=raw[:100],
                seo_title=topic_title[:70],
                seo_description=topic_title,
                tags=[],
                hashtags=[],
                thumbnail_concept="",
            )

        raw_sections = data.get("sections", [])
        sections: list[ScriptSection] = []
        for s in raw_sections:
            if isinstance(s, dict):
                sections.append(
                    ScriptSection(
                        title=str(s.get("title", "Section")),
                        content=str(s.get("content", "")),
                        duration_seconds=int(s.get("duration_seconds", 120)),
                    )
                )

        full_script = str(data.get("full_script", ""))
        if not full_script:
            parts = [
                data.get("introduction", ""),
                *[s.content for s in sections],
                data.get("conclusion", ""),
                data.get("cta", ""),
            ]
            full_script = "\n\n".join(p for p in parts if p)

        word_count = len(full_script.split())
        duration = int(word_count / self.WORDS_PER_SECOND)

        tags = list(data.get("tags", []))
        hashtags = list(data.get("hashtags", []))

        base_keywords = [w.lower() for w in re.findall(r"\w+", topic_title) if len(w) > 2] or ["video", "content"]
        modifiers = [
            "explained", "tips", "guide", "tutorial", "how to", "best", "breakdown",
            "summary", "viral", "trending", "review", "analysis", "top", "update",
            "secrets", "hacks", "facts", "new",
        ]

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
                hashtags.append(f"#Topic{len(hashtags)}")

        cta_text = str(data.get("cta", "Like, subscribe, and comment below!"))

        raw_chapters = data.get("chapter_timestamps", [])
        chapter_timestamps: list[ChapterTimestamp] = []
        if isinstance(raw_chapters, list) and raw_chapters:
            for ch in raw_chapters:
                if isinstance(ch, dict):
                    chapter_timestamps.append(
                        ChapterTimestamp(
                            time=str(ch.get("time", "00:00")),
                            title=str(ch.get("title", "")),
                        )
                    )
        if not chapter_timestamps and sections:
            chapter_timestamps.append(ChapterTimestamp(time="00:00", title="Introduction"))
            elapsed = 90
            for sec in sections:
                mins, secs = divmod(elapsed, 60)
                chapter_timestamps.append(
                    ChapterTimestamp(time=f"{mins:02d}:{secs:02d}", title=sec.title)
                )
                elapsed += sec.duration_seconds
            mins, secs = divmod(elapsed, 60)
            chapter_timestamps.append(
                ChapterTimestamp(time=f"{mins:02d}:{secs:02d}", title="Conclusion")
            )

        chapter_block = ""
        if chapter_timestamps:
            chapter_lines = "\n".join(f"{ch.time} {ch.title}" for ch in chapter_timestamps)
            chapter_block = f"\n\n⏱ Chapters:\n{chapter_lines}"

        seo_description = self._enrich_description(
            description=str(data.get("seo_description", "")),
            hashtags=hashtags,
            cta=cta_text,
        )
        if chapter_block:
            seo_description = seo_description + chapter_block

        hook_text = str(data.get("hook", "") or "")
        seo_title_text = str(data.get("seo_title", topic_title[:70]) or topic_title[:70])
        main_parts = []
        for s in (sections or []):
            main_parts.append(str(getattr(s, "title", "") or ""))
            main_parts.append(str(getattr(s, "content", "") or ""))
        main_blob = "\n".join(main_parts) if main_parts else full_script
        hook_text, cta_text, full_script, seo_title_text = self._apply_script_qa(
            hook=hook_text,
            main=main_blob,
            cta=cta_text,
            full_script=full_script,
            seo_title=seo_title_text,
        )
        word_count = len(full_script.split())

        return LongScriptAgentOutput(
            introduction=str(data.get("introduction", "")),
            sections=sections,
            conclusion=str(data.get("conclusion", "")),
            cta=cta_text,
            full_script=full_script,
            word_count=data.get("word_count", word_count),
            estimated_duration_seconds=max(
                490, int(data.get("estimated_duration_seconds", duration))
            ),
            hook=hook_text,
            seo_title=seo_title_text,
            seo_description=seo_description,
            tags=tags,
            hashtags=hashtags,
            thumbnail_concept=str(data.get("thumbnail_concept", "")),
            chapter_timestamps=chapter_timestamps,
        )

    def _apply_script_qa(
        self,
        hook: str,
        main: str,
        cta: str,
        full_script: str,
        seo_title: str,
    ) -> tuple[str, str, str, str]:
        """Enforce count honesty and CTA = last spoken line (same rules as Short)."""
        cta_clean = (cta or "").strip()
        fs = (full_script or "").strip()
        if cta_clean:
            if cta_clean not in fs:
                fs = (fs + "\n\n" + cta_clean).strip()
                logger.info("Long Script QA: appended cta onto full_script")
            else:
                if not fs.rstrip(".!?").endswith(cta_clean.rstrip(".!?")):
                    fs_wo = fs.replace(cta_clean, " ").strip()
                    fs_wo = re.sub(r"\s{2,}", " ", fs_wo)
                    fs = (fs_wo + "\n\n" + cta_clean).strip()
                    logger.info("Long Script QA: moved cta to end of full_script")

        promised = self._extract_promised_count(hook, seo_title)
        if promised is not None and promised >= 2:
            items = self._count_main_items(main)
            if items and items < promised:
                logger.warning(
                    "Long Script QA: hook/title promises more items than body delivers",
                    promised=promised,
                    delivered=items,
                )
                seo_title = self._rewrite_count_in_title(seo_title, items)
                hook = self._rewrite_count_in_title(hook, items)
                logger.info(
                    "Long Script QA: rewrote promised count to match body",
                    new_count=items,
                )

        return hook, cta_clean, fs, seo_title

    @staticmethod
    def _extract_promised_count(hook: str, seo_title: str) -> int | None:
        blob = f"{hook or ''} {seo_title or ''}"
        matches = re.findall(
            r"(?:top\s*)?(\d)\s+(?:best |new |free |secret )?(?:\w+\s+){0,2}"
            r"(?:phones?|apps?|tips?|hacks?|tricks?|ways?|tools?|ideas?|facts?|steps?|secrets?|reasons?)",
            blob,
            flags=re.I,
        )
        if matches:
            n = int(matches[0])
            if 2 <= n <= 9:
                return n
        m = re.search(r"\b([2-9])\b", (seo_title or hook or "")[:50])
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _count_main_items(main: str) -> int:
        if not main:
            return 0
        ordinals = re.findall(
            r"(?:^|\n)\s*(?:\d+[.)]|[-*]\s+|step\s+\d+|tip\s+#?\d+)",
            main,
            flags=re.I,
        )
        if len(ordinals) >= 2:
            return len(ordinals)
        nums = re.findall(
            r"\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\b",
            main,
            flags=re.I,
        )
        if len(nums) >= 2:
            return len(nums)
        return 0

    @staticmethod
    def _rewrite_count_in_title(text: str, new_count: int) -> str:
        if not text:
            return text
        rewritten = re.sub(
            r"\b([2-9]|10)\b(?=\s+(?:best |new |free |secret )?(?:\w+\s+){0,2}"
            r"(?:phones?|apps?|tips?|hacks?|tricks?|ways?|tools?|ideas?|facts?|steps?|secrets?|reasons?))",
            str(new_count),
            text,
            count=1,
            flags=re.I,
        )
        if rewritten != text:
            return rewritten
        return re.sub(r"\b([2-9]|10)\b", str(new_count), text, count=1)

    def _enrich_description(
        self,
        description: str,
        hashtags: list[str],
        cta: str,
    ) -> str:
        """Ensure seo_description passes the SEO gate.

        Guarantees:
        1. At least 7 inline #hashtags embedded in the text.
        2. Minimum 100 characters.
        3. A recognisable call-to-action phrase present.
        """
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

    def _extract_research(
        self, research: Optional[Research]
    ) -> tuple[Optional[str], list[str], list[str]]:
        if not research:
            return None, [], []
        summary = research.summary
        key_facts: list[str] = []
        talking_points: list[str] = []
        if research.key_facts:
            try:
                key_facts = json.loads(research.key_facts)
            except json.JSONDecodeError:
                pass
        if research.raw_data:
            try:
                raw_data = json.loads(research.raw_data)
                talking_points = raw_data.get("talking_points", [])
            except json.JSONDecodeError:
                pass
        return summary, key_facts, talking_points

    def _save_script_file(self, topic_id: str, content: str) -> str:
        scripts_dir = Path(settings.storage_local_path) / "scripts" / "long"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        file_path = scripts_dir / f"{topic_id}_long.txt"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
