# Autonomous YouTube Studio

A fully automated, zero-cost YouTube Shorts and long-form video production pipeline built with FastAPI, Ollama, MoviePy, and PIL.

## What It Does

The studio autonomously produces and publishes YouTube videos in a continuous loop:

1. **Topic Discovery** → Research trending topics via Reddit, RSS, and trend analysis  
2. **Script Writing** → Ollama LLM generates the full narration script (Hook → Body → CTA)  
3. **SEO Tagging** → Auto-generates title, description, tags, and hashtags  
4. **Voice Synthesis** → Kokoro neural TTS (or gTTS fallback) narrates the script  
5. **Visual Rendering** → FLUX AI images + Pexels stock photos composited with MoviePy  
6. **Karaoke Captions** → Word-by-word animated captions via Whisper word timestamps  
7. **Background Music** → Royalty-free tracks from Pixabay mixed at -18 dBFS under voice  
8. **Quality Gate** → Automated quality + SEO scoring before upload  
9. **YouTube Upload** → OAuth2 upload with retry handling and rate-limit protection  
10. **Analytics** → Performance tracking with adaptive topic optimization

## Architecture

```
FastAPI + APScheduler
│
├── Pipeline Agent  (orchestrates all stages)
├── Topic Agent     (trend research)
├── Script Agent    (LLM script generation via Ollama)
├── SEO Agent       (title/tags/description optimization)
├── Voice Agent     (Kokoro TTS → MP3)
├── Storyboard Agent (scene planning)
├── Video Agent     (MoviePy render + karaoke captions)
├── Thumbnail Agent (PIL thumbnail generation)
└── Upload Agent    (YouTube Data API v3)
```

## Quick Start

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for full installation instructions.

```bash
# Minimum requirements
pip install -r requirements.txt
ollama pull qwen2.5-script

# Configure
cp .env.example .env  # edit your API keys

# Start
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dashboard: http://localhost:8000/dashboard

## Key Features

| Feature | Status | Notes |
|---------|--------|-------|
| Kokoro TTS | ✅ Ready | Download model files — see SETUP_GUIDE |
| gTTS fallback | ✅ Built-in | Requires internet |
| Pollinations FLUX images | ✅ Active | Free, no API key |
| Pexels stock photos | ✅ Ready | Free API key needed |
| Karaoke captions | ✅ Active | Requires Whisper timestamps |
| Background music | ✅ Ready | Pixabay API key needed |
| YouTube upload | ✅ Active | OAuth2 credentials needed |
| AI presenter (Wav2Lip etc.) | 🔧 Stub | Needs GPU — see PresenterService |

## Repository Structure

```
app/
├── agents/         Each AI agent (topic, script, voice, video, upload…)
├── core/           Config, logging, health checks
├── integrations/   External services (TTS, images, Pexels, music, YouTube)
├── scheduler/      Publish + automation schedulers
├── api/            REST API endpoints
└── web/            Dashboard templates
docs/               This documentation
storage/            Generated audio, video, thumbnails, images
```
