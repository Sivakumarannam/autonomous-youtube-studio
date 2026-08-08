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


def extract_visual_keywords(narration: str, topic: str = "") -> str:
    """Topic-agnostic visual query for Pexels. Avoids literal idioms & filler."""
    import re

    def _clean(s: str) -> str:
        s = re.sub(r"[^\w\s]", " ", (s or "").lower())
        return re.sub(r"\s+", " ", s).strip()

    text = _clean(narration)
    topic_l = _clean(topic)

    # Universal idioms → never search the literal words
    idiom_map = [
        (r"break(?:ing)? the bank", "money savings budget"),
        (r"costs? an arm and a leg", "expensive price tag"),
        (r"piece of cake", "easy simple task"),
        (r"hit the nail", "precise solution"),
        (r"game changer", "innovation technology breakthrough"),
        # Do not map to party/gender-reveal stock
        (r"nobody expects?", ""),
        (r"the one nobody expects", ""),
        (r"but wait[-—,]?\s*number\s+\w+", ""),
        (r"number (one|two|three|four|five|1|2|3|4|5)", ""),
        (r"follow for (daily )?\w+", ""),
        (r"subscribe|comment|like and share", ""),
        (r"link in (the )?bio", ""),
        (r"which trend will you", ""),
        (r"invest in\??", ""),
    ]
    for pat, repl in idiom_map:
        text = re.sub(pat, repl, text)

    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
        "for", "with", "about", "from", "up", "out", "and", "or", "but", "if",
        "that", "this", "these", "those", "it", "its", "so", "as", "how",
        "what", "when", "where", "which", "who", "why", "your", "our", "their",
        "you", "we", "they", "first", "second", "third", "number", "nobody",
        "expects", "actually", "really", "very", "just", "also", "more",
        "most", "than", "now", "only", "into", "over", "under", "again",
        "then", "once", "without", "everything", "coming", "changing",
        "follow", "daily", "subscribe", "comment", "share", "video", "shorts",
        "youtube", "watch", "next", "one", "will", "build", "builds",
    }

    # Safe multi-word anchors (multi-niche). Never map bare "bank" → building.
    anchors = [
        ("electric vehicle", "electric vehicle charging"),
        ("electric car", "electric car road"),
        ("solar panel", "solar panels rooftop"),
        ("stock market", "stock market trading screen"),
        ("data center", "server room data center"),
        ("machine learning", "data science computer screen"),
        ("smart phone", "modern smartphone"),
        ("smartphone", "modern smartphone device"),
        ("gaming pc", "gaming computer desk"),
        ("graphics card", "computer graphics card"),
        ("microchip", "computer microchip close up"),
        ("cpu processor", "computer processor close up"),
        ("refurbished", "refurbished electronics product"),
    ]
    combined = f"{topic_l} {text}".strip()
    for needle, query in anchors:
        if needle in combined:
            return query

    tokens = [w for w in text.split() if w not in stop and len(w) > 2]
    topic_tokens = [w for w in topic_l.split() if w not in stop and len(w) > 2]

    # Prefer topic nouns, then narration nouns (max 5)
    ranked: list[str] = []
    for w in topic_tokens + tokens:
        if w not in ranked:
            ranked.append(w)
        if len(ranked) >= 5:
            break

    if ranked:
        return " ".join(ranked)
    if topic_tokens:
        return " ".join(topic_tokens[:4])
    return "technology product professional photo"
