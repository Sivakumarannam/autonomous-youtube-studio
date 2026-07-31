import asyncio
import random
from functools import wraps
from typing import Callable, Coroutine, Type, Union


def retry(
    retries: int = 3,
    delay_seconds: float = 0.5,
    max_delay_seconds: float = 5.0,
    exceptions: Union[Type[BaseException], tuple[Type[BaseException], ...]] = (Exception,),
):
    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapped(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    attempt += 1
                    if attempt > retries:
                        raise
                    jitter = random.uniform(0, delay_seconds)
                    wait = min(max_delay_seconds, delay_seconds * (2 ** (attempt - 1)) + jitter)
                    await asyncio.sleep(wait)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Retry-classification helper
#
# Used by both PipelineAgentService (Surface A) and VideoPublishScheduler
# (Surface B) to decide whether a caught exception warrants a retry attempt.
# ---------------------------------------------------------------------------

#: HTTP status codes from YouTube / upstream APIs that indicate a transient
#: condition worth retrying (rate-limit, server overload, gateway errors).
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_retryable_error(exc: BaseException) -> bool:
    """Return True iff *exc* is a transient error that should be retried.

    Retryable:
        - httpx.TimeoutException
        - httpx.NetworkError (includes ConnectError)
        - httpx.HTTPStatusError with status in {429, 500, 502, 503, 504}

    NOT retryable (fail immediately):
        - QualityError  — deliberate quality-gate rejection
        - NotFoundError — permanent data-integrity issue
        - httpx.HTTPStatusError with any other 4xx (auth, permission, quota, etc.)
        - Any other exception type (conservative default; avoids infinite loops
          on logic errors)
    """
    try:
        import httpx
        _httpx_available = True
    except ImportError:
        _httpx_available = False

    # Import lazily to avoid circular imports at module load time.
    from app.core.exceptions import QualityError, NotFoundError

    # Deliberate rejections are never retried.
    if isinstance(exc, (QualityError, NotFoundError)):
        return False

    if _httpx_available:
        import httpx

        # Transient network failures — always retryable.
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return True

        # HTTP-level errors: only specific 5xx/429 are transient.
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRYABLE_HTTP_STATUSES

    # Agents wrap their internal failures in AgentError (see
    # app/agents/*/agent.py), losing the original exception type unless the
    # explicit exception chain ("raise ... from e") is followed. Recurse
    # into __cause__ so a transient error doesn't stop being retryable just
    # because it happened inside an agent's own try/except. Deliberately
    # NOT __context__: that's set implicitly by Python on *any* exception
    # raised while handling another (e.g. an unrelated logging/cleanup
    # failure), which could misattribute an unrelated error as "the cause".
    if exc.__cause__ is not None and exc.__cause__ is not exc:
        return is_retryable_error(exc.__cause__)

    # Unknown exception types are NOT retried (safe default).
    return False
