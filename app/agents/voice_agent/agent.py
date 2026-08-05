import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional

from app.agents.voice_agent.models import VoiceAgentOutput, VoiceSettings
from app.agents.voice_agent.prompts import (
    VOICE_PREP_SYSTEM_PROMPT,
    build_voice_prep_prompt,
)
from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging import get_logger
from app.database.models.script import Script
from app.llm_providers.base import BaseLLMProvider

logger = get_logger(__name__)


class VoiceAgent:
    """
    Voice Generation Agent.

    Pipeline:
      1. LLM pre-processes the script (remove markdown, expand abbreviations)
      2. Kokoro / gTTS / pyttsx3 synthesises the cleaned text to MP3
      3. File is saved to local storage
      4. Returns VoiceAgentOutput with path and metadata
    """

    AGENT_NAME = "VoiceAgent"
    WORDS_PER_MINUTE_LONG = 175
    WORDS_PER_MINUTE_SHORT = 158

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script: Script,
        voice_settings: Optional[VoiceSettings] = None,
    ) -> VoiceAgentOutput:
        if voice_settings is None:
            voice_settings = VoiceSettings()

        logger.info(
            "VoiceAgent starting",
            script_id=str(script.id),
            provider=voice_settings.provider,
        )
        start = time.monotonic()

        try:
            output = await self._process(
                script_id=str(script.id),
                script_content=script.content,
                script_type=str(script.script_type),
                voice_settings=voice_settings,
            )
        except Exception as exc:
            logger.error("VoiceAgent failed", script_id=str(script.id), error=str(exc))
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

        elapsed = time.monotonic() - start
        logger.info(
            "VoiceAgent complete",
            script_id=str(script.id),
            duration=output.duration_seconds,
            provider=output.provider_used,
            elapsed=round(elapsed, 2),
        )
        return output

    async def synthesise(
        self,
        script_content: str,
        script_id: str,
        script_type: str = "long",
        voice_settings: Optional[VoiceSettings] = None,
    ) -> VoiceAgentOutput:
        if voice_settings is None:
            voice_settings = VoiceSettings()
        try:
            return await self._process(
                script_id=script_id,
                script_content=script_content,
                script_type=script_type,
                voice_settings=voice_settings,
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError(self.AGENT_NAME, str(exc)) from exc

    async def _process(
        self,
        script_id: str,
        script_content: str,
        script_type: str,
        voice_settings: VoiceSettings,
    ) -> VoiceAgentOutput:
        try:
            script_data = json.loads(script_content)
            body_text = script_data.get("body", script_content)
        except Exception:
            body_text = script_content

        cleaned = await self._clean_script(body_text, voice_settings.language)

        word_count = len(cleaned.split())
        wpm = self.WORDS_PER_MINUTE_SHORT if script_type == "short" else self.WORDS_PER_MINUTE_LONG
        duration_seconds = round((word_count / max(wpm, 1)) * 60, 1)

        audio_dir = Path(settings.storage_local_path) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        file_path = audio_dir / f"{script_id}.mp3"

        provider_used = await self._synthesise_audio(
            text=cleaned,
            file_path=file_path,
            voice_settings=voice_settings,
        )

        file_size = file_path.stat().st_size if file_path.exists() else 0

        measured_duration = self._measure_audio_duration(file_path)
        if measured_duration is not None:
            if abs(measured_duration - duration_seconds) > 2.0:
                logger.warning(
                    "Voice duration estimate was significantly off — using "
                    "measured value instead.",
                    estimated_seconds=duration_seconds,
                    measured_seconds=measured_duration,
                    script_id=script_id,
                )
            duration_seconds = measured_duration

        return VoiceAgentOutput(
            audio_file_path=str(file_path),
            duration_seconds=duration_seconds,
            word_count=word_count,
            provider_used=provider_used,
            language=voice_settings.language,
            file_size_bytes=file_size,
            success=True,
        )

    @staticmethod
    def _measure_audio_duration(file_path: Path) -> Optional[float]:
        if not file_path.exists():
            return None
        try:
            from pydub import AudioSegment  # type: ignore

            audio = AudioSegment.from_file(str(file_path))
            return round(len(audio) / 1000, 1)
        except Exception as exc:
            logger.warning(
                "Could not measure real audio duration — falling back to estimate",
                error=str(exc),
                file_path=str(file_path),
            )
            return None

    async def _clean_script(self, content: str, language: str) -> str:
        original_word_count = len(content.split())
        try:
            prompt = build_voice_prep_prompt(script_content=content, language=language)
            cleaned = await self._llm.generate_text(
                prompt=prompt,
                system=VOICE_PREP_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=4096,
            )
            cleaned = re.sub(r"\[(long-pause|pause)\]", " ", cleaned)
            cleaned = cleaned.strip()

            if len(cleaned) < 20:
                logger.warning("Voice cleanup returned suspiciously short output — using basic clean")
                return self._basic_clean(content)

            cleaned_word_count = len(cleaned.split())
            if original_word_count > 0 and cleaned_word_count > original_word_count * 1.3:
                logger.warning(
                    "Voice cleanup output far longer than input — likely LLM "
                    "hallucination, discarding and using basic clean instead.",
                    original_words=original_word_count,
                    cleaned_words=cleaned_word_count,
                )
                return self._basic_clean(content)

            return self._strip_instruction_leaks(cleaned)
        except Exception as exc:
            logger.warning("Script cleanup via LLM failed — using basic clean", error=str(exc))
            return self._basic_clean(content)

    _INSTRUCTION_LEAK_PATTERNS: list[str] = [
        r"remove emoji",
        r"remove hashtag",
        r"spoken text rule",
        r"critical.{0,20}rule",
        r"section heading",
        r"ad after pay",
        r"link in the description",
        r"replace with",
        r"remove uile",
        r"text.to.speech engine",
        r"punchy.*title",
        r"optimized title",
        r"under \d+ char",
        r"tts wright",
        r"\bETC\b\.?$",
    ]

    def _basic_clean(self, content: str) -> str:
        text = re.sub(r"#{1,6}\s*", "", content)
        text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
        text = re.sub(r"https?://\S+|www\.\S+", "", text)
        text = re.sub(r"[#@]", "", text)
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\s{2,}", " ", text)
        return self._strip_instruction_leaks(text.strip())

    def _strip_instruction_leaks(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept = []
        pattern = re.compile(
            "|".join(self._INSTRUCTION_LEAK_PATTERNS),
            re.IGNORECASE,
        )
        for sentence in sentences:
            if pattern.search(sentence):
                logger.debug(
                    "Dropped instruction-leak sentence before TTS",
                    sentence=sentence[:80],
                )
            else:
                kept.append(sentence)
        result = " ".join(kept).strip()
        return re.sub(r"  +", " ", result)

    async def _synthesise_audio(
        self,
        text: str,
        file_path: Path,
        voice_settings: VoiceSettings,
    ) -> str:
        from app.core.config import settings as cfg

        provider = voice_settings.provider.lower()
        gender = getattr(voice_settings, "gender", cfg.voice_gender)

        if provider in ("auto", "kokoro"):
            result = await self._kokoro_synthesise(
                text, str(file_path), gender, voice_settings.speed
            )
            if result:
                return "kokoro"

        if provider in ("auto", "gtts"):
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._gtts_synthesise, text, str(file_path), voice_settings.language
            )
            if result:
                return "gtts"

        if provider in ("auto", "pyttsx3"):
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._pyttsx3_synthesise, text, str(file_path)
            )
            if result:
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
        import time as _time

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
                if attempt < 3:
                    logger.warning(
                        "gTTS attempt failed — retrying",
                        attempt=attempt,
                        error=str(exc),
                    )
                    _time.sleep(5)
        logger.warning("gTTS synthesis failed after 3 attempts", error=str(last_exc))
        return False

    def _pyttsx3_synthesise(self, text: str, file_path: str) -> bool:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.save_to_file(text, file_path)
            engine.runAndWait()
            return Path(file_path).exists() and Path(file_path).stat().st_size > 0
        except ImportError:
            logger.debug("pyttsx3 not installed — skipping")
            return False
        except Exception as exc:
            logger.warning("pyttsx3 synthesis failed", error=str(exc))
            return False

    def _mock_synthesise(self, file_path: Path) -> None:
        mp3_header = (
            b"ID3\x03\x00\x00\x00\x00\x00\x00"
            b"\xff\xfb\x90\x00"
            b"\x00" * 413
        )
        file_path.write_bytes(mp3_header)
        logger.debug("Mock audio written", path=str(file_path))
