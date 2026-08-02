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
      2. gTTS (or pyttsx3 fallback) synthesises the cleaned text to MP3
      3. File is saved to local storage
      4. Returns VoiceAgentOutput with path and metadata

    Operates at zero cost using gTTS (Google Text-to-Speech free tier).
    Falls back to pyttsx3 (fully offline) if gTTS is unavailable.
    Falls back to a mock silent MP3 in test environments.
    """

    AGENT_NAME = "VoiceAgent"
    WORDS_PER_MINUTE_LONG = 175   # gTTS measured on Replit (~175 wpm)
    WORDS_PER_MINUTE_SHORT = 158  # gTTS measured on Replit (~158 wpm for shorts)

    def __init__(self, llm_provider: BaseLLMProvider) -> None:
        self._llm = llm_provider

    async def run(
        self,
        script: Script,
        voice_settings: Optional[VoiceSettings] = None,
    ) -> VoiceAgentOutput:
        """Generate audio for a Script ORM object."""
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
        """Synthesise raw content without a Script ORM object."""
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

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    async def _process(
        self,
        script_id: str,
        script_content: str,
        script_type: str,
        voice_settings: VoiceSettings,
    ) -> VoiceAgentOutput:
        # Step 1 — LLM script cleanup (force clean only the body part)
        # Assuming script_content might be JSON, we extract just the body
        try:
            script_data = json.loads(script_content)
            body_text = script_data.get("body", script_content)
        except:
            body_text = script_content
            
        cleaned = await self._clean_script(body_text, voice_settings.language)

        # Step 2 — Calculate word count and estimated duration
        word_count = len(cleaned.split())
        wpm = self.WORDS_PER_MINUTE_SHORT if script_type == "short" else self.WORDS_PER_MINUTE_LONG
        duration_seconds = round((word_count / max(wpm, 1)) * 60, 1)

        # Step 3 — Synthesise audio
        audio_dir = Path(settings.storage_local_path) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        file_path = audio_dir / f"{script_id}.mp3"

        provider_used = await self._synthesise_audio(
            text=cleaned,
            file_path=file_path,
            voice_settings=voice_settings,
        )

        file_size = file_path.stat().st_size if file_path.exists() else 0

        # Measure the REAL duration from the actual generated file rather
        # than trusting the pre-generation word-count/wpm estimate above.
        # That estimate can be significantly wrong — the WPM constants were
        # calibrated on a different environment (see class docstring) — and
        # everything downstream (Whisper alignment, scene pacing, the final
        # video/voice trim in the renderer) is more accurate when driven by
        # the real file length. Falls back to the estimate only if the file
        # is missing or can't be read (e.g. mock/test audio).
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
        """Real duration of the generated audio file, in seconds. Returns
        None (never raises) if the file is missing or can't be decoded —
        callers fall back to the word-count estimate in that case."""
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
        """Use the LLM to clean the script for TTS, then strip pause markers.

        After LLM cleaning, always run `_strip_instruction_leaks` as a hard
        second pass — small local models sometimes echo system-prompt text
        (e.g. "Remove emojis entirely", "Hook, Introduction") verbatim into
        the script body, and gTTS will read those words aloud.

        Also enforces a length-sanity check: this is meant to be a purely
        mechanical cleanup pass (strip markdown, expand abbreviations,
        remove emojis) that should never meaningfully change the word
        count. Small local models have been observed ignoring this and
        generating unrelated new content instead of editing the input
        (e.g. turning a 50-word script into 127 words of hallucinated
        text like "stringed meat" and "King changed everything" that
        never appeared in the original). If the cleaned output is
        significantly longer than the input, that is strong evidence of
        hallucination rather than legitimate cleanup (abbreviation
        expansion adds a few words at most, never 2x+), so we discard the
        LLM output entirely and fall back to the deterministic regex
        cleaner instead.
        """
        original_word_count = len(content.split())
        try:
            prompt = build_voice_prep_prompt(script_content=content, language=language)
            cleaned = await self._llm.generate_text(
                prompt=prompt,
                system=VOICE_PREP_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=4096,
            )
            # Remove SSML-like pause markers — gTTS ignores them
            cleaned = re.sub(r"\[(long-pause|pause)\]", " ", cleaned)
            cleaned = cleaned.strip()

            # Fall back to original if LLM returned something too short
            if len(cleaned) < 20:
                logger.warning("Voice cleanup returned suspiciously short output — using basic clean")
                return self._basic_clean(content)

            # Fall back if the LLM appears to have hallucinated new content
            # instead of just cleaning. Legitimate cleanup (abbreviation
            # expansion, "K8s" -> "Kubernetes") adds at most a modest number
            # of words; anything past 1.3x the original is treated as
            # unreliable rather than trusted.
            cleaned_word_count = len(cleaned.split())
            if original_word_count > 0 and cleaned_word_count > original_word_count * 1.3:
                logger.warning(
                    "Voice cleanup output far longer than input — likely LLM "
                    "hallucination, discarding and using basic clean instead.",
                    original_words=original_word_count,
                    cleaned_words=cleaned_word_count,
                )
                return self._basic_clean(content)

            # Hard second pass: strip any instruction-leak sentences the LLM
            # may have included in its output.
            return self._strip_instruction_leaks(cleaned)
        except Exception as exc:
            logger.warning("Script cleanup via LLM failed — using basic clean", error=str(exc))
            return self._basic_clean(content)

    # Phrases that indicate the LLM leaked system-prompt instructions into the
    # script body.  Any sentence containing one of these (case-insensitive) is
    # dropped before TTS synthesis.
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
        """Basic regex cleanup without LLM."""
        text = re.sub(r"#{1,6}\s*", "", content)   # headings
        text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)  # bold/italic
        # Drop URLs entirely — do NOT replace with a spoken phrase that gTTS will read
        text = re.sub(r"https?://\S+|www\.\S+", "", text)
        text = re.sub(r"[#@]", "", text)
        text = re.sub(r"\[.*?\]", "", text)         # markdown links
        text = re.sub(r"\s{2,}", " ", text)
        return self._strip_instruction_leaks(text.strip())

    def _strip_instruction_leaks(self, text: str) -> str:
        """Remove sentences where the LLM accidentally echoed system-prompt instructions.

        Splits on sentence boundaries, discards any sentence matching a known
        instruction-leak pattern, then re-joins.  This is the last line of
        defence before the text reaches gTTS.
        """
        # Split on sentence-ending punctuation
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
        # Collapse any double-spaces left behind
        return re.sub(r"  +", " ", result)

    async def _synthesise_audio(
        self,
        text: str,
        file_path: Path,
        voice_settings: VoiceSettings,
    ) -> str:
        """
        TTS synthesis chain (priority order):
          1. Kokoro ONNX (high-quality neural, offline) — auto/kokoro
          2. gTTS (Google, requires internet)            — auto/gtts
          3. pyttsx3 (offline, robotic)                  — auto/pyttsx3
          4. Mock (silent placeholder)                   — last resort
        """
        from app.core.config import settings as cfg

        provider = voice_settings.provider.lower()
        gender = getattr(voice_settings, "gender", cfg.voice_gender)

        # ------------------------------------------------------------------
        # 1. Kokoro TTS — highest quality, fully offline
        # ------------------------------------------------------------------
        if provider in ("auto", "kokoro"):
            result = await self._kokoro_synthesise(text, str(file_path), gender, voice_settings.speed)
            if result:
                return "kokoro"

        # ------------------------------------------------------------------
        # 2. gTTS — free Google TTS (requires internet connection)
        # ------------------------------------------------------------------
        if provider in ("auto", "gtts"):
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._gtts_synthesise, text, str(file_path), voice_settings.language
            )
            if result:
                return "gtts"

        # ------------------------------------------------------------------
        # 3. pyttsx3 — fully offline, robotic quality
        # ------------------------------------------------------------------
        if provider in ("auto", "pyttsx3"):
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._pyttsx3_synthesise, text, str(file_path)
            )
            if result:
                return "pyttsx3"

        # ------------------------------------------------------------------
        # 4. Mock — silent placeholder (test environments)
        # ------------------------------------------------------------------
        self._mock_synthesise(file_path)
        return "mock"

    async def _kokoro_synthesise(
        self,
        text: str,
        file_path: str,
        gender: str = "female",
        speed: float = 1.0,
    ) -> bool:
        """Attempt Kokoro ONNX synthesis; return True on success."""
        try:
            from app.integrations.kokoro_tts import synthesise, pick_voice, is_available
            if not is_available():
                return False
            voice = pick_voice(gender)
            # Kokoro outputs WAV; save to a temp file then convert to MP3
            import asyncio
            import tempfile
            from pathlib import Path

            wav_path = file_path.replace(".mp3", "_kokoro.wav")
            ok = await synthesise(text=text, output_path=wav_path, voice=voice, speed=speed)
            if not ok:
                return False
            # Convert WAV → MP3 using ffmpeg (always available)
            try:
                import subprocess
                ffmpeg_result = subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame",
                     "-b:a", "128k", file_path],
                    capture_output=True, timeout=300,
                )
                if ffmpeg_result.returncode == 0:
                    Path(wav_path).unlink(missing_ok=True)
                    logger.info("Kokoro TTS → MP3 conversion complete", path=file_path)
                else:
                    # ffmpeg failed — use WAV directly
                    logger.warning("Kokoro ffmpeg conversion failed, using WAV",
                                   returncode=ffmpeg_result.returncode,
                                   stderr=ffmpeg_result.stderr.decode()[:200])
                    import shutil
                    shutil.move(wav_path, file_path)
                return True
            except Exception as conv_exc:
                logger.warning("Kokoro WAV→MP3 conversion failed", error=str(conv_exc))
                import shutil
                shutil.move(wav_path, file_path)
                return True
        except Exception as exc:
            logger.debug("Kokoro synthesis skipped", error=str(exc))
            return False

    def _gtts_synthesise(self, text: str, file_path: str, language: str) -> bool:
        """gTTS with 3-attempt retry + 5 s backoff for transient network errors."""
        import time as _time
        try:
            from gtts import gTTS
        except ImportError:
            logger.debug("gTTS not installed — skipping")
            return False

        lang = language.split("-")[0][:2]  # "en-US" → "en"
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
        """Write a minimal valid MP3 header as a placeholder."""
        # ID3v2 header + minimal MP3 frame
        mp3_header = (
            b"ID3\x03\x00\x00\x00\x00\x00\x00"  # ID3 tag header
            b"\xff\xfb\x90\x00"                   # MPEG frame sync
            b"\x00" * 413                          # silence padding
        )
        file_path.write_bytes(mp3_header)
        logger.debug("Mock audio written", path=str(file_path))
