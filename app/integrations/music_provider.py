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
The music is mixed under the voice at -22 dBFS by default (voice stays dominant),
with an extra -4 dB soft-duck and 18 dB headroom under average voice level.
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
}


def _jamendo_client_id() -> str:
    return (
        os.environ.get("JAMENDO_CLIENT_ID", "")
        or os.environ.get("JAMENDO_API_KEY", "")
        or ""
    ).strip()


def is_configured() -> bool:
    """True if local music or Jamendo client id is available."""
    if _LOCAL_MUSIC_DIR.exists() and any(_LOCAL_MUSIC_DIR.glob("*.mp3")):
        return True
    return bool(_jamendo_client_id())


def genre_for_category(category: str) -> str:
    key = (category or "").strip().lower()
    return _CATEGORY_GENRE.get(key, "background")


async def fetch_track(
    genre: str = "background",
    duration_hint_seconds: float = 60.0,
) -> Optional[str]:
    """
    Return a local path to a music file suitable for mixing under voice.
    Tries local files first, then Jamendo.
    """
    local = _find_local_track(genre)
    if local:
        return local
    return await _fetch_from_jamendo(genre, duration_hint_seconds)


def _find_local_track(genre: str) -> Optional[str]:
    if not _LOCAL_MUSIC_DIR.exists():
        return None
    preferred = list(_LOCAL_MUSIC_DIR.glob(f"*{genre}*.mp3")) + list(
        _LOCAL_MUSIC_DIR.glob("*.mp3")
    )
    for p in preferred:
        if p.is_file() and p.stat().st_size > 1000:
            return str(p)
    return None


async def _fetch_from_jamendo(genre: str, duration_hint_seconds: float) -> Optional[str]:
    client_id = _jamendo_client_id()
    if not client_id:
        logger.debug("Jamendo client id not set — skip remote music fetch")
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"{genre}:{int(duration_hint_seconds)}".encode()).hexdigest()[:12]
    cache_path = _CACHE_DIR / f"jamendo_{cache_key}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return str(cache_path)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _JAMENDO_API,
                params={
                    "client_id": client_id,
                    "format": "json",
                    "limit": 5,
                    "audioformat": "mp32",
                    "include": "musicinfo",
                    "order": "popularity_total",
                    "tags": genre,
                    "durationbetween": f"30_{max(60, int(duration_hint_seconds) + 30)}",
                },
            )
            if resp.status_code != 200:
                logger.warning("Jamendo HTTP %s", resp.status_code)
                return None
            results = (resp.json() or {}).get("results") or []
            if not results:
                return None
            audio_url = results[0].get("audio")
            if not audio_url:
                return None
            audio_resp = await client.get(audio_url)
            if audio_resp.status_code != 200:
                return None
            cache_path.write_bytes(audio_resp.content)
            logger.info("Jamendo track cached", genre=genre, path=str(cache_path))
            return str(cache_path)
    except Exception as exc:
        logger.warning("Jamendo fetch failed", error=str(exc))
        return None


def mix_music_under_voice(
    voice_path: str,
    music_path: str,
    output_path: str,
    music_volume_db: float = -22.0,
    fade_in_ms: int = 1000,
    fade_out_ms: int = 1500,
) -> bool:
    """
    Mix background music under a voice audio file using pydub.

    The music is:
    - Looped if shorter than the voice track
    - Volume-adjusted to `music_volume_db` minus 4 dB soft-duck (default -22 → -26)
    - Extra-capped so music stays at least ~18 dB under the voice average
    - Faded in and out
    - Trimmed to match voice duration

    Returns True on success, False on any failure.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        voice = AudioSegment.from_file(voice_path)
        music = AudioSegment.from_file(music_path)

        # Soft-duck: bed quieter than configured level so speech stays clear
        target_bed_db = float(music_volume_db) - 4.0

        if music.dBFS != float("-inf"):
            music = music + (target_bed_db - music.dBFS)

        # Safety: keep music at least ~18 dB under voice average
        if voice.dBFS != float("-inf") and music.dBFS != float("-inf"):
            max_music_dbfs = voice.dBFS - 18.0
            if music.dBFS > max_music_dbfs:
                music = music + (max_music_dbfs - music.dBFS)

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
            music_volume_db=music_volume_db,
            effective_bed_db=target_bed_db,
            voice_dbfs=round(voice.dBFS, 1) if voice.dBFS != float("-inf") else None,
            music_dbfs_after=round(music.dBFS, 1) if music.dBFS != float("-inf") else None,
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
