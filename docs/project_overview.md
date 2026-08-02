# Autonomous YouTube Studio — Project Overview

## What It Does

Autonomous YouTube Studio is a fully automated content factory that produces and publishes YouTube videos with zero manual work after initial setup.

## Full Pipeline Flow

```
Topic Discovery
    ↓
Web Research (RAG — crawl + embed + vector search using FAISS + all-MiniLM-L6-v2)
    ↓
Script Writing (Groq LLM primary, Gemini fallback)
    ↓
Quality & Moderation checks (auto-reject bad content below minimum score)
    ↓
SEO optimisation (titles, descriptions, tags)
    ↓
Voice narration (Kokoro TTS primary, gTTS fallback)
    ↓
Storyboard → Scene cards with stock images (Pexels) / AI images (Pollinations)
    ↓
Video render (FFmpeg — karaoke captions, background music, transitions)
    ↓
Thumbnail generation
    ↓
YouTube upload (OAuth2 — client_id, client_secret, refresh_token)
    ↓
Instagram cross-post (Business Login token — 24 h delay)
    ↓
Notifications (Slack / Telegram / Discord / Email)
```

## Key Agents

- **Research Agent**: Crawls the web, embeds content into FAISS vector store per topic_id
- **Script Agent**: Calls LLM with research context to write video script
- **Quality Agent**: Scores the script and rejects it if below QUALITY_MIN_SCORE (default 70)
- **SEO Agent**: Generates YouTube title, description, tags
- **Voice Agent**: Synthesises narration audio (WAV/MP3) stored in storage/audio/
- **Storyboard Agent**: Creates scene cards with image prompts and timing
- **Video Agent**: Runs FFmpeg to assemble final MP4 with captions and music
- **Thumbnail Agent**: Generates thumbnail image
- **Upload Agent**: Uses YouTube Data API v3 to publish the video
- **Instagram Agent**: Cross-posts to Instagram Business account after 24 h

## Configuration

All configuration is via environment variables or `.env` file:

| Variable | Purpose | Default |
|----------|---------|---------|
| LLM_PROVIDER | groq / gemini / ollama / mock | mock |
| GROQ_API_KEY | Groq API key (required for groq provider) | — |
| GEMINI_API_KEY | Google Gemini API key (fallback) | — |
| DASHBOARD_AUTH_TOKEN | Dashboard login token | — (dev: no auth) |
| DATABASE_URL | PostgreSQL URL (prod) or SQLite (dev) | SQLite |
| YOUTUBE_CLIENT_ID | OAuth2 client ID | — |
| YOUTUBE_CLIENT_SECRET | OAuth2 client secret | — |
| YOUTUBE_REFRESH_TOKEN | OAuth2 refresh token | — |
| QUALITY_MIN_SCORE | Minimum script quality score 0–100 | 70 |
| VOICE_PROVIDER | auto / kokoro / gtts | auto |
| PEXELS_API_KEY | Stock photo/video API | — |
| PIXABAY_API_KEY | Background music API | — |
| BRAVE_API_KEY | Web search for RAG research | — |

## Scheduler

The publish scheduler runs every minute (configurable). It picks up pipeline runs with `status=pending` and `status=failed` (under retry limit) and processes them through the pipeline.

The automation scheduler runs daily to auto-create new pipeline runs for channels with automation enabled.

The Instagram scheduler retries failed Instagram cross-posts up to 3 times, 24 h apart.

## Database

Uses SQLAlchemy async (asyncpg for PostgreSQL, aiosqlite for SQLite). Schema is managed by Alembic migrations.

Tables: channels, topics, research, scripts, videos, thumbnails, uploads, analytics, agent_logs, users, quality_reports, storyboards, voices, pipeline_runs, channel_automations, chat_sessions, chat_messages, chat_unresolved, knowledge_docs.

## Storage

All generated files are stored locally under `storage/`:
- `storage/audio/` — voice narration WAV files
- `storage/videos/` — rendered MP4 files
- `storage/thumbnails/` — thumbnail images
- `storage/scripts/` — script text files
- `storage/frames/` — video frame images
- `storage/music/` — background music

## Dashboard

Web dashboard at `/dashboard` (requires DASHBOARD_AUTH_TOKEN if set).

Features:
- Trigger new pipeline runs manually
- View scheduler status (tick, due count, succeeded, failed)
- Monitor pipeline runs with stage-by-stage progress
- View upload queue and recently uploaded videos
- Channel automation management
- Notification configuration
- Studio Assistant chatbot

## Troubleshooting Common Issues

### Pipeline fails at Voice stage
- Check that `VOICE_PROVIDER` is set to `gtts` if Kokoro is not available
- Verify `storage/audio/` directory exists and is writable
- Check the Voice agent logs for specific error messages

### Pipeline fails at Video stage
- Usually caused by missing audio file from Voice stage
- Check that the Voice agent wrote the file path to the database before the Video agent ran
- Verify FFmpeg is installed (`ffmpeg -version`)
- Check `storage/videos/` is writable

### YouTube upload fails
- Verify `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` are set
- OAuth tokens expire — re-run the auth script to get a new refresh token
- Check daily upload quota (10,000 units/day on free tier)

### Instagram cross-posting fails
- Instagram Business Login token expires every 60 days
- Use the Instagram Token Refresh panel in the dashboard to renew it
- The instagram_token_watchdog scheduler auto-refreshes before expiry

### LLM returns empty or low-quality scripts
- Check `LLM_PROVIDER` and the corresponding API key
- Try increasing `max_tokens` in the script agent config
- Lower `QUALITY_MIN_SCORE` temporarily to diagnose
- Check the agent logs for prompt/response details

### Scheduler not running
- Verify `RUN_INTERNAL_SCHEDULERS=true` (default in production)
- Check the scheduler status panel for last tick time
- Look for errors in application logs at startup

## Adding a New Channel

1. POST to `/api/v1/channels` with `{"name": "My Channel", "youtube_channel_id": "UCxxxxxx"}`
2. POST to `/api/v1/topics` with `{"channel_id": "<id>", "title": "Topic Name", "description": "..."}`
3. Trigger a pipeline run from the dashboard or wait for the automation scheduler

## API Keys Overview

All API keys have free tiers sufficient for moderate use:
- **Groq**: Fast inference, free tier with rate limits
- **Gemini**: Google AI, free tier available
- **Pexels**: 200 requests/hour, 20,000/month
- **Pixabay**: 5,000 requests/hour
- **Brave Search**: 2,000 queries/month
- **YouTube Data API**: 10,000 units/day (uploads cost ~1,600 units each)
