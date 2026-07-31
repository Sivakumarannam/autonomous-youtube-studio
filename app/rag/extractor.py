"""
Content Extractor — Item 3 of Phase 4 RAG Research.

Strips boilerplate (nav, ads, scripts, sidebars) from raw HTML and returns
clean article text suitable for embedding.

Strategy:
  1. trafilatura.extract() — battle-tested boilerplate remover
  2. BeautifulSoup <p> extraction — fallback for pages trafilatura cannot parse
  3. Return empty ExtractedContent if neither method yields ≥ 50 chars

Never raises — failures return ExtractedContent with empty text.
"""
from __future__ import annotations

from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)

_MIN_CONTENT_LEN = 50  # below this we treat the extraction as failed


@dataclass(frozen=True)
class ExtractedContent:
    text: str
    title: str
    source_url: str

    @property
    def is_empty(self) -> bool:
        return len(self.text.strip()) < _MIN_CONTENT_LEN


def extract(html: str, source_url: str) -> ExtractedContent:
    """Extract clean article text and title from raw HTML.

    Returns ExtractedContent.  text is "" if extraction fails.
    """
    if not html:
        return ExtractedContent(text="", title="", source_url=source_url)

    title = _extract_title(html)

    # --- Pass 1: trafilatura ---
    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        ) or ""
        if len(text.strip()) >= _MIN_CONTENT_LEN:
            logger.debug("trafilatura extraction ok", url=source_url, chars=len(text))
            return ExtractedContent(text=text.strip(), title=title, source_url=source_url)
    except Exception as exc:
        logger.debug("trafilatura raised; falling back to bs4", url=source_url, error=str(exc))

    # --- Pass 2: BeautifulSoup <p> fallback ---
    text = _bs4_extract(html)
    if len(text.strip()) >= _MIN_CONTENT_LEN:
        logger.debug("bs4 fallback extraction ok", url=source_url, chars=len(text))
        return ExtractedContent(text=text.strip(), title=title, source_url=source_url)

    logger.debug("extraction yielded no usable content", url=source_url)
    return ExtractedContent(text="", title=title, source_url=source_url)


def _extract_title(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        return tag.get_text(strip=True) if tag else ""
    except Exception:
        return ""


def _bs4_extract(html: str) -> str:
    """Join non-trivial <p> texts as a last-resort content extraction."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
        return "\n".join(p for p in paragraphs if len(p) > 40)
    except Exception:
        return ""


def extract_batch(items: list[tuple[str, str]]) -> list[ExtractedContent]:
    """Extract content from a list of (html, source_url) pairs.

    Skips pairs with empty HTML.  Never raises — returns empty
    ExtractedContent on per-item failure.
    """
    results: list[ExtractedContent] = []
    for html, url in items:
        try:
            results.append(extract(html, url))
        except Exception as exc:
            logger.warning("Extraction error (skipping)", url=url, error=str(exc))
            results.append(ExtractedContent(text="", title="", source_url=url))
    return results
