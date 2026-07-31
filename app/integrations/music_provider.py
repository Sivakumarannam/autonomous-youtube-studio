"""
Background Music Provider — free music for video backgrounds.

Sources (in priority order):
  1. Local bundled royalty-free tracks in storage/music/   (fastest, zero risk)
  2. Jamendo API (free, requires a free client_id)          (automated fallback)
  3. None — pipeline continues without music                (never blocks render)

NOTE ON PIXABAY:
  Pixabay's public REST API (pixabay.com/api/) only covers images and videos.
  It has no music/audio search endpoint, despite some third-party docs implying
  otherwise. Any "media_type=music" query against it will not return usable
  results. Pixabay support has been removed from the fetch chain for that
  reason — PIXABAY_API_KEY is no longer read by this module.

NOTE ON LICENSING:
  Jamendo's API is documented as free for non-commercial use; commercial use
  (which includes a monetized YouTube channel) technically requires contacting
  Jamendo for a license. Individual tracks are also commonly CC BY-NC licensed.
  Treat Jamendo as a convenient automated fallback for testing/development, and
  verify licensing terms directly with Jamendo before relying on it at scale on
  a monetized channel. Local files you've sourced yourself (Pixabay's own site
  UI, YouTube Audio Library, Mixkit, etc.) remain the safest option and are
  always tried first.

Category → genre mapping:
  technology, ai, programming → "electronic"
  motivation, fitness          → "cinematic"
  education, history, science  → "ambient"
  travel, lifestyle            → "acoustic"
  health, wellness             → "relaxing"
  finance, business            → "corporate"
  (default)                    → "background"

Configure:
    JAMENDO_CLIENT_ID=your_id_here   # free at https://devportal.jamendo.com/

Audio mixing is done with pydub (already installed).
The music is mixed under the voice at -18 dBFS (voice stays dominant).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_JAMENDO_API = "https://api.jamendo.com/v3.0/tracks/"
_CACHE_DIR = Path("./storage/cache/music")
_LOCAL_MUSIC_DIR = Path("./storage/music")
_TIMEOUT = 30.0

# Music genre per channel category
_CATEGORY_GENRE: dict[str, str] = {
    "technology":   "electronic",
    "ai":           "electronic",
    "programming":  "electronic",
    "gaming":       "electronic",
    "motivation":   "cinematic",
    "fitness":      "cinematic",
    "education":    "ambient",
    "history":      "ambient",
    "science":      "ambient",
    "travel":       "acoustic",
    "lifestyle":    "acoustic",
    "health":       "relaxing",
    "wellness":     "relaxing",
    "finance":      "corporate",
    "business":     "corporate",
    "news":         "corporate",
}

# Jamendo uses its own tag vocabulary. Map our internal genre keys to tags
# that reliably return results (Jamendo's "fuzzytags" search is lenient but
# these are known-good terms).
_GENRE_TO_JAMENDO_TAG: dict[str, str] = {
    "electronic": "electronic",
    "cinematic":  "cinematic",
    "ambient":    "ambient",
    "acoustic":   "acoustic",
    "relaxing":   "relaxing",
    "corporate":  "corporate",
    "background": "chillout",
}


def _jamendo_client_id() -> str:
    from app.core.config import settings
    return settings.jamendo_client_id or os.environ.get("JAMENDO_CLIENT_ID", "")


def is_configured() -> bool:
    has_local = _LOCAL_MUSIC_DIR.exists() and any(_LOCAL_MUSIC_DIR.glob("*.mp3"))
    return bool(has_local) or bool(_jamendo_client_id())


def genre_for_category(category: str) -> str:
    """Return the best music genre for the given channel category."""
    return _CATEGORY_GENRE.get(category.lower(), "background")


async def fetch_track(
    genre: str = "background",
    duration_hint_seconds: float = 30.0,
) -> Optional[str]:
    """
    Fetch a background music track for `genre`.

    Returns the local file path of a downloaded/local MP3, or None if
    unavailable (caller must treat None as "render without music" — never
    raises).
    """
    # 1. Local music directory first — fastest, zero network dependency,
    #    zero licensing ambiguity if you've sourced the files yourself.
    local = _find_local_track(genre)
    if local:
        return local

    # 2. Jamendo API — automated fallback. Requires JAMENDO_CLIENT_ID.
    if _jamendo_client_id():
        path = await _fetch_from_jamendo(genre, duration_hint_seconds)
        if path:
            return path

    logger.info("No background music available", genre=genre)
    return None


def _find_local_track(genre: str) -> Optional[str]:
    """Search the local music directory for a matching genre track."""
    if not _LOCAL_MUSIC_DIR.exists():
        return None
    for f in _LOCAL_MUSIC_DIR.glob("*.mp3"):
        if genre in f.stem.lower():
            return str(f)
    files = list(_LOCAL_MUSIC_DIR.glob("*.mp3"))
    return str(files[0]) if files else None


async def _fetch_from_jamendo(genre: str, duration_hint_seconds: float) -> Optional[str]:
    """Fetch a track from the Jamendo API and cache it locally.

    Jamendo search endpoint: GET https://api.jamendo.com/v3.0/tracks/
    Requires only a free client_id (no OAuth needed for public search/stream).
    Docs: https://developer.jamendo.com/v3.0/tracks
    """
    tag = _GENRE_TO_JAMENDO_TAG.get(genre, "chillout")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"jamendo:{tag}".encode()).hexdigest()[:10]
    cache_path = _CACHE_DIR / f"jamendo_{cache_key}.mp3"

    if cache_path.exists() and cache_path.stat().st_size > 10_000:
        return str(cache_path)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                _JAMENDO_API,
                params={
                    "client_id": _jamendo_client_id(),
                    "format": "json",
                    "limit": 20,
                    "tags": tag,
                    "audioformat": "mp32",
                    "include": "musicinfo licenses",
                    # ccsa=1 → Creative Commons ShareAlike (commercial OK)
                    # This ensures tracks are safe for monetized YouTube uploads.
                    "ccsa": 1,
                    "order": "popularity_total",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            # Keep only tracks that:
            #   1. allow audio download (required to cache locally)
            #   2. carry a CC license that permits commercial use
            #      (CC BY or CC BY-SA — identified by absence of "nc" in the URL)
            def _is_commercial(track: dict) -> bool:
                lic = (track.get("license_ccurl") or "").lower()
                if not lic:
                    return False          # unknown license — skip to be safe
                return "nc" not in lic    # nc = NonCommercial → not safe

            downloadable = [
                t for t in results
                if t.get("audiodownload_allowed") is not False
                and t.get("audio")
                and _is_commercial(t)
            ]
            if not downloadable:
                logger.info("Jamendo returned no downloadable tracks", tag=tag)
                return None

            track = downloadable[0]
            audio_url = track.get("audiodownload") or track.get("audio")
            if not audio_url:
                return None

            dl = await client.get(audio_url)
            dl.raise_for_status()
            cache_path.write_bytes(dl.content)

        logger.info(
            "Jamendo music downloaded",
            genre=genre,
            tag=tag,
            track_name=track.get("name"),
            artist=track.get("artist_name"),
            license=track.get("license_ccurl"),
            path=str(cache_path),
        )
        return str(cache_path)
    except Exception as exc:
        logger.warning("Jamendo music fetch failed", genre=genre, tag=tag, error=str(exc))
        return None


def mix_music_under_voice(
    voice_path: str,
    music_path: str,
    output_path: str,
    music_volume_db: float = -18.0,
    fade_in_ms: int = 1000,
    fade_out_ms: int = 1500,
) -> bool:
    """
    Mix background music under a voice audio file using pydub.

    The music is:
    - Looped if shorter than the voice track
    - Volume-adjusted to `music_volume_db` (default -18 dBFS keeps voice dominant)
    - Faded in and out
    - Trimmed to match voice duration

    Returns True on success, False on any failure.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        voice = AudioSegment.from_file(voice_path)
        music = AudioSegment.from_file(music_path)

        music = music + (music_volume_db - music.dBFS)
        music = music.fade_in(fade_in_ms).fade_out(fade_out_ms)

        voice_ms = len(voice)
        if len(music) < voice_ms:
            loops = (voice_ms // len(music)) + 2
            music = music * loops
        music = music[:voice_ms]

        mixed = voice.overlay(music)

        out = Path(output_path)
        mixed.export(str(out), format=out.suffix.lstrip(".") or "mp3")
        logger.info(
            "Background music mixed",
            voice=voice_path,
            music=music_path,
            output=output_path,
            voice_duration_s=round(voice_ms / 1000, 1),
        )
        return True
    except ImportError:
        logger.warning("pydub not available — skipping music mixing")
        return False
    except Exception as exc:
        logger.warning("Music mixing failed", error=str(exc))
        return False


def normalize_audio(input_path: str, output_path: str, target_dbfs: float = -16.0) -> bool:
    """
    Normalize audio levels using pydub so the voice is at `target_dbfs`.

    Returns True on success.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        audio = AudioSegment.from_file(input_path)
        change = target_dbfs - audio.dBFS
        normalized = audio + change
        out = Path(output_path)
        normalized.export(str(out), format=out.suffix.lstrip(".") or "mp3")
        logger.info(
            "Audio normalized",
            input=input_path,
            output=output_path,
            change_db=round(change, 1),
        )
        return True
    except ImportError:
        logger.warning("pydub not available — skipping normalization")
        return False
    except Exception as exc:
        logger.warning("Audio normalization failed", error=str(exc))
        return False