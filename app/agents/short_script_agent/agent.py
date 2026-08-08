"""Short-form script agent — retention-loop structure for 15-30s Shorts."""
from __future__ import annotations

import json
import re
from typing import Any

from app.agents.short_script_agent.models import ShortScriptRequest, ShortScriptResult
from app.agents.short_script_agent.prompts import (
    SHORT_SCRIPT_SYSTEM_PROMPT,
    build_short_script_prompt,
    build_short_seo_prompt,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.llm_provider import LLMProvider

logger = get_logger(__name__)


class ShortScriptAgent:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm or LLMProvider()

    async def generate(self, request: ShortScriptRequest) -> ShortScriptResult:
        prompt = build_short_script_prompt(
            topic_title=request.topic_title,
            research_summary=request.research_summary,
            key_facts=request.key_facts or [],
            niche=request.niche or settings.channel_niche or "technology",
            language=request.language or "en",
            rag_context=request.rag_context,
        )
        raw = await self._llm.complete_json(
            system=SHORT_SCRIPT_SYSTEM_PROMPT,
            user=prompt,
            temperature=0.7,
        )
        result = self._parse(raw, request)
        result = self._apply_count_qa(result)
        return result

    def _parse(self, data: dict[str, Any], request: ShortScriptRequest) -> ShortScriptResult:
        if not isinstance(data, dict):
            data = {}
        hook = str(data.get("hook", "")).strip()
        intro = str(data.get("intro", "")).strip()
        main = str(data.get("main", "")).strip()
        outro = str(data.get("outro", "")).strip()
        cta = str(data.get("cta", "Subscribe for more!")).strip()
        full_script = str(data.get("full_script", "")).strip()
        if not full_script:
            parts = [p for p in (hook, intro, main, outro, cta) if p]
            full_script = " ".join(parts)

        seo_title = str(data.get("seo_title", request.topic_title or "")).strip()
        seo_description = str(data.get("seo_description", "")).strip()
        tags = data.get("tags") or []
        hashtags = data.get("hashtags") or []
        if not isinstance(tags, list):
            tags = []
        if not isinstance(hashtags, list):
            hashtags = []
        tags = [str(t).strip() for t in tags if str(t).strip()][:28]
        hashtags = [str(h).strip() for h in hashtags if str(h).strip()]
        if "#Shorts" not in hashtags and "#shorts" not in [h.lower() for h in hashtags]:
            hashtags = ["#Shorts"] + hashtags
        hashtags = hashtags[:12]

        word_count = int(data.get("word_count") or len(full_script.split()))
        duration = float(data.get("estimated_duration_seconds") or max(15.0, word_count / 2.6))

        hook, cta, full_script, seo_title = self._normalize_fields(
            hook, cta, full_script, seo_title
        )

        return ShortScriptResult(
            hook=hook,
            intro=intro,
            main=main,
            outro=outro,
            cta=cta,
            full_script=full_script,
            word_count=word_count,
            estimated_duration_seconds=duration,
            seo_title=seo_title,
            seo_description=seo_description or full_script[:140],
            tags=tags,
            hashtags=hashtags,
        )

    def _normalize_fields(
        self,
        hook: str,
        cta: str,
        full_script: str,
        seo_title: str,
    ) -> tuple[str, str, str, str]:
        hook = (hook or "").strip()
        cta_clean = self._sanitize_cta(cta)
        fs = (full_script or "").strip()
        seo_title = (seo_title or "").strip()

        # Ensure cta is last sentence of full_script
        if cta_clean:
            if cta_clean not in fs:
                fs = (fs + " " + cta_clean).strip()
            elif not fs.rstrip(".!?").endswith(cta_clean.rstrip(".!?")):
                fs = (fs + " " + cta_clean).strip()

        return hook, cta_clean, fs, seo_title

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
        # Fallback: leading number in seo_title
        m = re.search(r"\b([2-9])\b", (seo_title or "")[:60])
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _count_main_items(main: str, full_script: str) -> int:
        """Count ordinal / numbered list items in main or full script."""
        blob = f"{main or ''} {full_script or ''}"
        ordinals = re.findall(
            r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\b",
            blob,
            flags=re.I,
        )
        if ordinals:
            return len(set(o.lower() for o in ordinals))
        numbered = re.findall(r"(?:^|[\s.])(?:number\s+)?([1-9]|10)[.):]\s", blob, flags=re.I)
        if numbered:
            return len(set(numbered))
        return 0

    def _apply_count_qa(self, result: ShortScriptResult) -> ShortScriptResult:
        """If title/hook promises N but body delivers M, rewrite title number to M."""
        promised = self._extract_promised_count(result.hook, result.seo_title)
        items = self._count_main_items(result.main, result.full_script)
        if not promised or not items or promised == items:
            return result
        # Rewrite number in hook and seo_title
        new_hook = re.sub(
            rf"\b{promised}\b",
            str(items),
            result.hook or "",
            count=1,
        )
        new_title = re.sub(
            rf"\b{promised}\b",
            str(items),
            result.seo_title or "",
            count=1,
        )
        logger.info(
            "count_qa_rewrite",
            promised=promised,
            items=items,
            hook_before=result.hook,
            hook_after=new_hook,
        )
        result.hook = new_hook
        result.seo_title = new_title
        # Keep full_script hook aligned if it starts with old hook
        if result.full_script and result.hook:
            # soft: replace first occurrence of old number in full_script opening
            fs = result.full_script
            fs2 = re.sub(rf"\b{promised}\b", str(items), fs, count=1)
            result.full_script = fs2
        return result

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
        niche: str,
        hashtags: list[str],
    ) -> str:
        d = (description or "").strip()
        if not d:
            d = f"Daily {niche} facts. Subscribe for more."
        tags_line = " ".join(hashtags[:5]) if hashtags else "#Shorts"
        if tags_line not in d:
            d = f"{d} {tags_line}".strip()
        return d[:500]
