# Autonomous YouTube Studio

A fully automated YouTube content pipeline — from topic research to upload — powered by FastAPI, AI agents, and multiple LLM/TTS/media integrations.

## Stack

- **Backend**: Python 3.12 · FastAPI · Uvicorn
- **Database**: PostgreSQL (Replit managed) via SQLAlchemy async + Alembic migrations
- **LLM**: Groq (llama-3.3-70b-versatile) with Gemini as automatic fallback
- **TTS**: Kokoro ONNX (high-quality, primary) → gTTS (fallback)
- **Video**: MoviePy + FFmpeg 7.1.1
- **Scheduler**: APScheduler (publish, automation, Instagram cross-post)

## Run

The `Start application` workflow handles this automatically. It runs:

```
python3 -m alembic upgrade head && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

## Setup after a fresh clone

1. Install dependencies: `pip install -r requirements.txt`
2. Set required secrets (see below)
3. Set non-secret env vars (see below)
4. Run migrations: `python3 -m alembic upgrade head`
5. Start: `python3 -m uvicorn app.main:app --host 0.0.0.0 --port 5000`

Kokoro TTS model files (~116 MB) are committed to the repo — no separate download needed.

## Non-secret environment variables

| Key | Value | Notes |
|-----|-------|-------|
| `APP_ENV` | `production` | |
| `LLM_PROVIDER` | `groq` | groq → gemini fallback chain |
| `VOICE_ENABLED` | `true` | Enable voice stage in pipeline |
| `AUTO_UPLOAD` | `true` | Auto-upload to YouTube after render |
| `VOICE_PROVIDER` | `auto` | auto → kokoro → gtts → pyttsx3 |
| `CAPTION_STYLE` | `karaoke` | word-by-word karaoke captions |
| `USE_STOCK_PHOTOS` | `true` | Pexels before Pollinations AI |
| `BACKGROUND_MUSIC_ENABLED` | `true` | Jamendo background music |

## Secrets required

### Required (pipeline fails without these)
- `DASHBOARD_AUTH_TOKEN` — dashboard login password
- `GROQ_API_KEY` **or** `GEMINI_API_KEY` — at least one LLM key required

### YouTube upload
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

### Security (strongly recommended in production)
- `JWT_SECRET_KEY` — signs session tokens; falls back to `SESSION_SECRET` if unset
- `SESSION_SECRET` — app session key (Replit injects this automatically)

### Optional integrations
- `PEXELS_API_KEY` — stock photo search
- `PIXABAY_API_KEY` — additional stock footage
- `JAMENDO_CLIENT_ID` — background music
- `HF_API_TOKEN` — presenter/talking-head avatar via Hugging Face
- `SLACK_WEBHOOK_URL` — Slack failure/success notifications (auto-enabled when set)
- `DISCORD_WEBHOOK_URL` — Discord notifications (auto-enabled when set)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — both required for Telegram notifications
- `NOTIFICATION_EMAIL_FROM`, `NOTIFICATION_EMAIL_PASSWORD`, `NOTIFICATION_EMAIL_TO` — email (auto-enabled when all three are set)
- `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`, `INSTAGRAM_APP_SECRET` — Instagram cross-post (auto-enabled when first two are set)
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Reddit cross-post

## Agents

| Agent | Purpose |
|-------|---------|
| `topic_agent` | Discover trending topics via Reddit + YouTube |
| `seo_agent` | Title / description / tags optimisation |
| `short_script_agent` | ~60 s Shorts script generation |
| `long_script_agent` | 8+ min script (2000–2400 words) |
| `voice_agent` | Kokoro TTS narration synthesis |
| `thumbnail_agent` | AI thumbnail generation (Pollinations FLUX) |
| `video_agent` | Full video rendering (MoviePy + FFmpeg) |
| `upload_agent` | YouTube Data API v3 upload |
| `quality_agent` | Pre-upload quality gate scoring |
| `analytics_agent` | Post-upload performance tracking |
| `pipeline_agent` | Orchestrates all stages with retry + DB session management |

## Database

Migrations live in `app/database/migrations/versions/`. Schema is always at head on startup (alembic runs automatically in the workflow command).

## Optional: RAG research

Set `RAG_RESEARCH_ENABLED=true` and install extra deps:

```
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-rag.txt
```

## Optional: Celery distributed workers

`app/workflows/scheduler.py` defines Celery Beat tasks. Celery is **not** installed by default — the app uses APScheduler instead. Install with `pip install celery[redis]` and configure `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` only if you need distributed workers.

## User Preferences

- Keep the existing project structure — do not restructure or migrate the stack.
- Use `installLanguagePackages` (not bare `pip`) for Python package installs.
- LLM provider is Groq with Gemini fallback; do not switch to mock unless testing.
