"""Background music fetch + mix under voice (Jamendo / local)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Soft-duck: always keep bed a few dB quieter than the configured bed level
_SOFT_DUCK_DB = -4.0
# Safety floor: music must stay at least this many dB under average voice
_MIN_VOICE_HEADROOM_DB = 18.0


def genre_for_category(category: str) -> str:
    cat = (category or "technology").lower()
    mapping = {
        "technology": "electronic",
        "tech": "electronic",
        "science": "ambient",
        "finance": "corporate",
        "health": "ambient",
        "education": "piano",
        "gaming": "electronic",
        "news": "corporate",
    }
    for key, genre in mapping.items():
        if key in cat:
            return genre
    return "electronic"


def _music_cache_dir() -> Path:
    p = Path(settings.storage_local_path) / "music"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _local_track(genre: str) -> Optional[str]:
    """Prefer a local file under storage/music if present."""
    base = _music_cache_dir()
    for name in (f"{genre}.mp3", f"{genre}.wav", "default.mp3", "bed.mp3"):
        candidate = base / name
        if candidate.exists() and candidate.stat().st_size > 1000:
            return str(candidate)
    # Any mp3 in folder
    for f in sorted(base.glob("*.mp3")):
        if f.stat().st_size > 1000:
            return str(f)
    return None


async def fetch_track(genre: str = "electronic") -> Optional[str]:
    """
    Return path to a background music file.
    Order: local cache → Jamendo (if API key) → None.
    """
    local = _local_track(genre)
    if local:
        return local

    client_id = (getattr(settings, "jamendo_client_id", None) or "").strip()
    if not client_id:
        logger.info("No local music and no Jamendo client id — skip music")
        return None

    cache = _music_cache_dir() / f"jamendo_{genre}.mp3"
    if cache.exists() and cache.stat().st_size > 1000:
        return str(cache)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://api.jamendo.com/v3.0/tracks/",
                params={
                    "client_id": client_id,
                    "format": "json",
                    "limit": 5,
                    "audioformat": "mp32",
                    "include": "musicinfo",
                    "groupby": "artist_id",
                    "order": "popularity_total",
                    "tags": genre,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if not results:
                return None
            audio_url = results[0].get("audio")
            if not audio_url:
                return None
            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()
            cache.write_bytes(audio_resp.content)
            logger.info("Jamendo track cached", genre=genre, path=str(cache))
            return str(cache)
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
    - Volume-adjusted to `music_volume_db` plus soft-duck (-4 dB)
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
        target_bed_db = float(music_volume_db) + _SOFT_DUCK_DB

        if music.dBFS != float("-inf"):
            music = music + (target_bed_db - music.dBFS)

        # Safety: keep music well under voice average
        if voice.dBFS != float("-inf") and music.dBFS != float("-inf"):
            max_music_dbfs = voice.dBFS - _MIN_VOICE_HEADROOM_DB
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
            soft_duck_db=_SOFT_DUCK_DB,
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
    """
    try:
        from pydub import AudioSegment  # type: ignore

        audio = AudioSegment.from_file(input_path)
        if audio.dBFS == float("-inf"):
            return False
        change = target_dbfs - audio.dBFS
        audio = audio + change
        out = Path(output_path)
        audio.export(str(out), format=out.suffix.lstrip(".") or "mp3")
        return True
    except Exception as exc:
        logger.warning("Audio normalize failed", error=str(exc))
        return False
