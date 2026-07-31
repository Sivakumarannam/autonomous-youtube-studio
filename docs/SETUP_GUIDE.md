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

# Voice provider (auto selects best available)
VOICE_PROVIDER=auto
```

## 4. Kokoro TTS Setup (Optional — Highly Recommended)

Kokoro produces human-quality audio and runs fully offline (CPU).

```bash
# Install the package
pip install kokoro-onnx soundfile

# Create model directory
mkdir -p storage/models/kokoro

# Download model files (~300 MB total)
# kokoro-v0_19.onnx — ONNX model weights
# voices.bin        — Voice embeddings

# Using Python:
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('hexgrad/Kokoro-82M', 'kokoro-v0_19.onnx', local_dir='storage/models/kokoro')
hf_hub_download('hexgrad/Kokoro-82M', 'voices.bin', local_dir='storage/models/kokoro')
print('Kokoro models downloaded.')
"
```

Verify: `python -c "from app.integrations.kokoro_tts import is_available; print(is_available())"`

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
| `kokoro not available` | Download model files (step 4 above) |
| `YouTube 400 error` | Check credentials; title must be ≤100 chars, no hashtags |
| Black video frames | Check `storage/images/` — image generation may be failing |
