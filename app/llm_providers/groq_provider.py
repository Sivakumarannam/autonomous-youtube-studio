"""
Groq LLM provider.

Uses the Groq REST API (OpenAI-compatible) with a persistent httpx.AsyncClient.
Free tier: 14,400 requests/day, 6,000 tokens/min on llama-3.3-70b-versatile.

Rate-limit handling: on 429, we parse the "Please try again in Xs" from the
error body and sleep that long before retrying (up to _MAX_RETRIES times).
This keeps all retries inside the provider so the pipeline never sees a 429.
"""
from typing import Optional
import asyncio
import re

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = get_logger(__name__)

_MAX_RETRIES = 6          # max 429 retries before raising
_DEFAULT_WAIT = 15.0      # fallback wait if we can't parse retry-after


class GroqProvider(BaseLLMProvider):
    """
    Groq cloud LLM provider (free tier, no local hardware required).

    Default model: llama-3.3-70b-versatile
    Free limits: 14,400 req/day · 6,000 tokens/min · 500,000 tokens/day
    """

    def __init__(self) -> None:
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self._client = httpx.AsyncClient(
            base_url="https://api.groq.com",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    @property
    def provider_name(self) -> str:
        return "groq"

    async def generate(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        api_messages: list[dict] = []

        if system:
            api_messages.append({"role": "system", "content": system})

        for msg in messages:
            api_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.debug(
            "groq_request",
            model=self.model,
            num_messages=len(api_messages),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Retry loop — handles Groq 429 rate-limit transparently so the
        # pipeline never sees a rate-limit error.
        for attempt in range(_MAX_RETRIES + 1):
            response = await self._client.post(
                "/openai/v1/chat/completions",
                json=payload,
            )
            if response.status_code == 429:
                # Parse "Please try again in 6.19s" from the error body
                body_text = response.text
                wait = _DEFAULT_WAIT
                m = re.search(r"try again in (\d+(?:\.\d+)?)s", body_text)
                if m:
                    wait = float(m.group(1)) + 1.0   # +1s safety margin
                logger.warning(
                    "groq_rate_limited",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                    tpm_info=body_text[body_text.find("Limit"):body_text.find("Need") - 1]
                    if "Limit" in body_text else "",
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
                # Exhausted all retries — raise so the caller knows
                response.raise_for_status()

            if response.status_code != 200:
                logger.error(
                    "groq_api_error",
                    status=response.status_code,
                    body=response.text[:500],
                )
                response.raise_for_status()
            break   # success

        data = response.json()
        choice = data["choices"][0]
        content = choice["message"]["content"] or ""
        usage = data.get("usage", {})

        logger.debug(
            "groq_response",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason"),
        )

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider_name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    async def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        messages = [LLMMessage(role="user", content=prompt)]
        result = await self.generate(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result.content

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/openai/v1/models")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
        logger.info("GroqProvider HTTP client closed")
