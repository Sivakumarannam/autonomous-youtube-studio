"""
Pexels free stock photo/video provider.

Requires PEXELS_API_KEY in settings.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
_PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"


def _api_key() -> str:
    return (settings.pexels_api_key or "").strip()


def is_configured() -> bool:
    return bool(_api_key())


def _cache_path(query: str, kind: str) -> Path:
    base = Path(settings.storage_local_path) / "images" / "pexels"
    base.mkdir(parents=True, exist_ok=True)
    slug = hashlib.md5(f"{kind}:{query}".encode()).hexdigest()[:12]
    return base / f"{kind}_{slug}.jpg"


async def search_photo(
    query: str,
    orientation: str = "portrait",
) -> Optional[str]:
    """Search Pexels for a photo matching `query`. Returns best-match URL or None."""
    if not is_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                _PEXELS_PHOTO_URL,
                headers={"Authorization": _api_key()},
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            photos = data.get("photos") or []
            if not photos:
                logger.debug("Pexels: no photos found", query=query)
                return None
            src = photos[0].get("src") or {}
            url = src.get("large") or src.get("medium") or src.get("original")
            logger.debug("Pexels photo found", query=query, url=(url or "")[:60])
            return url
    except Exception as exc:
        logger.warning("Pexels photo search failed", query=query, error=str(exc))
        return None


async def download_photo(query: str, orientation: str = "portrait") -> Optional[str]:
    """Search and download a Pexels photo. Cached by query."""
    cache = _cache_path(query, "photo")
    if cache.exists() and cache.stat().st_size > 1000:
        return str(cache)

    url = await search_photo(query, orientation=orientation)
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
) -> Optional[str]:
    """Search Pexels for a video matching `query`. Returns a video file URL or None."""
    if not is_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                _PEXELS_VIDEO_URL,
                headers={"Authorization": _api_key()},
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": 3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            videos = data.get("videos") or []
            if not videos:
                return None
            files = videos[0].get("video_files") or []
            files_sorted = sorted(files, key=lambda f: abs((f.get("width") or 0) - 720))
            url = files_sorted[0].get("link") if files_sorted else None
            logger.info("Pexels video found", query=query, url=(url or "")[:60])
            return url
    except Exception as exc:
        logger.warning("Pexels video search failed", query=query, error=str(exc))
        return None


def extract_visual_keywords(narration: str) -> str:
    """Concrete visual keywords for Pexels (avoid abstract / commercial junk)."""
    import re

    text = re.sub(r"[^\w\s]", " ", (narration or "").lower())
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
        "know", "just", "very", "really", "more", "most", "also", "well",
        "even", "back", "any", "first", "second", "third", "fourth", "fifth",
        "than", "now", "only", "number", "nobody", "expects", "coming",
        "changing", "everything", "follow", "daily", "updates", "shocked",
        "change", "special", "price", "sale", "deal", "today", "discount",
        "offer", "secret", "shocking", "amazing", "best", "top", "new",
        "game", "changer", "changers",
        "subscribe", "comment", "like", "share", "link", "bio",
        "watch", "next", "video", "shorts", "youtube",
    }

    anchors = [
        ("electric car", "electric car vehicle"),
        ("electric vehicle", "electric vehicle road"),
        ("ev ", "electric vehicle charging"),
        ("charging", "ev fast charging station"),
        ("battery", "electric car battery pack"),
        ("solar roof", "solar panels on car roof"),
        ("solar", "solar panels rooftop"),
        ("range", "electric car highway driving"),
        ("miles", "electric vehicle road trip"),
        ("self driving", "autonomous car sensors"),
        ("autonomous", "self driving car road"),
        ("smartphone", "modern smartphone device"),
        ("iphone", "iphone smartphone"),
        ("android", "android smartphone"),
        ("phone", "smartphone device close up"),
        ("foldable", "foldable smartphone"),
        ("chatgpt", "laptop coding artificial intelligence"),
        ("coding", "software developer laptop code"),
        ("programmer", "programmer coding screen"),
        ("ai ", "artificial intelligence technology"),
        ("robot", "humanoid robot technology"),
        ("machine learning", "data science computer screen"),
        ("rocket", "rocket launch space"),
        ("nasa", "space rocket launch"),
        ("mars", "mars planet surface"),
        ("satellite", "satellite orbit earth"),
        ("stock market", "stock market trading screen"),
        ("crypto", "cryptocurrency blockchain concept"),
        ("bitcoin", "bitcoin digital currency"),
        ("bank", "modern bank building"),
        ("workout", "person gym workout"),
        ("fitness", "fitness training gym"),
        ("meditation", "meditation calm person"),
        ("laptop", "laptop computer desk"),
        ("data center", "server room data center"),
        ("cloud", "cloud computing servers"),
        ("chip", "computer microchip close up"),
        ("semiconductor", "semiconductor wafer factory"),
    ]
    for needle, query in anchors:
        if needle in text:
            return query

    tokens = [w for w in text.split() if w not in stop_words and len(w) > 2]
    if len(tokens) > 4:
        tokens = tokens[-4:]
    return " ".join(tokens[:4]) if tokens else "technology product"
