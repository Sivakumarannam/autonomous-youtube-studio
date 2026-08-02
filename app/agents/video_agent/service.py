import asyncio
import json
import re
import time
import unicodedata
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.video_agent.agent import VideoAgent
from app.agents.video_agent.models import VideoAgentOutput
from app.agents.video_agent.renderer import VideoRenderer
from app.core.config import settings
from app.core.logging import get_logger
from app.database.models.agent_log import AgentLog, AgentLogLevel
from app.database.models.video import Video, VideoStatus
from app.database.models.voice import VoiceStatus
from app.database.repositories.script_repository import ScriptRepository
from app.database.repositories.storyboard_repository import StoryboardRepository
from app.database.repositories.video_repository import VideoRepository
from app.database.repositories.voice_repository import VoiceRepository
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)
_WHISPER_MODEL = None
# ---------------------------------------------------------------------------
# Pure helpers — no DB, no async, fully unit-testable
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\r?\n+")
# Matches any hashtag token in text (e.g. #Shorts, #Tips)
_HASHTAG_RE = re.compile(r"#\w+")
# Matches URLs
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


def _clean_narration(text: str) -> str:
    """Remove non-speakable characters from narration before rendering.

    Text-to-speech engines and video captions should contain ONLY plain
    spoken words.  Strip:
      - Hashtags  (#Shorts, #Tips, …)
      - URLs      (https://…)
      - Emojis and other non-letter Unicode symbols (category So / Cs / Cn)
      - Asterisks and markdown formatting markers
    Collapses any resulting double-spaces.
    """
    text = _HASHTAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    # Remove emojis / pictographic symbols
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep: letters (L*), numbers (N*), punctuation (P*), separators (Z*),
        # and plain ASCII symbols that appear in normal prose.
        if cat.startswith(("L", "N", "P", "Z")) or ch in (" ", "\n", "\t", "-", "'", '"'):
            cleaned.append(ch)
        # Drop: Symbol (S*), Other (C*) — covers most emoji ranges
    text = "".join(cleaned)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def split_sentences(text: str) -> list[str]:
    """Split *text* into a list of non-empty sentences.

    Uses trailing punctuation (.!?) followed by whitespace as the split
    boundary.  Falls back to the whole text as a single item when no
    sentence boundary is found.
    """
    parts = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def align_sentences_to_scenes(
    sentences: list[str],
    raw_scenes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one scene-card per sentence, perfectly aligned.

    Rules
    -----
    * There is always exactly ``len(sentences)`` output cards.
    * Each card carries exactly one sentence as its ``narration`` — the text
      displayed on screen **and** spoken aloud at that moment.
    * ``duration_seconds`` on each card is proportional so that, when the
      renderer scales all cards to the actual audio duration, the transitions
      happen exactly when the narration moves to the next sentence.

    Cases
    -----
    n_sentences <= n_scenes  →  merge consecutive storyboard scenes into
                                sentence-groups (one group per sentence).
                                Each group's duration = sum of its members.

    n_sentences > n_scenes   →  distribute sentences across the available
                                storyboard duration.  Each sentence card gets
                                a share of the total storyboard duration
                                proportional to its word count — longer
                                sentences take longer to speak, so they hold
                                the screen for longer.
                                Visual context is borrowed from the
                                proportionally nearest storyboard scene.
    """
    if not sentences:
        return []

    if not raw_scenes:
        # No storyboard at all — give every sentence a 5-second placeholder.
        return [
            {
                "scene_number": i + 1,
                "timestamp": "",
                "duration_seconds": 5.0,
                "visual": "",
                "narration": sentence,
            }
            for i, sentence in enumerate(sentences)
        ]

    n_sentences = len(sentences)
    n_scenes = len(raw_scenes)

    # ------------------------------------------------------------------
    # CASE A: more storyboard scenes than sentences
    #         Merge scenes so each sentence gets one card.
    # ------------------------------------------------------------------
    if n_sentences <= n_scenes:
        base, remainder = divmod(n_scenes, n_sentences)
        merged: list[dict[str, Any]] = []
        scene_idx = 0
        for sent_idx, sentence in enumerate(sentences):
            group_size = base + (1 if sent_idx < remainder else 0)
            group = raw_scenes[scene_idx: scene_idx + group_size]
            scene_idx += group_size

            merged.append(
                {
                    "scene_number": sent_idx + 1,
                    "timestamp": group[0].get("timestamp", "") if group else "",
                    "duration_seconds": sum(s["duration_seconds"] for s in group),
                    "visual": group[0].get("visual", "") if group else "",
                    "narration": sentence,
                }
            )
        return merged

    # ------------------------------------------------------------------
    # CASE B: more sentences than storyboard scenes
    #         Create exactly n_sentences cards.  Duration is allocated
    #         proportional to each sentence's word count because speech
    #         rate is approximately proportional to word count — longer
    #         sentences hold the screen longer, keeping text in sync with
    #         the audio.  Visual context is borrowed from the
    #         proportionally nearest storyboard scene.
    # ------------------------------------------------------------------
    total_duration = sum(s["duration_seconds"] for s in raw_scenes)
    word_counts = [max(1, len(sentence.split())) for sentence in sentences]
    total_words = sum(word_counts)

    result: list[dict[str, Any]] = []
    for i, sentence in enumerate(sentences):
        # Map sentence index → nearest storyboard scene (proportional mapping)
        scene_idx = min(int(i * n_scenes / n_sentences), n_scenes - 1)
        scene = raw_scenes[scene_idx]
        # Word-count-proportional duration; floor at 1 second
        duration = max(1.0, (word_counts[i] / total_words) * total_duration)
        result.append(
            {
                "scene_number": i + 1,
                "timestamp": scene.get("timestamp", ""),
                "duration_seconds": duration,
                "visual": scene.get("visual", ""),
                "narration": sentence,
            }
        )
    return result


def transcribe_sentences_from_audio(
    audio_path: str,
    sentences: list[str],
) -> list[tuple[float, float]] | None:
    """Map each sentence to its real ``(start_sec, end_sec)`` in *audio_path*.

    Uses **faster-whisper** (``tiny`` model, CPU + int8) to obtain word-level
    timestamps from the TTS-generated MP3, then advances a word-cursor through
    the transcript by the sentence's own word count.  This gives far more
    accurate scene timing than estimating from word count alone.

    Returns ``None`` on any failure so the caller can silently fall back to
    the word-count estimator — the pipeline never breaks.

    Why faster-whisper, not MoviePy
    --------------------------------
    MoviePy 2.x is a *video editing* library.  It has **no** APIs for:
    word timestamps, sentence timestamps, speech alignment, transcript timing,
    or phoneme timing.  It does not know anything about speech content.
    Verified against moviepy 2.x source: only ``AudioFileClip``,
    ``VideoFileClip``, compositing and effects are exposed.

    Why faster-whisper over alternatives
    --------------------------------------
    * **faster-whisper** — CTranslate2-backed, 4× faster than OpenAI Whisper
      on CPU, returns word-level timestamps natively, int8 quantisation for
      minimum RAM, well-maintained (Systran).  Best for this stack.
    * openai-whisper — slower CPU inference, no word timestamps without hacks.
    * WhisperX — adds phoneme alignment but requires torch + alignment models.
    * aeneas / Gentle — forced aligners, need the exact transcript up-front
      and complex C/Java dependencies.
    * stable-ts — good but depends on openai-whisper which is slower.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError:
        logger.info(
            "faster-whisper not installed — using word-count timing.",
            hint="pip install faster-whisper",
        )
        return None

    if not sentences:
        return None

    try:
        # ``tiny`` model: ~75 MB download, runs in ≈real-time on CPU with int8.
        # Downloaded once to ~/.cache/huggingface/hub/ on first call.
        global _WHISPER_MODEL

        if _WHISPER_MODEL is None:
            _WHISPER_MODEL = WhisperModel(
                "tiny",
                device="cpu",
                compute_type="int8",
            )

        model = _WHISPER_MODEL
        segments_gen, _info = model.transcribe(
            audio_path,
            language="en",
            word_timestamps=True,
            vad_filter=True,          # skip silent leading/trailing audio
            vad_parameters={
                "threshold": 0.5,     # voice activity detection sensitivity
                "min_silence_duration_ms": 300,
            },
            beam_size=5,              # faster; accuracy sufficient for timing
            condition_on_previous_text=False,
            no_speech_threshold=0.6,  # ignore low-confidence non-speech segments
            log_prob_threshold=-1.0,  # drop hallucinated segments on silence
            compression_ratio_threshold=2.4,
        )

        # Consume the generator → flat word list with timestamps
        whisper_words: list[tuple[str, float, float]] = []
        for seg in segments_gen:
            seg_logged = False
            for w in seg.words or []:
                logger.info(f"{w.word}  {w.start:.2f} -> {w.end:.2f}")
                tok = w.word.strip()
                if tok:
                    whisper_words.append((tok, w.start, w.end))
                    if not seg_logged:
                        logger.info(
                            f"Whisper segment: "
                            f"{seg.start:.2f}s -> {seg.end:.2f}s | {seg.text}"
                        )
                        seg_logged = True

        if not whisper_words:
            logger.warning("faster-whisper returned no words; falling back.")
            return None
        total_w = len(whisper_words)
        timestamps: list[tuple[float, float]] = []
        # word_timestamps_per_sentence[i] = list of {"word", "start", "end"} for sentence i
        word_timestamps_per_sentence: list[list[dict]] = []

        all_words = [w[0].lower() for w in whisper_words]
        search_start = 0

        for sentence in sentences:
            sentence_words = [w.lower() for w in sentence.split()]
            if not sentence_words:
                word_timestamps_per_sentence.append([])
                continue

            search_limit = len(all_words) - len(sentence_words) + 1
            best_index = search_start
            found = False

            for i in range(search_start, max(search_start + 1, search_limit)):
                matches = sum(
                    1 for j in range(min(4, len(sentence_words)))
                    if all_words[i + j] == sentence_words[j]
                )
                if matches >= max(2, min(4, len(sentence_words))):
                    best_index = i
                    found = True
                    break
            if not found:
                best_index = search_start

            start_sec = whisper_words[best_index][1]
            end_index = min(best_index + len(sentence_words) - 1, len(whisper_words) - 1)
            end_sec = whisper_words[end_index][2]
            timestamps.append((start_sec, end_sec))

            # Collect word-level timestamps for this sentence window
            sent_words = [
                {"word": whisper_words[k][0], "start": whisper_words[k][1], "end": whisper_words[k][2]}
                for k in range(best_index, end_index + 1)
            ]
            word_timestamps_per_sentence.append(sent_words)
            search_start = end_index + 1

        logger.info(
            "faster-whisper timestamp alignment complete.",
            sentences=len(sentences),
            whisper_words=total_w,
            audio_covered_sec=round(whisper_words[-1][2], 2),
        )
        # Return sentence timestamps AND per-sentence word timestamps
        return timestamps, word_timestamps_per_sentence

    except Exception as exc:
        logger.warning(
            "faster-whisper transcription failed; using word-count timing.",
            error=str(exc),
        )
        return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VideoAgentService:
    AGENT_NAME = "VideoAgent"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._renderer = VideoRenderer()

    async def run_for_script(
        self,
        script,
        topic_title: str = "",
        description: str = "",
        script_type: str = "long",
    ) -> VideoAgentOutput:
        agent = VideoAgent(llm_provider=get_llm_provider())
        output = await agent.generate_plan(
            topic_title=topic_title or script.seo_title or "Untitled",
            description=description,
            script_type=script_type,
        )

        video_repository = VideoRepository(self._session)

        video = await video_repository.get_by_script_id(script.id)
        if video is None:
            video = Video(
                script_id=script.id,
                status=VideoStatus.PENDING,
                resolution=self._resolution_for(script_type),
            )
            self._session.add(video)
            await self._session.flush()

        video = await video_repository.mark_generating(video)

        # Resolve voice-only audio path. This is the clean speech file before
        # any background music is mixed in. Whisper MUST run on this file —
        # running it on the music-mixed track shifts word timestamps because
        # Whisper's VAD and alignment are thrown off by the music signal.
        voice_only_audio_path = await self._resolve_audio_path(script.id)

        # Mix background music into a separate copy for the final video audio.
        # The voice-only path is preserved for Whisper alignment and SadTalker.
        audio_path = voice_only_audio_path
        if audio_path and settings.background_music_enabled:
            audio_path = await self._mix_background_music(
                audio_path=audio_path,
                script_id=str(script.id),
                channel_category=getattr(script, "niche", "technology"),
            )

        # Generate a picture-in-picture presenter clip (SadTalker via a
        # hosted Hugging Face Space) covering the ENTIRE narration, once
        # per video — not per scene.
        # Uses the clean voice-only audio, not the music-mixed track.
        # Returns None (and logs why) if disabled/unavailable/failed; the
        # pipeline continues with background-only visuals either way.
        presenter_path = await self._generate_presenter_clip(
            audio_path=voice_only_audio_path,
            script_id=str(script.id),
            gender=script.voice_gender or "female",
        )

        # Whisper alignment uses voice_only_audio_path so music does not
        # disturb the timestamp extraction. The final video uses audio_path
        # (which may be the music-mixed version).
        scenes = await self._resolve_scenes(
            script.id, output, script, audio_path=voice_only_audio_path
        )

        # Generate one background image per scene concurrently (max 3 in-flight).
        # Returns an empty mapping on any failure so the renderer falls back to
        # text cards — the pipeline must never hard-fail because of ImageProvider.
        from app.agents.video_agent.renderer import _SHORT_RESOLUTION, _LONG_RESOLUTION
        img_resolution = _SHORT_RESOLUTION if script_type == "short" else _LONG_RESOLUTION
        image_paths = await self._generate_scene_images(
            str(script.id), scenes, resolution=img_resolution
        )

        # ── Commit before the long render ─────────────────────────────────────
        # The renderer is synchronous CPU-bound work that blocks the event loop
        # for several minutes with zero DB activity.  Remote serverless Postgres
        # (e.g. Neon) silently drops connections idle for ~5 min.
        # Committing here flushes all pre-render state to the DB and releases
        # the checked-out asyncpg connection back to the pool.  The post-render
        # write then checks out a fresh, pool_pre_ping-validated connection.
        await self._session.commit()

        render_result = self._renderer.render(
            script_id=str(script.id),
            scenes=scenes,
            audio_path=audio_path,
            script_type=script_type,
            image_paths=image_paths,
            presenter_path=presenter_path,
            # Use the SEO title (short keyword phrase) as the visual hook
            # overlay — NOT the spoken hook sentence from full_script, which
            # is already in the audio. Using the spoken sentence here caused
            # the viewer to see and hear the same words simultaneously.
            hook_text=script.seo_title or output.title,
        )

        # ── Post-render DB write: use a fresh session ──────────────────────
        # The connection held before the render may have been dropped by the
        # remote DB during the multi-minute render.  Open a fresh session so
        # pool_pre_ping validates the checkout before any write.
        from app.database.connection import get_session_factory as _gsf
        _video_id = video.id
        _script_id = script.id
        async with _gsf()() as _fresh:
            _vr = VideoRepository(_fresh)
            _v = await _vr.get_by_script_id(_script_id)
            if _v is None:
                # Safety fallback: look up by primary key
                _v = await _vr.get_or_raise(_video_id)

            if render_result.success:
                video = await _vr.mark_complete(
                    _v,
                    video_path=render_result.video_path,
                    duration=render_result.duration_seconds,
                    file_size=render_result.file_size,
                )
                await _fresh.commit()

                output.output_path = render_result.video_path
                output.duration_seconds = int(render_result.duration_seconds)
                output.file_size = render_result.file_size

                await self._log(
                    AgentLogLevel.INFO,
                    f"Video rendered: {output.title}",
                    context=json.dumps(
                        {
                            "script_id": str(_script_id),
                            "video_path": video.video_path,
                        }
                    ),
                    entity_id=str(_script_id),
                    execution_time=time.monotonic(),
                )
            else:
                video = await _vr.mark_failed(
                    _v,
                    error_message=render_result.error_message or "Video rendering failed.",
                )
                await _fresh.commit()

                output.success = False

                await self._log(
                    AgentLogLevel.ERROR,
                    f"Video rendering failed: {render_result.error_message}",
                    context=json.dumps({"script_id": str(_script_id)}),
                    entity_id=str(_script_id),
                    execution_time=time.monotonic(),
                )

        return output

    async def _resolve_scenes(
        self,
        script_id: UUID,
        output: VideoAgentOutput,
        script,
        audio_path: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        storyboard_repository = StoryboardRepository(self._session)
        voice_repository = VoiceRepository(self._session)

        storyboard = await storyboard_repository.get_by_script_id(script_id)
        voice = await voice_repository.get_by_script_id(script_id)

        # Use voice transcript as the authoritative narration source — it is
        # exactly what was spoken.  Fall back to script content.
        spoken_text: str = ""
        if (
            voice is not None
            and voice.status == VoiceStatus.COMPLETE
            and voice.transcript
        ):
            spoken_text = voice.transcript.strip()
            logger.info(
                "Using voice transcript for scene narration.",
                script_id=str(script_id),
            )
        elif script.content:
            spoken_text = script.content.strip()
            logger.info(
                "Using script content for scene narration.",
                script_id=str(script_id),
            )

        # Strip emojis, hashtags, and URLs before splitting — these must never
        # appear in spoken captions or Whisper word-matching will fail.
        spoken_text = _clean_narration(spoken_text)

        sentences = split_sentences(spoken_text)
        # Sanitize each sentence individually as a safety net
        sentences = [_clean_narration(s) for s in sentences if _clean_narration(s)]
        if not sentences:
            sentences = [""]

        # Build raw storyboard scene list
        raw_scenes: list[dict[str, Any]] = []

        if storyboard is not None and storyboard.scenes:
            raw = storyboard.scenes
            if isinstance(raw, dict):
                raw = raw.get("scenes", [])
            if isinstance(raw, list):
                raw_scenes = [
                    {
                        "scene_number": s.get("scene_number", i + 1),
                        "timestamp": s.get("timestamp", ""),
                        "duration_seconds": float(
                            s.get("duration_seconds", 5) or 5
                        ),
                        "visual": s.get("visual") or s.get("image_prompt", ""),
                    }
                    for i, s in enumerate(raw)
                ]

        if not raw_scenes:
            raw_scenes = [
                {
                    "scene_number": i + 1,
                    "timestamp": "",
                    "duration_seconds": float(s.duration_seconds or 5),
                    # Use the full description so the AI knows what action to draw!
                    "visual": f"{s.title}: {s.description}", 
                }
                for i, s in enumerate(output.scenes)
            ]

        if not raw_scenes:
            raw_scenes = [
                {"scene_number": 1, "timestamp": "", "duration_seconds": 5.0, "visual": ""}
            ]

        # Initial alignment using word-count-proportional durations.
        aligned = align_sentences_to_scenes(sentences, raw_scenes)

        # ----------------------------------------------------------------
        # WHISPER TIMESTAMP OVERRIDE
        # If an audio file is available, use faster-whisper to get real
        # per-sentence timestamps and replace the word-count estimates.
        # This eliminates drift caused by variable TTS speech rate.
        # The CPU-bound transcription runs in a thread so it does not
        # block the async event loop.
        # ----------------------------------------------------------------
        if audio_path and sentences:
            try:
                loop = asyncio.get_running_loop()
                whisper_result = await loop.run_in_executor(
                    None,
                    transcribe_sentences_from_audio,
                    audio_path,
                    sentences,
                )
                if whisper_result is not None:
                    timestamps, word_timestamps_per_sentence = whisper_result
                    if len(timestamps) == len(aligned):
                        for card, (start_sec, end_sec), words in zip(
                        aligned, timestamps, word_timestamps_per_sentence
                    ):
                            real_dur = max(0.5, end_sec - start_sec)
                            old_dur = card["duration_seconds"]
                            card["start_seconds"] = start_sec
                            card["end_seconds"] = end_sec
                            card["duration_seconds"] = real_dur

                            # Build karaoke word-timestamps from the ACTUAL clean
                            # script text (card["narration"]), not from Whisper's
                            # raw transcription. Whisper can mishear words (e.g.
                            # "violinist" → "violence"), so we replace the TEXT
                            # with correct clean words.
                            #
                            # TIMING: We now use Whisper's actual per-word
                            # boundaries as keyframes rather than linear
                            # interpolation. Whisper knows where pauses, fast
                            # syllables, and emphasis occur — mapping clean words
                            # proportionally across those keyframes gives far
                            # more accurate karaoke highlight timing than
                            # assuming every word takes equal time.
                            clean_words = card["narration"].split()
                            if clean_words:
                                n_clean = len(clean_words)
                                if words:
                                    # Map each clean word to its proportional
                                    # position in the Whisper word-boundary list.
                                    # This preserves Whisper's non-linear timing
                                    # (pauses, fast speech, emphasis) while
                                    # showing the correct clean text.
                                    n_w = len(words)
                                    wt: list[dict] = []
                                    for ci, cw in enumerate(clean_words):
                                        wi_s = min(
                                            int(ci * n_w / n_clean), n_w - 1
                                        )
                                        wi_e = min(
                                            int((ci + 1) * n_w / n_clean),
                                            n_w - 1,
                                        )
                                        t_s = words[wi_s]["start"]
                                        t_e = words[wi_e]["end"]
                                        wt.append(
                                            {"word": cw, "start": t_s, "end": t_e}
                                        )
                                    card["word_timestamps"] = wt
                                else:
                                    # No Whisper words for this sentence —
                                    # fall back to linear interpolation.
                                    n = n_clean
                                    card["word_timestamps"] = [
                                        {
                                            "word": w,
                                            "start": start_sec + (i / n) * real_dur,
                                            "end": start_sec
                                            + ((i + 1) / n) * real_dur,
                                        }
                                        for i, w in enumerate(clean_words)
                                    ]
                            else:
                                # No clean narration — fall back to Whisper's
                                # words so the karaoke bar is never empty.
                                card["word_timestamps"] = words
                            logger.info(
                                "Whisper timestamp applied.",
                                scene=card["scene_number"],
                                word_count_est=round(old_dur, 2),
                                whisper_real=round(real_dur, 2),
                                start=round(start_sec, 3),
                                end=round(end_sec, 3),
                                karaoke_words=len(words),
                            )
                    else:
                        logger.warning(
                            "Whisper returned different count than sentences; skipping.",
                            whisper_count=len(timestamps),
                            sentence_count=len(aligned),
                        )
            except Exception as exc:
                logger.warning(
                    "Whisper timestamp override failed; keeping word-count timing.",
                    error=str(exc),
                )

            logger.info("========== FINAL SCENE TIMING ==========")

            for scene in aligned:
                logger.info(
                    f"""
            Scene {scene['scene_number']}
            Start    : {scene.get('start_seconds', 'N/A')}
            Duration : {scene['duration_seconds']:.2f}

            Narration:
            {scene['narration']}
            """
                )

            logger.info("=======================================")
         # Always return the scenes, even if no audio exists
        return aligned

    async def _generate_scene_images(
        self,
        script_id: str,
        scenes: list[dict[str, Any]],
        resolution: tuple[int, int] = (1280, 720),
    ) -> dict[int, str]:
        """Sequentially generate a background image for each scene.

        Uses a sequential for-loop to guarantee we do not trigger rate limits
        on free shared services like Pollinations.
        Returns an empty mapping on any unexpected failure so the renderer
        falls back gracefully to text-card style.
        """
        from app.integrations.image_provider import ImageProvider, enhance_prompt

        width, height = resolution
        mapping: dict[int, str] = {}

        # Regex to detect generic structural labels that are useless as image prompts
        # e.g. "Intro: The presenter introduces...", "Point 1: ...", "Scene 3:"
        _generic_label_re = re.compile(
            r"^(intro|scene|point|hook|body|cta|conclusion|outro|section)\b",
            re.IGNORECASE,
        )

        try:
            for scene in scenes:
                scene_num: int = scene.get("scene_number", 0)
                storyboard_visual = str(
                    scene.get("visual") or scene.get("image_prompt") or ""
                ).strip()
                narration = str(scene.get("narration") or "").strip()

                # Prefer the actual narration over generic storyboard labels.
                # Narration text ("Did you know the didgeridoo is over 4000 years old?")
                # produces far more relevant images than "Intro: The presenter
                # introduces the topic with a shocking fact."
                if narration and (
                    not storyboard_visual
                    or _generic_label_re.match(storyboard_visual)
                    or len(storyboard_visual) < 30
                ):
                    prompt = narration
                elif storyboard_visual:
                    prompt = storyboard_visual
                else:
                    prompt = narration

                if not prompt:
                    continue

                # Enhance the prompt with quality keywords before generation
                enhanced = enhance_prompt(prompt)

                path = await ImageProvider.generate(
                    prompt=enhanced,
                    width=width,
                    height=height,
                    script_id=script_id,
                )

                # ----------------------------------------------------------
                # Try Pexels stock photo first (free API, real photos)
                # ----------------------------------------------------------
                pexels_used = False
                if settings.pexels_api_key and settings.use_stock_photos:
                    try:
                        from app.integrations.pexels_provider import (
                            download_photo,
                            extract_visual_keywords,
                        )
                        orientation = "portrait" if width < height else "landscape"
                        search_q = extract_visual_keywords(prompt)
                        pexels_path = await download_photo(search_q, orientation=orientation)
                        if pexels_path:
                            mapping[scene_num] = pexels_path
                            pexels_used = True
                            logger.info(
                                "Pexels stock photo selected",
                                scene=scene_num,
                                query=search_q,
                            )
                    except Exception as pex_exc:
                        logger.debug("Pexels fetch skipped", error=str(pex_exc))

                if not pexels_used:
                    path = await ImageProvider.generate(
                        prompt=enhanced,
                        width=width,
                        height=height,
                        script_id=script_id,
                    )
                    if path is not None:
                        mapping[scene_num] = path

                # Hard 2-second sleep between successful requests
                await asyncio.sleep(2.0)

            logger.info(
                "Scene image generation complete.",
                script_id=script_id,
                total_scenes=len(scenes),
                images_generated=len(mapping),
            )
            return mapping
        except Exception as exc:
            logger.warning(
                "Scene image generation failed; proceeding with text-card fallback.",
                script_id=script_id,
                error=str(exc),
            )
            return mapping

    async def _mix_background_music(
        self,
        audio_path: str,
        script_id: str,
        channel_category: str = "technology",
    ) -> str:
        """
        Fetch background music and mix it under the voice audio.

        Returns the path to the mixed audio file.  Falls back to the original
        audio_path if music is unavailable or mixing fails (never hard-fails
        the pipeline).
        """
        try:
            from app.integrations.music_provider import (
                fetch_track,
                genre_for_category,
                mix_music_under_voice,
            )
            from pathlib import Path

            genre = genre_for_category(channel_category)
            music_path = await fetch_track(genre=genre)

            if music_path is None:
                logger.info(
                    "No background music available",
                    genre=genre,
                    category=channel_category,
                )
                return audio_path

            # Output path: storage/audio/<script_id>_mixed.mp3
            mixed_path = str(
                Path(settings.storage_local_path)
                / "audio"
                / f"{script_id}_mixed.mp3"
            )
            ok = mix_music_under_voice(
                voice_path=audio_path,
                music_path=music_path,
                output_path=mixed_path,
                music_volume_db=settings.background_music_volume_db,
                fade_in_ms=settings.background_music_fade_in_ms,
                fade_out_ms=settings.background_music_fade_out_ms,
            )
            if ok:
                logger.info(
                    "Background music mixed",
                    genre=genre,
                    mixed_path=mixed_path,
                )
                return mixed_path
        except Exception as exc:
            logger.warning(
                "Background music mixing failed — using voice-only audio",
                error=str(exc),
            )
        return audio_path
    

    async def _generate_presenter_clip(
        self,
        audio_path: Optional[str],
        script_id: str,
        gender: str = "female",
    ) -> Optional[str]:
        """
        Generate a picture-in-picture presenter (talking-head) clip covering
        the full narration audio, via a hosted SadTalker Gradio Space on
        Hugging Face.

        Returns None (never raises) if the presenter feature is disabled,
        unconfigured, or the Space call fails for any reason — the pipeline
        must always be able to render a video with background visuals only.
        """
        if not audio_path:
            return None
 
        try:
            from app.integrations.presenter_service import PresenterService
            from pathlib import Path
 
            presenter = PresenterService()
            if not presenter.is_available():
                return None
 
            output_path = str(
                Path(settings.storage_local_path) / "presenter" / f"{script_id}.mp4"
            )
            result = await presenter.generate(
                audio_path=audio_path,
                output_path=output_path,
                gender=gender,
            )
            return result
        except Exception as exc:
            logger.warning(
                "Presenter clip generation failed — continuing without it",
                error=str(exc),
            )
            return None

    async def _resolve_audio_path(self, script_id: UUID) -> Optional[str]:
        voice_repository = VoiceRepository(self._session)
        voice = await voice_repository.get_by_script_id(script_id)

        if voice is None:
            logger.info(
                "No Voice record found for script.", script_id=str(script_id)
            )
            return None

        if voice.status != VoiceStatus.COMPLETE:
            logger.info(
                "Voice record exists but is not complete; skipping audio.",
                script_id=str(script_id),
                voice_status=str(voice.status),
            )
            return None

        if not voice.audio_path:
            logger.info(
                "Voice record is complete but has no audio_path.",
                script_id=str(script_id),
            )
            return None

        return voice.audio_path

    def _resolution_for(self, script_type: str) -> str:
        return "720x1280" if script_type == "short" else "1280x720"

    async def run_for_approved_scripts(
        self, limit: int = 5
    ) -> list[VideoAgentOutput]:
        script_repository = ScriptRepository(self._session)
        video_repository = VideoRepository(self._session)

        scripts = await script_repository.get_approved(limit=limit)

        outputs: list[VideoAgentOutput] = []

        for script in scripts:
            existing = await video_repository.get_by_script_id(script.id)
            if existing is not None and existing.status != VideoStatus.FAILED:
                continue

            output = await self.run_for_script(
                script=script,
                topic_title=script.seo_title or script.title,
                description=getattr(script, "description", ""),
                script_type=str(script.script_type),
            )
            outputs.append(output)

        return outputs

    async def _log(
        self,
        level: AgentLogLevel,
        message: str,
        context: str | None = None,
        entity_id: str | None = None,
        execution_time: float | None = None,
    ) -> None:
        entry = AgentLog(
            agent_name=self.AGENT_NAME,
            level=level,
            message=message,
            context=context,
            entity_type="script",
            entity_id=entity_id,
            execution_time=execution_time,
        )
        self._session.add(entry)
        await self._session.flush()