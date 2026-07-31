import json
import re
import time
from pathlib import Path
from typing import Optional

from app.agents.thumbnail_agent.models import (
    ThumbnailAgentOutput,
    ThumbnailDesign,
    ThumbnailElement,
)
from app.agents.thumbnail_agent.prompts import (
    THUMBNAIL_SYSTEM_PROMPT,
    build_thumbnail_prompt,
)
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class ThumbnailAgent:
    """
    Thumbnail Design Agent.

    Generates a detailed thumbnail concept and design specification
    using the LLM, then renders a placeholder PNG using Pillow.
    The rendered image is saved to local storage.
    """

    AGENT_NAME = "ThumbnailAgent"

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script: Script,
        topic_title: str,
        niche: str = "technology",
    ) -> ThumbnailAgentOutput:
        """Generate thumbnail concept and render a placeholder image."""
        logger.info("ThumbnailAgent starting", script_id=str(script.id))
        start = time.monotonic()

        seo_title = script.seo_title or topic_title
        script_excerpt = script.content[:400] if script.content else ""

        try:
            output = await self._generate_concept(
                topic_title=topic_title,
                seo_title=seo_title,
                script_type=str(script.script_type),
                niche=niche,
                script_excerpt=script_excerpt,
            )
        except Exception as exc:
            logger.error("ThumbnailAgent concept generation failed", error=str(exc))
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

        # Render placeholder thumbnail to disk
        file_path = self._render_thumbnail(
            script_id=str(script.id),
            script_type=str(script.script_type),
            output=output,
        )
        output.file_path = file_path

        elapsed = time.monotonic() - start
        logger.info(
            "ThumbnailAgent complete",
            script_id=str(script.id),
            ctr_score=output.ctr_score,
            file_path=file_path,
            elapsed=round(elapsed, 2),
        )
        return output

    async def generate_concept(
        self,
        topic_title: str,
        seo_title: str = "",
        script_type: str = "long",
        niche: str = "technology",
        script_excerpt: str = "",
    ) -> ThumbnailAgentOutput:
        """Generate thumbnail concept without a Script ORM object."""
        try:
            return await self._generate_concept(
                topic_title=topic_title,
                seo_title=seo_title,
                script_type=script_type,
                niche=niche,
                script_excerpt=script_excerpt,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    async def _generate_concept(
        self,
        topic_title: str,
        seo_title: str,
        script_type: str,
        niche: str,
        script_excerpt: str,
    ) -> ThumbnailAgentOutput:
        prompt = build_thumbnail_prompt(
            topic_title=topic_title,
            seo_title=seo_title,
            script_type=script_type,
            niche=niche,
            script_excerpt=script_excerpt,
        )
        response = await self._llm.generate_text(
            prompt=prompt,
            system=THUMBNAIL_SYSTEM_PROMPT,
            temperature=0.75,
            max_tokens=2048,
        )
        return self._parse(response, topic_title)

    def _parse(self, raw: str, topic_title: str) -> ThumbnailAgentOutput:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("ThumbnailAgent JSON parse failed — using fallback")
            return self._fallback(topic_title)

        # Parse design sub-object
        design_data = data.get("design", {})
        text_elements: list[ThumbnailElement] = []
        for el in design_data.get("text_elements", []):
            if isinstance(el, dict):
                text_elements.append(
                    ThumbnailElement(
                        text=str(el.get("text", "")),
                        position=str(el.get("position", "center")),
                        font_size=str(el.get("font_size", "large")),
                        color=str(el.get("color", "#FFFFFF")),
                    )
                )

        design = ThumbnailDesign(
            background_color=str(design_data.get("background_color", "#1A1A2E")),
            accent_color=str(design_data.get("accent_color", "#E94560")),
            text_color=str(design_data.get("text_color", "#FFFFFF")),
            layout=str(design_data.get("layout", "split")),
            subject=str(design_data.get("subject", "")),
            background_style=str(design_data.get("background_style", "gradient")),
            text_elements=text_elements,
            style_notes=str(design_data.get("style_notes", "")),
        )

        try:
            ctr = max(0.0, min(100.0, float(data.get("ctr_score", 0.0))))
        except (TypeError, ValueError):
            ctr = 0.0

        return ThumbnailAgentOutput(
            concept=str(data.get("concept", f"Thumbnail for: {topic_title}")),
            design=design,
            title_text=str(data.get("title_text", topic_title[:30].upper())),
            subtitle_text=str(data.get("subtitle_text", "")),
            emoji=str(data.get("emoji", "")),
            ctr_score=ctr,
        )

    def _fallback(self, topic_title: str) -> ThumbnailAgentOutput:
        words = topic_title.upper().split()
        title_text = " ".join(words[:4])
        return ThumbnailAgentOutput(
            concept=(
                f"Bold dark-background thumbnail for '{topic_title}'. "
                "High-contrast text overlay on gradient background. "
                "Clean, professional design with niche-relevant icon."
            ),
            design=ThumbnailDesign(
                background_color="#0D1117",
                accent_color="#2196F3",
                text_color="#FFFFFF",
                layout="centered",
                subject=f"Icon or logo related to {topic_title}",
                background_style="gradient",
                text_elements=[
                    ThumbnailElement(
                        text=title_text,
                        position="center",
                        font_size="large",
                        color="#FFFFFF",
                    )
                ],
                style_notes="Dark gradient background, centered bold title text.",
            ),
            title_text=title_text,
            subtitle_text="",
            emoji="🎯",
            ctr_score=65.0,
        )

    def _render_thumbnail(
        self,
        script_id: str,
        script_type: str,
        output: ThumbnailAgentOutput,
    ) -> str:
        """
        Render a placeholder thumbnail PNG using Pillow.
        Returns the file path. Falls back gracefully if Pillow is unavailable.
        """
        thumbnails_dir = Path(settings.storage_local_path) / "thumbnails"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        file_path = thumbnails_dir / f"{script_id}_thumbnail.png"

        try:
            from PIL import Image, ImageDraw, ImageFont

            width, height = (1080, 1920) if script_type == "short" else (1280, 720)

            # Parse colors with fallback
            def _hex(hex_str: str, fallback: tuple) -> tuple:
                try:
                    h = hex_str.lstrip("#")
                    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
                except Exception:
                    return fallback

            bg_color = _hex(output.design.background_color, (13, 17, 23))
            accent_color = _hex(output.design.accent_color, (33, 150, 243))
            text_color = _hex(output.design.text_color, (255, 255, 255))

            img = Image.new("RGB", (width, height), bg_color)
            draw = ImageDraw.Draw(img)

            # Draw accent stripe
            stripe_h = height // 6
            draw.rectangle([(0, height - stripe_h), (width, height)], fill=accent_color)

            # Draw title text — use default font (no external font required)
            title = output.title_text or output.concept[:40]
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
                small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
            except (IOError, OSError):
                font = ImageFont.load_default()
                small_font = font

            # Center the title
            bbox = draw.textbbox((0, 0), title, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (width - tw) // 2
            y = (height - th) // 2
            draw.text((x, y), title, fill=text_color, font=font)

            # Subtitle
            if output.subtitle_text:
                sbbox = draw.textbbox((0, 0), output.subtitle_text, font=small_font)
                sw = sbbox[2] - sbbox[0]
                draw.text(
                    ((width - sw) // 2, y + th + 20),
                    output.subtitle_text,
                    fill=accent_color,
                    font=small_font,
                )

            img.save(str(file_path), "PNG", optimize=True)
            logger.info("Thumbnail rendered", path=str(file_path))

        except ImportError:
            # Pillow not installed — write a minimal placeholder file
            logger.warning("Pillow not available — writing placeholder thumbnail")
            file_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes only

        except Exception as exc:
            logger.error("Thumbnail render error", error=str(exc))
            file_path.write_bytes(b"\x89PNG\r\n\x1a\n")

        return str(file_path)