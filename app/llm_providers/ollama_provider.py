from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.llm_providers.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = get_logger(__name__)


class OllamaProvider(BaseLLMProvider):
    """
    Ollama LLM provider.

    A single ``httpx.AsyncClient`` is created at construction time and reused
    for every request.  This avoids the overhead of opening a new TCP
    connection on each of the 14 LLM calls that the LongScriptAgent makes.

    Call ``await provider.close()`` during application shutdown (wired into
    the FastAPI lifespan in ``main.py``) to release the connection pool.
    """

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._num_threads = settings.ollama_num_threads

        # Persistent client — one TCP connection pool for the provider's
        # lifetime.  connect timeout is short (we expect Ollama to be local);
        # read/write timeouts are long because LLM inference can take minutes.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=120.0, pool=300.0),
            # Keep-alive so successive calls reuse the same connection.
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ── Core defaults ──────────────────────────────────────────────────────

    def _default_options(self, temperature: float, max_tokens: int) -> dict:
        """
        Base Ollama options applied to every call.

        Callers may supply an ``options`` dict to ``generate()`` whose keys
        are merged over these defaults (caller wins on conflicts).  This lets
        individual call-sites tune ``num_ctx`` or ``num_batch`` without
        touching the provider.
        """
        return {
            "temperature": temperature,
            "top_p": 0.85,
            "top_k": 40,
            "repeat_penalty": 1.15,
            "num_predict": max_tokens,
            # Default context window — callers can override via options=.
            # Use settings.ollama_num_ctx_large (8192) for structure/plan calls,
            # settings.ollama_num_ctx_small (4096) for paragraph calls.
            "num_ctx": settings.ollama_num_ctx_small,
            "num_thread": self._num_threads,
            "num_batch": 256,
        }

    # ── Public API ─────────────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        options: Optional[dict] = None,
    ) -> LLMResponse:
        ollama_messages: list[dict] = []

        if system:
            ollama_messages.append({"role": "system", "content": system})

        for msg in messages:
            ollama_messages.append({"role": msg.role, "content": msg.content})

        # Merge caller options over provider defaults.
        # The caller can pass e.g. options={"num_ctx": 8192} for large prompts.
        merged_options = {**self._default_options(temperature, max_tokens), **(options or {})}

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": merged_options,
        }

        logger.debug(
            "ollama_request",
            model=self.model,
            num_messages=len(ollama_messages),
            max_tokens=max_tokens,
            temperature=temperature,
            num_ctx=merged_options.get("num_ctx"),
        )

        response = await self._client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        logger.debug(
            "ollama_response",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_duration_ns=data.get("total_duration"),
            done_reason=data.get("done_reason"),
        )

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

    async def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        options: Optional[dict] = None,
    ) -> str:
        messages = [LLMMessage(role="user", content=prompt)]
        result = await self.generate(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            options=options,
        )
        return result.content

    async def health_check(self) -> bool:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the persistent HTTP client and release all connections."""
        await self._client.aclose()
        logger.info("OllamaProvider HTTP client closed")