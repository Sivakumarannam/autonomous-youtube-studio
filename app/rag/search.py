"""
Search Agent — Item 1 of Phase 4 RAG Research.

Default: DuckDuckGo HTML endpoint (no API key, no rate-limit charges).
Config-swappable: set SERPER_API_KEY or BRAVE_API_KEY in .env to use a
paid provider.  The first non-empty key wins.

Returns a ranked list of SearchResult(url, title, snippet) objects.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_SERPER_URL = "https://google.serper.dev/search"
_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# A realistic browser UA keeps DDG from serving the JS-only version.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


async def search(query: str, max_results: int | None = None) -> list[SearchResult]:
    """Search the web for a query and return ranked URL+snippet results.

    Provider selection (first non-empty key wins):
      1. Serper  — if settings.serper_api_key is set
      2. Brave   — if settings.brave_api_key is set
      3. DuckDuckGo HTML (default, always available, no key needed)
    """
    n = max_results if max_results is not None else settings.rag_search_max_results
    if settings.serper_api_key:
        return await _search_serper(query, n)
    if settings.brave_api_key:
        return await _search_brave(query, n)
    return await _search_duckduckgo(query, n)


# ---------------------------------------------------------------------------
# DuckDuckGo — default, no API key
# ---------------------------------------------------------------------------

async def _search_duckduckgo(query: str, max_results: int) -> list[SearchResult]:
    """Scrape DuckDuckGo's HTML endpoint.  No API key required."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=float(settings.rag_crawl_timeout_seconds),
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.post(_DDG_HTML_URL, data={"q": query})
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("DuckDuckGo search request failed", query=query, error=str(exc))
        return []

    return _parse_ddg_html(resp.text, max_results)


def _parse_ddg_html(html: str, max_results: int) -> list[SearchResult]:
    """Parse DDG HTML search results page into SearchResult objects."""
    soup = BeautifulSoup(html, "lxml")
    results: list[SearchResult] = []

    for div in soup.select(".result"):
        a_title = div.select_one(".result__a")
        a_snippet = div.select_one(".result__snippet")
        if not a_title:
            continue
        href: str = a_title.get("href", "")
        if not href or href.startswith("//duckduckgo"):
            continue
        title = a_title.get_text(strip=True)
        snippet = a_snippet.get_text(strip=True) if a_snippet else ""
        results.append(SearchResult(url=href, title=title, snippet=snippet))
        if len(results) >= max_results:
            break

    logger.info("DuckDuckGo parse complete", count=len(results))
    return results


# ---------------------------------------------------------------------------
# Serper — paid, Google results
# ---------------------------------------------------------------------------

async def _search_serper(query: str, max_results: int) -> list[SearchResult]:
    """Serper.dev Google Search API.  Requires SERPER_API_KEY."""
    try:
        async with httpx.AsyncClient(timeout=float(settings.rag_crawl_timeout_seconds)) as client:
            resp = await client.post(
                _SERPER_URL,
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": max_results},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Serper search failed", query=query, error=str(exc))
        return []

    data = resp.json()
    results: list[SearchResult] = []
    for item in data.get("organic", [])[:max_results]:
        results.append(
            SearchResult(
                url=item.get("link", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            )
        )
    logger.info("Serper search complete", query=query, results=len(results))
    return results


# ---------------------------------------------------------------------------
# Brave — paid, privacy-first results
# ---------------------------------------------------------------------------

async def _search_brave(query: str, max_results: int) -> list[SearchResult]:
    """Brave Search API.  Requires BRAVE_API_KEY."""
    try:
        async with httpx.AsyncClient(timeout=float(settings.rag_crawl_timeout_seconds)) as client:
            resp = await client.get(
                _BRAVE_URL,
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.brave_api_key,
                },
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Brave search failed", query=query, error=str(exc))
        return []

    data = resp.json()
    results: list[SearchResult] = []
    for item in data.get("web", {}).get("results", [])[:max_results]:
        results.append(
            SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("description", ""),
            )
        )
    logger.info("Brave search complete", query=query, results=len(results))
    return results