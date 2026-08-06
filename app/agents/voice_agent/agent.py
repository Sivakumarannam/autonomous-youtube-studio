"""Voice synthesis agent — Kokoro primary, gTTS / pyttsx3 fallbacks."""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.agents.voice_agent.models import VoiceAgentOutput, VoiceSettings
from app.agents.voice_agent.prompts import (
    VOICE_CLEAN_SYSTEM,
    build_voice_clean_prompt,
)
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class VoiceAgent:
    """
    Synthesises spoken audio for a script.

    Flow:
      1. Optional LLM clean of script text for speech
      2. Kokoro / gTTS / pyttsx3 synthesises the cleaned text to MP3
      3. Returns path + metadata
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self._llm = llm_provider

    async def synthesise(
        self,
        script: Script,
        voice_settings: Optional[VoiceSettings] = None,
    ) -> VoiceAgentOutput:
        voice_settings = voice_settings or VoiceSettings()
        start = time.monotonic()

        script_content = script.content or ""
        if not script_content.strip():
            # try structured fields
            try:
                script_data = json.loads(script_content) if script_content else {}
            except Exception:
                script_data = {}
            script_content = (
                script_data.get("full_script")
                or getattr(script, "full_script", None)
                or script.title
                or ""
            )

        text = await self._prepare_spoken_text(script_content)
        if not text.strip():
            raise AgentError("No speakable text for voice synthesis")

        out_dir = Path(settings.storage_local_path) / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{script.id}.mp3"

        provider_used = await self._synthesise_audio(
            text=text,
            file_path=file_path,
            voice_settings=voice_settings,
        )

        duration_s = 0.0
        try:
            from pydub import AudioSegment  # type: ignore

            duration_s = len(AudioSegment.from_file(str(file_path))) / 1000.0
        except Exception:
            duration_s = max(1.0, len(text.split()) * 0.35)

        return VoiceAgentOutput(
            success=True,
            audio_path=str(file_path),
            transcript=text,
            duration_seconds=duration_s,
            provider=provider_used,
            execution_time=time.monotonic() - start,
        )

    async def _prepare_spoken_text(self, script_content: str) -> str:
        text = script_content.strip()
        # Strip markdown / stage directions lightly
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"#+", "", text)
        if self._llm is None:
            return text
        try:
            prompt = build_voice_clean_prompt(text)
            cleaned = await self._llm.generate(
                system=VOICE_CLEAN_SYSTEM,
                prompt=prompt,
                max_tokens=2000,
            )
            if cleaned and len(cleaned.strip()) > 20:
                return cleaned.strip()
        except Exception as exc:
            logger.debug("Voice clean LLM skipped", error=str(exc))
        return text

    async def _synthesise_audio(
        self,
        text: str,
        file_path: Path,
        voice_settings: VoiceSettings,
    ) -> str:
        provider = (getattr(settings, "tts_provider", None) or "auto").lower()
        gender = getattr(voice_settings, "gender", None) or getattr(
            settings, "default_voice_gender", "female"
        )
        speed = float(getattr(voice_settings, "speed", 1.0) or 1.0)

        if provider in ("auto", "kokoro"):
            result = await self._kokoro_synthesise(
                text=text, file_path=str(file_path), gender=gender, speed=speed
            )
            if result:
                return "kokoro"

        if provider in ("auto", "gtts"):
            ok = await asyncio.get_running_loop().run_in_executor(
                None, self._gtts_synthesise, text, str(file_path), voice_settings.language
            )
            if ok:
                return "gtts"

        if provider in ("auto", "pyttsx3"):
            ok = await asyncio.get_running_loop().run_in_executor(
                None, self._pyttsx3_synthesise, text, str(file_path)
            )
            if ok:
                return "pyttsx3"

        self._mock_synthesise(file_path)
        return "mock"

    async def _kokoro_synthesise(
        self,
        text: str,
        file_path: str,
        gender: str = "female",
        speed: float = 1.0,
    ) -> bool:
        """Kokoro ONNX synthesis with optional per-sentence timings.json for low-RAM sync."""
        try:
            import json
            import shutil
            import subprocess

            from app.integrations.kokoro_tts import (
                is_available,
                pick_voice,
                split_spoken_sentences,
                synthesise,
                synthesise_sentences,
            )

            if not is_available():
                return False
            voice = pick_voice(gender)
            wav_path = file_path.replace(".mp3", "_kokoro.wav")
            timings_path = str(Path(file_path).with_suffix(".timings.json"))

            sentences = split_spoken_sentences(text)
            timings: list = []
            if len(sentences) >= 1:
                timings = await synthesise_sentences(
                    sentences=sentences,
                    output_path=wav_path,
                    voice=voice,
                    speed=speed,
                )
            if not timings:
                ok = await synthesise(
                    text=text, output_path=wav_path, voice=voice, speed=speed
                )
                if not ok:
                    return False
                # Fallback: estimate spans so LOW_RAM can still align scenes
                try:
                    from pydub import AudioSegment  # type: ignore

                    dur = len(AudioSegment.from_file(wav_path)) / 1000.0
                except Exception:
                    dur = max(2.0, len(text.split()) * 0.35)
                rows = sentences or [text]
                n = max(1, len(rows))
                payload = {
                    "sentences": [
                        {
                            "text": s,
                            "start": float(i * (dur / n)),
                            "end": float((i + 1) * (dur / n)),
                        }
                        for i, s in enumerate(rows)
                    ]
                }
                Path(timings_path).write_text(json.dumps(payload), encoding="utf-8")
                logger.info(
                    "Kokoro timings estimated (single-pass fallback)",
                    path=timings_path,
                    duration_s=round(dur, 2),
                    count=n,
                )
            else:
                payload = {
                    "sentences": [
                        {"text": s, "start": float(a), "end": float(b)}
                        for s, (a, b) in zip(sentences, timings)
                    ]
                }
                Path(timings_path).write_text(json.dumps(payload), encoding="utf-8")
                logger.info(
                    "Kokoro sentence timings saved",
                    path=timings_path,
                    count=len(timings),
                )

            try:
                ffmpeg_result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        wav_path,
                        "-codec:a",
                        "libmp3lame",
                        "-b:a",
                        "128k",
                        file_path,
                    ],
                    capture_output=True,
                    timeout=300,
                )
                if ffmpeg_result.returncode == 0:
                    logger.info("Kokoro TTS → MP3 conversion complete", path=file_path)
                else:
                    logger.warning(
                        "Kokoro ffmpeg conversion failed, using WAV",
                        returncode=ffmpeg_result.returncode,
                        stderr=ffmpeg_result.stderr.decode()[:200],
                    )
                    if Path(wav_path).is_file():
                        shutil.move(wav_path, file_path)
                return True
            except Exception as conv_exc:
                logger.warning("Kokoro WAV→MP3 conversion failed", error=str(conv_exc))
                if Path(wav_path).is_file():
                    shutil.move(wav_path, file_path)
                return True
            finally:
                # Line L: never leave large Kokoro WAV temps on free-tier disk
                try:
                    p = Path(wav_path)
                    if p.is_file():
                        p.unlink(missing_ok=True)
                        logger.info("Cleaned Kokoro temp WAV", path=wav_path)
                    parent = Path(file_path).parent
                    stem = Path(file_path).stem
                    for leftover in parent.glob(f"{stem}*_kokoro.wav"):
                        leftover.unlink(missing_ok=True)
                except Exception as clean_exc:
                    logger.debug("Kokoro temp cleanup skipped", error=str(clean_exc))
        except Exception as exc:
            logger.debug("Kokoro synthesis skipped", error=str(exc))
            return False

    def _gtts_synthesise(self, text: str, file_path: str, language: str) -> bool:
        try:
            from gtts import gTTS
        except ImportError:
            logger.debug("gTTS not installed — skipping")
            return False

        lang = language.split("-")[0][:2]
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                tts = gTTS(text=text, lang=lang, slow=False)
                tts.save(file_path)
                if attempt > 1:
                    logger.info("gTTS succeeded after retry", attempt=attempt)
                return True
            except Exception as exc:
                last_exc = exc
                time.sleep(0.5 * attempt)
        logger.warning("gTTS failed", error=str(last_exc))
        return False

    def _pyttsx3_synthesise(self, text: str, file_path: str) -> bool:
        try:
            import pyttsx3  # type: ignore
        except ImportError:
            return False
        try:
            engine = pyttsx3.init()
            engine.save_to_file(text, file_path)
            engine.runAndWait()
            return Path(file_path).is_file()
        except Exception as exc:
            logger.debug("pyttsx3 failed", error=str(exc))
            return False

    def _mock_synthesise(self, file_path: Path) -> None:
        """Write a tiny silent-ish placeholder so the pipeline can continue in tests."""
        file_path.write_bytes(b"")
        logger.warning("Mock voice file written (no TTS provider available)", path=str(file_path))
