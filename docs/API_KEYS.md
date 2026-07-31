# API Keys & Credentials

## Required

### YouTube Data API v3 (for upload)
1. Go to https://console.cloud.google.com/
2. Create project → Library → Enable **YouTube Data API v3**
3. Credentials → Create OAuth client ID → Desktop App
4. Download `client_secrets.json`
5. Run auth script and copy refresh token to `.env`:
   ```
   YOUTUBE_CLIENT_ID=...
   YOUTUBE_CLIENT_SECRET=...
   YOUTUBE_REFRESH_TOKEN=...
   ```

## Optional (free tiers)

### Pexels — stock photos & videos
- Sign up: https://www.pexels.com/api/
- Free tier: **200 requests/hour**, **20,000/month**
- Config: `PEXELS_API_KEY=your_key`
- Effect: Scenes use real stock photos instead of AI-generated ones

### Pixabay — background music
- Sign up: https://pixabay.com/service/about/api/
- Free tier: 5,000 requests/hour
- Config: `PIXABAY_API_KEY=your_key`
- Effect: Royalty-free music auto-selected per video category

### Brave Search (for RAG research)
- Sign up: https://brave.com/search/api/
- Free tier: 2,000 queries/month
- Config: `BRAVE_API_KEY=your_key`
- Effect: Script research pulls live web results

### Serper.dev (Google Search for RAG)
- Sign up: https://serper.dev/
- Free tier: 2,500 queries
- Config: `SERPER_API_KEY=your_key`
- Effect: Better research results for script generation

## Cost Overview

| Service | Cost | Purpose |
|---------|------|---------|
| Ollama | Free (local GPU/CPU) | Script generation |
| Pollinations AI | Free | AI image generation |
| Kokoro TTS | Free (local CPU) | Voice synthesis |
| gTTS | Free (Google) | Voice synthesis fallback |
| Pexels | Free tier | Stock photos |
| Pixabay | Free tier | Background music |
| Brave Search | Free tier | Research |
| YouTube Data API | Free quota | Upload + analytics |

**Total: $0/month** within free tier limits.

## Security Notes

- Never commit `.env` to git (it's in `.gitignore`)
- YouTube refresh tokens never expire unless revoked
- Rotate API keys if logs show unexpected 429 errors (quota exhausted by another app)
- All keys are read from environment variables — never hardcoded in source
