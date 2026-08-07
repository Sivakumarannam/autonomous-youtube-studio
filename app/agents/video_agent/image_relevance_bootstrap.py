"""Image relevance: grounded prompts, Pexels-first, topic-aware keywords.

Applied from app.main lifespan.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def apply_image_relevance_patch() -> None:
    try:
        from app.agents.video_agent import service as vas
    except Exception as exc:
        logger.warning("image relevance patch skipped", error=str(exc))
        return

    if getattr(vas.VideoAgentService, "_image_relevance_patched", False):
        return

    async def _generate_scene_images(
        self,
        script_id: str,
        scenes: list[dict[str, Any]],
        resolution: tuple[int, int] = (1280, 720),
        topic: str = "",
    ) -> dict[int, str]:
        from app.integrations.image_provider import ImageProvider, enhance_prompt

        width, height = resolution
        mapping: dict[int, str] = {}
        _generic_label_re = re.compile(
            r"^(intro|scene|point|hook|body|cta|conclusion|outro|section)\b",
            re.IGNORECASE,
        )
        topic = (topic or getattr(self, "_current_topic_title", "") or "").strip()

        try:
            for scene in scenes:
                scene_num: int = scene.get("scene_number", 0)
                storyboard_visual = str(
                    scene.get("visual") or scene.get("image_prompt") or ""
                ).strip()
                narration = str(scene.get("narration") or "").strip()

                if narration and (
                    not storyboard_visual
                    or _generic_label_re.match(storyboard_visual)
                    or len(storyboard_visual) < 30
                ):
                    prompt = narration
                elif storyboard_visual:
                    prompt = storyboard_visual
                else:
                    prompt = narration

                if not prompt:
                    continue

                visual_prompt = (
                    f"Photorealistic scene illustrating: {prompt}. "
                    f"Relevant real-world subject matching the topic"
                    f"{f' ({topic})' if topic else ''}. "
                    f"No text, no watermark, no price tags, no sale signs, "
                    f"no logos, no stock photo watermarks, "
                    f"no faces close-up unless the topic requires a person."
                )
                enhanced = enhance_prompt(visual_prompt)

                pexels_used = False
                if settings.pexels_api_key and settings.use_stock_photos:
                    try:
                        from app.integrations.pexels_provider import (
                            download_photo,
                            extract_visual_keywords,
                        )

                        orientation = "portrait" if width < height else "landscape"
                        search_q = extract_visual_keywords(prompt, topic=topic)
                        pexels_path = await download_photo(
                            search_q, orientation=orientation
                        )
                        if pexels_path:
                            mapping[scene_num] = pexels_path
                            pexels_used = True
                            logger.info(
                                "Pexels stock photo selected",
                                scene=scene_num,
                                query=search_q,
                                topic=topic[:80] if topic else "",
                            )
                    except Exception as pex_exc:
                        logger.debug("Pexels fetch skipped", error=str(pex_exc))

                if not pexels_used:
                    path = await ImageProvider.generate(
                        prompt=enhanced,
                        width=width,
                        height=height,
                        script_id=script_id,
                    )
                    if path is not None:
                        mapping[scene_num] = path

                await asyncio.sleep(2.0)

            logger.info(
                "Scene image generation complete.",
                script_id=script_id,
                total_scenes=len(scenes),
                images_generated=len(mapping),
            )
            return mapping
        except Exception as exc:
            logger.warning(
                "Scene image generation failed; proceeding with text-card fallback.",
                script_id=script_id,
                error=str(exc),
            )
            return mapping

    vas.VideoAgentService._generate_scene_images = _generate_scene_images  # type: ignore[method-assign]
    vas.VideoAgentService._image_relevance_patched = True  # type: ignore[attr-defined]
    logger.info("Image relevance patch applied (Pexels-first, topic-aware keywords)")
