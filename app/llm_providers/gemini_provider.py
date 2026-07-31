from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from app.llm_providers.base import BaseLLMProvider, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider — uses the current google-genai SDK."""

    # gemini-2.0-flash-lite: fastest free-tier model available on this API key.
    # This API key does not have gemini-1.5-flash — it only has 2.0+ models.
    MODEL = "gemini-2.0-flash-lite"

    def __init__(self):
        if not settings.gemini_api_key:
            raise LLMProviderError("gemini", "GEMINI_API_KEY is not set")
        try:
            from google import genai  # type: ignore
            self._client = genai.Client(api_key=settings.gemini_api_key)
        except ImportError:
            raise LLMProviderError(
                "gemini",
                "google-genai package not installed — run: pip install google-genai",
            )

    @property
    def provider_name(self) -> str:
        return "gemini"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        from google.genai import types  # type: ignore

        # Build the flat prompt string (same approach as before — keeps
        # behaviour identical while using the new SDK).
        parts = []
        if system:
            parts.append(f"System: {system}\n\n")
        for msg in messages:
            parts.append(f"{msg.role.capitalize()}: {msg.content}\n")
        prompt = "".join(parts)

        try:
            response = await self._client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            content = response.text or ""
            usage = response.usage_metadata or types.GenerateContentResponseUsageMetadata()
            return LLMResponse(
                content=content,
                model=self.MODEL,
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                provider="gemini",
            )
        except Exception as e:
            logger.error("Gemini generation failed", error=str(e))
            raise LLMProviderError("gemini", str(e))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        from google.genai import types  # type: ignore

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        try:
            response = await self._client.aio.models.generate_content(
                model=self.MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text or ""
        except Exception as e:
            logger.error("Gemini text generation failed", error=str(e))
            raise LLMProviderError("gemini", str(e))
