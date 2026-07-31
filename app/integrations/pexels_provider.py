"""
Pexels Stock Media Provider — free stock photos and videos.

Free API with 200 requests/hour, 20,000/month.
Sign up at https://www.pexels.com/api/ to get a free API key.

Configure via environment variable:
    PEXELS_API_KEY=your_key_here

Usage:
    photo_url = await PexelsProvider.search_photo("didgeridoo musical instrument")
    video_url = await PexelsProvider.search_video("ocean waves")
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
_PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
_TIMEOUT = 20.0
_CACHE_DIR = Path("./storage/cache/pexels")


def _api_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def is_configured() -> bool:
    return bool(_api_key())


def _cache_path(query: str, kind: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = hashlib.md5(f"{kind}:{query}".encode()).hexdigest()[:12]
    return _CACHE_DIR / f"{slug}.{'mp4' if kind == 'video' else 'jpg'}"


async def search_photo(
    query: str,
    orientation: str = "portrait",
    per_page: int = 5,
) -> Optional[str]:
    """
    Search Pexels for a photo matching `query`.

    Returns the URL of the best matching photo (landscape or portrait),
    or None if the API is not configured or no results were found.
    """
    key = _api_key()
    if not key:
        return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _PEXELS_PHOTO_URL,
                headers={"Authorization": key},
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": per_page,
                    "size": "large",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        photos = data.get("photos", [])
        if not photos:
            logger.debug("Pexels: no photos found", query=query)
            return None

        # Pick best photo: prefer portrait for Shorts, landscape for long
        photo = photos[0]
        src = photo.get("src", {})
        url = src.get("large2x") or src.get("large") or src.get("original")
        logger.info(
            "Pexels photo found",
            query=query,
            photographer=photo.get("photographer", "unknown"),
            url=url[:60] if url else "",
        )
        return url
    except Exception as exc:
        logger.warning("Pexels photo search failed", query=query, error=str(exc))
        return None


async def download_photo(query: str, orientation: str = "portrait") -> Optional[str]:
    """
    Search and download a Pexels photo for `query`.

    Returns the local file path, or None on failure.
    Cached by query — same query returns same file immediately.
    """
    cache = _cache_path(query, "photo")
    if cache.exists() and cache.stat().st_size > 1000:
        return str(cache)

    url = await search_photo(query, orientation=orientation)
    if url is None:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cache.write_bytes(resp.content)
        logger.info("Pexels photo downloaded", query=query, path=str(cache))
        return str(cache)
    except Exception as exc:
        logger.warning("Pexels photo download failed", query=query, error=str(exc))
        return None


async def search_video(
    query: str,
    orientation: str = "portrait",
    per_page: int = 3,
) -> Optional[str]:
    """
    Search Pexels for a video matching `query`.

    Returns the URL of the best matching video file (HD), or None.
    """
    key = _api_key()
    if not key:
        return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _PEXELS_VIDEO_URL,
                headers={"Authorization": key},
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": per_page,
                    "size": "medium",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        videos = data.get("videos", [])
        if not videos:
            return None

        video = videos[0]
        # Pick best quality file: prefer HD (1280x720 or better)
        files = sorted(
            video.get("video_files", []),
            key=lambda f: f.get("width", 0),
            reverse=True,
        )
        url = next(
            (f["link"] for f in files if f.get("width", 0) >= 720),
            files[0]["link"] if files else None,
        )
        logger.info("Pexels video found", query=query, url=(url or "")[:60])
        return url
    except Exception as exc:
        logger.warning("Pexels video search failed", query=query, error=str(exc))
        return None


def extract_visual_keywords(narration: str) -> str:
    """
    Extract concrete visual keywords from a narration sentence for stock search.

    Strategy: remove filler words and abstract terms, keep nouns, places,
    actions, and objects.  Simple heuristic — good enough for Pexels queries.
    """
    import re

    # Strip punctuation for processing
    text = re.sub(r"[^\w\s]", " ", narration.lower())

    # Common filler / abstract words to skip
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "on", "at", "by", "for", "with", "about",
        "against", "between", "into", "through", "during", "before", "after",
        "above", "below", "from", "up", "down", "out", "off", "over", "under",
        "again", "then", "once", "and", "or", "but", "if", "while", "that",
        "this", "these", "those", "it", "its", "so", "as", "how", "what",
        "when", "where", "which", "who", "why", "your", "our", "their", "you",
        "we", "they", "he", "she", "i", "me", "him", "her", "us", "them",
        "know", "did", "just", "very", "really", "more", "most", "also",
        "well", "even", "back", "any", "first", "than", "now", "only",
    }

    tokens = [w for w in text.split() if w not in stop_words and len(w) > 2]
    # Take first 4 meaningful tokens as the search query
    return " ".join(tokens[:4]) if tokens else narration[:50]
