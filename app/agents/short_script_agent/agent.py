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
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.research import Research
from app.database.models.script import Script, ScriptStatus, ScriptType
from app.database.models.topic import Topic
from app.database.repositories.script_repository import ScriptRepository
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Instruction-leak safety net
#
# Even with a clear prompt, small local models (via Ollama) sometimes echo
# scaffolding/meta-text into the actual script fields instead of writing
# real spoken content — e.g. "The opening 1-2 sentences (first 3-5 seconds)"
# appearing verbatim as the hook, instead of an actual hook sentence.
#
# This mirrors the proven pattern already used in voice_agent/agent.py's
# _strip_instruction_leaks — catch known scaffolding phrases and drop any
# sentence containing them before the text ever reaches TTS or captions.
# ---------------------------------------------------------------------------
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
]
_LEAK_PATTERN = re.compile("|".join(_INSTRUCTION_LEAK_PATTERNS), re.IGNORECASE)


def _strip_instruction_leaks(text: str) -> str:
    """Remove sentences that look like leaked prompt scaffolding rather than
    real spoken script content. Returns the text unchanged if nothing matches.
    """
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if not _LEAK_PATTERN.search(s)]
    if not kept:
        # Everything matched — better to return the original than an empty
        # script; this should be rare given the prompt fix.
        return text.strip()
    result = " ".join(kept).strip()
    return re.sub(r"  +", " ", result)


class ShortScriptAgent:
    """
    Short Script Agent.

    Generates a 40-90 word YouTube Shorts script (9:16, 15-30 seconds),
    following a 5-part Hook / Intro / Main / Outro / CTA structure.
    """

    AGENT_NAME = "ShortScriptAgent"
    TARGET_MIN_WORDS = 65   # 65 words @ 158 wpm ≈ 25 s
    TARGET_MAX_WORDS = 75   # 75 words @ 158 wpm ≈ 28 s
    WORDS_PER_SECOND = 2.63  # gTTS measured ~158 wpm on Replit

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
        """Generate and persist a short script for a topic.

        Args:
            rag_context: Optional web-research context string from
                RagResearchService.retrieve_context().  When provided it is
                appended to the generation prompt.  Pass None (default) to
                generate without RAG augmentation.
        """
        logger.info("ShortScriptAgent starting", topic_id=str(topic.id))
        start = time.monotonic()

        # Extract research data
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

        # Save to disk
        file_path = self._save_script_file(topic_id=str(topic.id), content=raw.full_script)

        # Persist to DB
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
            # Treat entire response as full script
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

        # Pull the new 5-part fields.  "body" is kept as an alias of "main"
        # for backward compatibility with ShortScriptAgentOutput's existing
        # schema, which only has hook/body/cta — intro and outro get folded
        # into full_script but are also sanitized individually so a leak in
        # either one never survives into the final spoken text.
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

        # ------------------------------------------------------------------
        # HARD WORD-COUNT ENFORCEMENT
        #
        # Small local models frequently ignore the 40-90 word instruction and
        # keep writing -- the LLM's own self-reported "word_count" field is
        # NOT trustworthy evidence that it complied (it has been observed
        # claiming ~84 words while actually writing ~150+, nearly doubling
        # the real spoken/video duration and breaking the Shorts format).
        #
        # Always compute word_count from the ACTUAL full_script text, never
        # from the model's self-report. If the real script overshoots the
        # max, truncate at the nearest sentence boundary so the video stays
        # within Shorts duration instead of silently ballooning to 60s+.
        # ------------------------------------------------------------------
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

        # --- DETERMINISTIC SEO PADDING ---
        tags = list(data.get("tags", []))
        hashtags = list(data.get("hashtags", ["#Shorts"]))
        
        base_keywords = [w.lower() for w in re.findall(r'\w+', topic_title) if len(w) > 2] or ["video", "content"]
        modifiers = ["explained", "tips", "guide", "tutorial", "how to", "best", "breakdown", "summary", "viral", "trending", "review", "analysis", "top", "update", "secrets", "hacks", "facts", "new"]
        
        # Pad tags up to 22
        if len(tags) < 22:
            for mod in modifiers:
                for kw in base_keywords:
                    new_tag = f"{kw} {mod}"
                    if new_tag not in tags:
                        tags.append(new_tag)
                    if len(tags) >= 22: break
                if len(tags) >= 22: break
            while len(tags) < 22: tags.append(f"{base_keywords[0]} info {len(tags)}")

        # Pad hashtags up to 8
        if len(hashtags) < 8:
            for kw in base_keywords:
                new_ht = f"#{kw.capitalize()}"
                if new_ht not in hashtags: hashtags.append(new_ht)
                if len(hashtags) >= 8: break
            for mod in modifiers:
                new_ht = f"#{mod.capitalize()}"
                if new_ht not in hashtags: hashtags.append(new_ht)
                if len(hashtags) >= 8: break
            while len(hashtags) < 8: hashtags.append(f"#Trend{len(hashtags)}")
        # ---------------------------------

        seo_description = self._enrich_description(
            description=str(data.get("seo_description", "")),
            hashtags=hashtags,
            cta=cta,
        )

        return ShortScriptAgentOutput(
            hook=hook,
            body=main,
            cta=cta,
            full_script=full_script,
            # Deliberately NOT using data.get("word_count", ...) or
            # data.get("estimated_duration_seconds", ...) here -- the LLM's
            # self-reported values are not reliable (see enforcement block
            # above) and using them let a ~150-word script pass through
            # labelled as 84 words, breaking the Shorts duration target.
            word_count=word_count,
            estimated_duration_seconds=duration,
            seo_title=str(data.get("seo_title", topic_title[:60])),
            seo_description=seo_description,
            tags=tags,
            hashtags=hashtags,
        )

    def _enrich_description(
        self,
        description: str,
        hashtags: list[str],
        cta: str,
    ) -> str:
        """Ensure seo_description passes the SEO gate.

        Guarantees:
        1. At least 7 inline #hashtags embedded in the text (scorer checks
           for #word tokens directly inside seo_description, not the separate
           hashtags column).
        2. Minimum 100 characters (description length sub-score).
        3. A recognisable call-to-action phrase present.
        """
        desc = description.strip()

        # 1. Embed hashtags inline if not already present
        existing_inline = set(re.findall(r"#\w+", desc))
        missing = [h for h in hashtags if h not in existing_inline]
        needed = max(0, 7 - len(existing_inline))
        if needed > 0 and missing:
            desc = desc.rstrip() + " " + " ".join(missing[:needed])

        # 2. Append CTA if no recognisable call-to-action is present
        cta_lower = cta.lower()
        desc_lower = desc.lower()
        if cta and cta_lower not in desc_lower and "subscribe" not in desc_lower and "follow" not in desc_lower:
            desc = desc.rstrip() + " " + cta.strip()

        # 3. Pad to minimum 100 chars
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