"""LLM provider factory with automatic Groq → Gemini fallback.

When LLM_PROVIDER=groq and GROQ_API_KEY is set, Groq is used as the primary
provider. If Groq is unavailable (missing key, API error, rate-limit exhausted)
AND GEMINI_API_KEY is also set, the factory wraps both in a FallbackProvider
that transparently retries every request against Gemini before raising.

Priority order (when both keys are present and provider=groq):
  1. GroqProvider (free tier: 14,400 req/day)
  2. GeminiProvider (fallback: free tier 1,500 req/day)

If only one key is present, that provider is used directly — no wrapper.
"""
from __future__ import annotations

from app.llm_providers.base import BaseLLMProvider, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Fallback wrapper
# ---------------------------------------------------------------------------

class FallbackProvider(BaseLLMProvider):
    """Wraps a primary and secondary provider.

    On any exception from the primary, logs a warning and retries the call
    against the secondary.  If the secondary also raises, that exception
    propagates to the caller.
    """

    def __init__(self, primary: BaseLLMProvider, secondary: BaseLLMProvider) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def provider_name(self) -> str:
        return f"{self._primary.provider_name}→{self._secondary.provider_name}"

    async def generate(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        try:
            return await self._primary.generate(
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as primary_exc:
            logger.warning(
                "Primary LLM failed — switching to fallback provider",
                primary=self._primary.provider_name,
                fallback=self._secondary.provider_name,
                error=str(primary_exc),
            )
            return await self._secondary.generate(
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    async def generate_text(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        try:
            return await self._primary.generate_text(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as primary_exc:
            logger.warning(
                "Primary LLM failed — switching to fallback provider",
                primary=self._primary.provider_name,
                fallback=self._secondary.provider_name,
                error=str(primary_exc),
            )
            return await self._secondary.generate_text(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    async def health_check(self) -> bool:
        if await self._primary.health_check():
            return True
        return await self._secondary.health_check()

    async def close(self) -> None:
        for provider in (self._primary, self._secondary):
            try:
                if hasattr(provider, "close"):
                    await provider.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_provider() -> BaseLLMProvider:
    provider_name = settings.llm_provider.lower()
    logger.info("Creating LLM provider", provider=provider_name)

    if provider_name == "mock":
        from app.llm_providers.mock_provider import MockLLMProvider
        return MockLLMProvider()

    if provider_name == "ollama":
        from app.llm_providers.ollama_provider import OllamaProvider
        return OllamaProvider()

    if provider_name == "groq":
        from app.llm_providers.groq_provider import GroqProvider
        groq = GroqProvider()

        # Automatic Groq → Gemini fallback when both keys are configured
        if settings.groq_api_key and settings.gemini_api_key:
            from app.llm_providers.gemini_provider import GeminiProvider
            gemini = GeminiProvider()
            logger.info(
                "LLM fallback chain configured: groq → gemini",
                groq_model=settings.groq_model,
            )
            return FallbackProvider(primary=groq, secondary=gemini)

        if settings.groq_api_key:
            logger.info("Using Groq as sole LLM provider (no Gemini key)")
            return groq

        # No Groq key — try Gemini directly if available
        if settings.gemini_api_key:
            logger.warning(
                "GROQ_API_KEY not set — falling back to Gemini directly"
            )
            from app.llm_providers.gemini_provider import GeminiProvider
            return GeminiProvider()

        logger.warning(
            "Neither GROQ_API_KEY nor GEMINI_API_KEY is set — using mock provider"
        )
        from app.llm_providers.mock_provider import MockLLMProvider
        return MockLLMProvider()

    if provider_name == "gemini":
        from app.llm_providers.gemini_provider import GeminiProvider
        gemini = GeminiProvider()

        # Gemini → Groq fallback when both keys are present
        if settings.gemini_api_key and settings.groq_api_key:
            from app.llm_providers.groq_provider import GroqProvider
            groq = GroqProvider()
            logger.info("LLM fallback chain configured: gemini → groq")
            return FallbackProvider(primary=gemini, secondary=groq)

        return gemini

    if provider_name == "openai":
        from app.llm_providers.openai_provider import OpenAIProvider
        return OpenAIProvider()

    if provider_name == "anthropic":
        from app.llm_providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()

    logger.warning(
        "Unknown LLM provider, falling back to mock",
        provider=provider_name,
    )

    from app.llm_providers.mock_provider import MockLLMProvider
    return MockLLMProvider()


# Singleton provider for the application lifetime
_provider: BaseLLMProvider | None = None


def get_llm_provider() -> BaseLLMProvider:
    global _provider
    if _provider is None:
        _provider = create_llm_provider()
    return _provider


def reset_llm_provider() -> None:
    """Reset the provider singleton — used in tests."""
    global _provider
    _provider = None
