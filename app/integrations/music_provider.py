"""Background music: local files + optional Jamendo, mix under voice."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Soft-duck: bed quieter than configured level; window-duck under speech.

_GENRE_MAP = {
    "tech": "electronic",
    "technology": "electronic",
    "ai": "electronic",
    "science": "ambient",
    "space": "ambient",
    "finance": "corporate",
    "business": "corporate",
    "health": "chill",
    "fitness": "upbeat",
    "news": "corporate",
    "default": "ambient",
}


def _jamendo_client_id() -> str:
    return (getattr(settings, "jamendo_client_id", None) or "").strip()


def is_configured() -> bool:
    local = Path(getattr(settings, "background_music_dir", "storage/music") or "storage/music")
    return local.is_dir() or bool(_jamendo_client_id())


def genre_for_category(category: str) -> str:
    key = (category or "").lower().strip()
    return _GENRE_MAP.get(key, _GENRE_MAP["default"])


async def fetch_track(
    category: str = "default",
    duration_hint_seconds: float = 60.0,
) -> Optional[str]:
    """Return a local path to a background music track, or None."""
    genre = genre_for_category(category)
    local = _find_local_track(genre)
    if local:
        return local
    if _jamendo_client_id():
        return await _fetch_from_jamendo(genre, duration_hint_seconds)
    return None


def _find_local_track(genre: str) -> Optional[str]:
    base = Path(getattr(settings, "background_music_dir", "storage/music") or "storage/music")
    if not base.is_dir():
        return None
    for pattern in (f"*{genre}*.mp3", f"*{genre}*.wav", "*.mp3", "*.wav"):
        hits = sorted(base.glob(pattern))
        if hits:
            return str(hits[0])
    return None


async def _fetch_from_jamendo(genre: str, duration_hint_seconds: float) -> Optional[str]:
    client_id = _jamendo_client_id()
    if not client_id:
        return None
    cache_dir = Path(settings.storage_local_path) / "music" / "jamendo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"{genre}:{int(duration_hint_seconds)}".encode()).hexdigest()[:12]
    cache_path = cache_dir / f"{genre}_{cache_key}.mp3"
    if cache_path.is_file() and cache_path.stat().st_size > 1000:
        return str(cache_path)
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
                    "tags": genre,
                },
            )
            resp.raise_for_status()
            results = (resp.json().get("results") or [])
            if not results:
                return None
            audio = results[0].get("audio")
            if not audio:
                return None
            audio_resp = await client.get(audio)
            audio_resp.raise_for_status()
            cache_path.write_bytes(audio_resp.content)
            logger.info("Jamendo track cached", path=str(cache_path), genre=genre)
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
    - Window-duck: further −8 dB under active speech (100 ms windows)
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

        # Window-duck: extra cut under speech; mild floor in gaps (pydub-only)
        try:
            window_ms = 100
            duck_db = -8.0
            floor_db = -2.0
            voice_thresh = (
                voice.dBFS - 8.0 if voice.dBFS != float("-inf") else -30.0
            )
            music = music.set_frame_rate(voice.frame_rate).set_channels(voice.channels)
            ducked = AudioSegment.silent(duration=0, frame_rate=music.frame_rate)
            ducked = ducked.set_channels(music.channels).set_sample_width(
                music.sample_width
            )
            for start in range(0, voice_ms, window_ms):
                end = min(start + window_ms, voice_ms)
                v_slice = voice[start:end]
                m_slice = music[start:end]
                if len(m_slice) == 0:
                    break
                if v_slice.dBFS != float("-inf") and v_slice.dBFS > voice_thresh:
                    m_slice = m_slice + duck_db
                else:
                    m_slice = m_slice + floor_db
                ducked += m_slice
            if len(ducked) >= int(voice_ms * 0.9):
                music = ducked[:voice_ms]
                logger.info(
                    "Music window-duck applied",
                    window_ms=window_ms,
                    duck_db=duck_db,
                    floor_db=floor_db,
                )
        except Exception as duck_exc:
            logger.debug(
                "Window duck skipped — using constant soft-duck",
                error=str(duck_exc),
            )

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
            music_dbfs_after=round(music.dBFS, 1)
            if music.dBFS != float("-inf")
            else None,
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
        if audio.dBFS != float("-inf"):
            audio = audio + (target_dbfs - audio.dBFS)
        out = Path(output_path)
        audio.export(str(out), format=out.suffix.lstrip(".") or "mp3")
        return True
    except Exception as exc:
        logger.warning("Audio normalize failed", error=str(exc))
        return False
