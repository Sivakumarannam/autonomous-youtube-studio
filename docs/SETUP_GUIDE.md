# Setup Guide

## System Requirements

- **OS**: Windows 10/11 or Linux (tested on Windows with i5-1135G7, 16GB RAM)
- **Python**: 3.11+
- **FFmpeg**: Required for video encoding
- **Ollama**: Required for script generation (LLM)
- **Disk space**: ~5 GB (models + generated content)

## 1. Install Prerequisites

### FFmpeg

**Windows (Chocolatey):**
```powershell
choco install ffmpeg
```
**Windows (manual):** Download from https://ffmpeg.org/download.html and add to PATH

**Linux:**
```bash
sudo apt install ffmpeg
```

### Ollama

Download from https://ollama.ai and install.

```bash
# Pull the recommended model (4.7 GB)
ollama pull qwen2.5:7b

# Or a faster smaller model (1.8 GB)
ollama pull qwen2.5:3b
```

## 2. Python Dependencies

```bash
pip install -r requirements.txt
```

## 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# LLM Provider
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:pass@localhost:5432/youtube_studio

# YouTube API
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REFRESH_TOKEN=your_refresh_token

# Optional: Pexels stock photos (free at pexels.com/api)
PEXELS_API_KEY=your_pexels_key

# Optional: Pixabay background music (free at pixabay.com/api/docs)
PIXABAY_API_KEY=your_pixabay_key

# Voice provider (auto selects best available — Kokoro if models present)
VOICE_PROVIDER=auto
```

## 4. Kokoro TTS Setup (Optional — Highly Recommended)

Kokoro produces human-quality audio and runs fully offline (CPU).

The app loads these exact filenames under `storage/models/kokoro/`:

- `kokoro-v1.0.int8.onnx` (~89 MB)
- `voices-v1.0.bin` (~27 MB)

```bash
# Package is already in requirements.txt (kokoro-onnx, soundfile).

# Create model directory
mkdir -p storage/models/kokoro

# Download official v1.0 model files (matches app/integrations/kokoro_tts.py)
curl -L -o storage/models/kokoro/kokoro-v1.0.int8.onnx \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
curl -L -o storage/models/kokoro/voices-v1.0.bin \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# Docker / Oracle volume (run inside the api container):
# docker compose -f docker/docker-compose.oracle.yml exec api bash -c '
#   mkdir -p /app/storage/models/kokoro && cd /app/storage/models/kokoro &&
#   curl -L -o kokoro-v1.0.int8.onnx \
#     "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx" &&
#   curl -L -o voices-v1.0.bin \
#     "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
# '
```

Verify: `python -c "from app.integrations.kokoro_tts import is_available; print(is_available())"`

On success you should see `True` and a log line: `Kokoro TTS model loaded`.

## 5. Database Setup

```bash
# Run migrations
alembic upgrade head
```

## 6. YouTube OAuth Setup

1. Go to https://console.cloud.google.com/
2. Create a project → Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop App)
4. Download `client_secrets.json`
5. Run the auth script:
   ```bash
   python scripts/youtube_auth.py
   ```
6. Copy the refresh token to `.env`

## 7. Verify Installation

Start the server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Check the startup logs for validation results. All required services (FFmpeg, Ollama) must show ✓. Optional services (Pexels, Pixabay, Kokoro) show ⚠ if not configured — the pipeline still runs without them.

Dashboard: http://localhost:8000/dashboard

## 8. First Video

1. Open the dashboard
2. Create a channel with your niche (e.g. "technology")
3. Click **Generate Video**
4. The pipeline runs: Topic → Script → Voice → Video → Review

Check `storage/videos/` for the output MP4.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ffmpeg not found` | Add FFmpeg to PATH and restart terminal |
| `Ollama not reachable` | Start Ollama: `ollama serve` |
| `gTTS synthesis failed` | Check internet connection |
| `kokoro not available` | Download model files (step 4 above) into `storage/models/kokoro/` |
| `YouTube 400 error` | Check credentials; title must be ≤100 chars, no hashtags |
| Black video frames | Check `storage/images/` — image generation may be failing |
