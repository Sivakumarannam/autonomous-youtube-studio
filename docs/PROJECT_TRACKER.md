# Project Tracker

## Implemented Features

### Core Pipeline
- [x] Topic discovery (Reddit, RSS, trend analysis)
- [x] LLM script generation (Ollama — short + long form)
- [x] SEO title/tag/description generation (100/100 scorer)
- [x] Content moderation gate
- [x] Voice synthesis (Kokoro neural TTS / gTTS / pyttsx3)
- [x] Storyboard planning (scene layout)
- [x] AI image generation (Pollinations FLUX)
- [x] Pexels stock photo integration
- [x] Video rendering (MoviePy + PIL)
- [x] Karaoke animated captions (word-level Whisper timestamps)
- [x] Background music mixing (Pixabay + pydub)
- [x] Thumbnail generation (PIL)
- [x] YouTube upload (OAuth2 + retry)
- [x] Analytics tracking

### Quality & Safety
- [x] Quality gate (score threshold, rejects poor videos)
- [x] Narration sanitizer (strips emojis, hashtags, URLs from TTS)
- [x] Instruction-leak detector (strips LLM system-prompt echoes)
- [x] Dead-tail trim (video ends at last narration word + 0.8s)
- [x] Upload validation (title length, no hashtags, tag limits)
- [x] Template title detection (rejects unfilled LLM placeholders)

### Infrastructure
- [x] FastAPI async server
- [x] PostgreSQL + SQLAlchemy async ORM
- [x] Alembic migrations
- [x] APScheduler (publish + daily automation)
- [x] HTMX dashboard
- [x] Prometheus metrics endpoint
- [x] Structured JSON logging
- [x] Startup health checks (Ollama, FFmpeg, Whisper, TTS, APIs)
- [x] Retry with exponential backoff
- [x] RAG research (FAISS + crawl + embed — optional)

## In Progress / Partial

- [ ] **Piper TTS** — Kokoro is installed, Piper binary download needs `PIPER_MODEL_DIR` setup
- [ ] **AI Presenter** — PresenterService stub ready; Wav2Lip/SadTalker needs GPU
- [ ] **Channel branding / watermark** — config exists, not yet composited into video
- [ ] **Video blur/resolution validation** — quality gate exists, SSIM-based sharpness check planned

## Planned

### High Priority
- [ ] Multi-language support (Spanish, Hindi, French)
- [ ] A/B thumbnail testing
- [ ] Shorts series continuity (related-topic follow-ups)
- [ ] Piper TTS offline model auto-download

### Medium Priority
- [ ] AI presenter integration (SadTalker when GPU available)
- [ ] Video quality validation (SSIM blur detection, resolution check)
- [ ] Push notifications (Telegram/Discord on video publish)
- [ ] Channel performance dashboard improvements

### Low Priority
- [ ] Video chapter markers
- [ ] Custom intro/outro clips
- [ ] End-screen automation
- [ ] Comment sentiment monitoring

## Known Issues / Workarounds

| Issue | Workaround |
|-------|-----------|
| Whisper `tiny` model may miss words in noisy audio | Switch to `base` model by editing `service.py` |
| Pexels returns landscape photos for portrait Shorts | Query forced to `orientation=portrait` |
| Kokoro model files must be downloaded manually | See SETUP_GUIDE.md step 4 |
| gTTS requires internet connection | Use Kokoro for offline operation |
| Background music fallback CDN URLs may be stale | Add MP3 files to `storage/music/` |
