"""
Web Crawler — Item 2 of Phase 4 RAG Research.

Fetches raw HTML from a URL with:
  - robots.txt respect (cached per-domain)
  - Transient-error retry via is_retryable_error() from app/utils/retry.py
  - Per-URL failure isolation: any failure returns "" instead of raising

Never builds a second retry system — reuses the same classification helper
that Phase 3 (Retry Manager) already established.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.retry import is_retryable_error

logger = get_logger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Domain → RobotFileParser, cached for the process lifetime.
# Avoids re-fetching robots.txt for every URL on the same domain.
_ROBOTS_CACHE: dict[str, RobotFileParser] = {}


# ---------------------------------------------------------------------------
# robots.txt helpers
# ---------------------------------------------------------------------------

def _domain_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _get_robots(domain_root: str) -> RobotFileParser:
    """Fetch and parse robots.txt for a domain root.  Errors are silently ignored."""
    rp = RobotFileParser()
    robots_url = f"{domain_root}/robots.txt"
    try:
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.get(robots_url)
            rp.parse(resp.text.splitlines())
    except Exception:
        pass  # inaccessible robots.txt → assume crawling is allowed
    return rp


async def _is_allowed(url: str) -> bool:
    """Return True if robots.txt permits crawling *url* with our User-Agent."""
    root = _domain_root(url)
    if root not in _ROBOTS_CACHE:
        _ROBOTS_CACHE[root] = await _get_robots(root)
    return _ROBOTS_CACHE[root].can_fetch(_USER_AGENT, url)


# ---------------------------------------------------------------------------
# Single-URL fetch
# ---------------------------------------------------------------------------

async def crawl(url: str, max_retries: int = 2) -> str:
    """Fetch raw HTML for *url*.

    Returns an empty string on any unrecoverable failure.
    Transient errors (timeout, network) are retried with short backoff.
    Respects robots.txt; disallowed URLs return "" immediately.
    """
    if not url:
        return ""

    if not await _is_allowed(url):
        logger.info("Crawl skipped: robots.txt disallows", url=url)
        return ""

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=float(settings.rag_crawl_timeout_seconds),
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text

        except Exception as exc:
            attempt += 1
            if is_retryable_error(exc) and attempt <= max_retries:
                delay = float(2 ** (attempt - 1))  # 1 s, 2 s
                logger.warning(
                    "Crawl transient error; retrying",
                    url=url,
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "Crawl failed permanently",
                    url=url,
                    attempts=attempt,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return ""


# ---------------------------------------------------------------------------
# Batch fetch
# ---------------------------------------------------------------------------

async def crawl_batch(urls: list[str]) -> list[tuple[str, str]]:
    """Crawl multiple URLs concurrently.

    Returns list of (url, html) pairs.  html is "" for any failed URL.
    Individual failures are fully isolated — one bad URL never aborts others.
    """
    htmls = await asyncio.gather(*[crawl(url) for url in urls])
    return list(zip(urls, htmls))