# Changelog

## 2026-07-12 — Feature Update

### Added
- **Kokoro ONNX TTS** — High-quality neural TTS, runs offline on CPU  
  Priority: `kokoro → gtts → pyttsx3`. Download model files per SETUP_GUIDE.md.
- **Pexels stock photo integration** — Scenes now try real topic-relevant photos  
  before falling back to Pollinations AI images. Set `PEXELS_API_KEY` to enable.
- **Background music mixing** — Royalty-free music auto-selected per category  
  and mixed at -18 dBFS under voice using pydub. Set `PIXABAY_API_KEY` for live fetch.
- **Karaoke animated captions** — Word-by-word gold highlight using Whisper  
  word timestamps. Active by default (`CAPTION_STYLE=karaoke`). 
  Set `CAPTION_STYLE=static` for the original behaviour.
- **Startup health checks** — Validates Ollama, FFmpeg, Whisper, gTTS, Kokoro,  
  Pollinations, Pexels, Pixabay, and YouTube on startup with clear ✓/⚠/✗ logs.
- **PresenterService stub** — Interface ready for Wav2Lip/SadTalker/MuseTalk  
  when GPU hardware is available (`PRESENTER_PROVIDER` env var).
- **New config fields**: `pexels_api_key`, `pixabay_api_key`, `use_stock_photos`,  
  `voice_provider`, `voice_gender`, `background_music_*`, `caption_style`,  
  `karaoke_highlight_color`, `karaoke_base_color`.
- **VoiceSettings.gender** field — controls Kokoro voice selection (female/male).
- **`docs/` folder** — README, SETUP_GUIDE, AUTOMATION_GUIDE, API_KEYS,  
  CONFIG_REFERENCE, PROJECT_TRACKER, CHANGELOG.
- **`extract_visual_keywords()`** in Pexels provider — extracts concrete nouns/actions  
  from narration for better stock photo search queries.

### Changed
- `transcribe_sentences_from_audio` now returns `(timestamps, word_timestamps_per_sentence)`  
  tuple instead of plain `timestamps`. Word timestamps are stored on each scene dict  
  as `scene["word_timestamps"]` for karaoke rendering.
- `_render_scene_cards` gains `bake_captions` parameter (default True). Set to False  
  in karaoke mode to keep background PNGs caption-free.
- `_assemble_video` gains `karaoke_mode` parameter. When True and word_timestamps  
  are available, uses `_make_karaoke_clip()` (VideoClip with per-frame PIL drawing)  
  instead of a static ImageClip.
- Voice agent `_synthesise_audio` now tries Kokoro before gTTS when `VOICE_PROVIDER=auto`.

---

## 2026-07-11 — Bug Fixes

### Fixed
- **Dead-tail trim**: `effective_duration = last_scene.end_seconds + 0.8s` prevents  
  last scene from holding silently after narration ends.
- **gTTS instruction leaks**: Added `_strip_instruction_leaks()` with 15 regex  
  patterns to remove LLM system-prompt echoes from TTS text.
- **Image prompt quality**: Scenes now use narration text as FLUX prompt instead  
  of generic storyboard labels ("Intro:", "Point 1:").
- **YouTube 400 errors**: Pre-upload validation strips hashtags from title, truncates  
  at 100 chars, validates tags combined < 500 chars.
- **FLUX images**: Switched Pollinations to `model=flux`, 60s timeout, deterministic  
  seed from MD5 of prompt.
- **Video quality**: Default preset changed to `high` (CRF 18, slow encode).
- **Emojis in captions**: `_clean_narration()` strips non-letter Unicode before TTS  
  and caption rendering.

---

## 2026-07-07 — Phase 4 (RAG Research)

### Added
- RAG research pipeline (optional): Search → Crawl → Extract → Embed → FAISS store
- Script agents inject retrieved web content into Ollama prompts
- Channel automation scheduler (Phase 6): daily pipeline per channel
- Retry manager with exponential backoff for pipeline stages and scheduler

---

## Earlier

See `CHANGELOG_2026_07_07.md` and `PHASE4_PROGRESS.md` for earlier history.
