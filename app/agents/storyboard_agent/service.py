from app.llm_providers.factory import get_llm_provider
from app.utils.json_utils import extract_json
from app.core.config import settings

from .models import (
    StoryboardRequest,
    StoryboardResponse,
    StoryboardScene,
)

from .prompts import STORYBOARD_PROMPT


class StoryboardService:

    def __init__(self):
        self.provider = get_llm_provider()

    async def generate(
        self,
        request: StoryboardRequest,
    ) -> StoryboardResponse:

        prompt = STORYBOARD_PROMPT.format(
            script=request.script,
        )

        response = await self.provider.generate_text(
            prompt=prompt,
            temperature=0.3,
            max_tokens=1200,
        )

        try:
            data = extract_json(response)
        except Exception as exc:
            from app.core.logging import get_logger as _get_logger
            _get_logger(__name__).warning(
                "StoryboardAgent returned invalid JSON — using minimal fallback storyboard",
                error=str(exc),
            )
            return self._fallback_storyboard(request.script)

        if "scenes" not in data or not isinstance(data.get("scenes"), list):
            from app.core.logging import get_logger as _get_logger
            _get_logger(__name__).warning(
                "StoryboardAgent response missing or invalid 'scenes' — using fallback"
            )
            return self._fallback_storyboard(request.script)

        scenes = []

        for scene in data["scenes"]:
            scenes.append(
                StoryboardScene(
                    scene_number=scene["scene_number"],
                    timestamp=scene["timestamp"],
                    duration_seconds=scene["duration_seconds"],
                    narration=scene["narration"],
                    visual=scene["visual"],
                    image_prompt=scene["image_prompt"],
                )
            )

        return StoryboardResponse(
            scenes=scenes
        )

    def _fallback_storyboard(self, script: str) -> StoryboardResponse:
        """Return a minimal 3-scene storyboard when LLM output cannot be parsed."""
        words = script.split()
        third = max(1, len(words) // 3)
        parts = [
            " ".join(words[:third]),
            " ".join(words[third : third * 2]),
            " ".join(words[third * 2 :]),
        ]
        scenes = [
            StoryboardScene(
                scene_number=i + 1,
                timestamp=f"00:{i * 8:02d}-00:{(i + 1) * 8:02d}",
                duration_seconds=8,
                narration=parts[i] or "...",
                visual="Cinematic wide shot with dramatic lighting and rich colours.",
                image_prompt="Cinematic landscape, dramatic lighting, vivid colours, 8K HDR",
            )
            for i in range(3)
        ]
        return StoryboardResponse(scenes=scenes)