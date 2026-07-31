# Configuration Reference

All settings are read from environment variables (or `.env` file).

## Core Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development`, `testing`, `production` |
| `APP_DEBUG` | `true` | Enable debug mode |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (local PostgreSQL) | PostgreSQL connection string |

## LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `mock` | `ollama`, `gemini`, `openai`, `anthropic`, `mock` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5-script:latest` | Model name |
| `OLLAMA_NUM_THREADS` | `4` | CPU threads for inference |
| `OLLAMA_NUM_CTX_SMALL` | `4096` | Context window (short scripts) |
| `OLLAMA_NUM_CTX_LARGE` | `8192` | Context window (long scripts) |

## YouTube

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_API_KEY` | `` | Read-only API key (analytics) |
| `YOUTUBE_CLIENT_ID` | `` | OAuth2 client ID (upload) |
| `YOUTUBE_CLIENT_SECRET` | `` | OAuth2 client secret |
| `YOUTUBE_REFRESH_TOKEN` | `` | Long-lived refresh token |

## Stock Media

| Variable | Default | Description |
|----------|---------|-------------|
| `PEXELS_API_KEY` | `` | Pexels API key (stock photos) |
| `PIXABAY_API_KEY` | `` | Pixabay API key (music + photos) |
| `USE_STOCK_PHOTOS` | `true` | Try Pexels before AI image generation |

## Voice

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_PROVIDER` | `auto` | `auto`, `kokoro`, `gtts`, `pyttsx3` |
| `VOICE_GENDER` | `female` | `female` or `male` |
| `VOICE_ENABLED` | `false` | Enable voice stage in pipeline |

## Background Music

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKGROUND_MUSIC_ENABLED` | `true` | Mix music under voice |
| `BACKGROUND_MUSIC_VOLUME_DB` | `-18.0` | Music volume in dBFS (lower = quieter) |
| `BACKGROUND_MUSIC_FADE_IN_MS` | `1000` | Fade-in duration (ms) |
| `BACKGROUND_MUSIC_FADE_OUT_MS` | `1500` | Fade-out duration (ms) |

## Captions

| Variable | Default | Description |
|----------|---------|-------------|
| `CAPTION_STYLE` | `karaoke` | `karaoke` (word-highlight) or `static` |
| `KARAOKE_HIGHLIGHT_COLOR` | `#FFD700` | Active word colour (gold) |
| `KARAOKE_BASE_COLOR` | `#FFFFFF` | Inactive word colour (white) |

## Video Quality

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEO_QUALITY_PRESET` | `high` | `draft`, `standard`, `high`, `cinematic` |
| `ENABLE_TRANSITIONS` | `true` | Cross-fade between scenes |
| `ENABLE_KEN_BURNS` | `true` | Subtle zoom/pan on background images |
| `ENABLE_IMAGE_ENHANCE` | `true` | PIL sharpness boost on AI images |
| `ENABLE_CINEMATIC_OVERLAY` | `true` | Dark gradient overlay for readability |
| `TEXT_STYLE_PROFILE` | `modern` | `modern`, `classic`, `bold` |

## Quality Gates

| Variable | Default | Description |
|----------|---------|-------------|
| `QUALITY_MIN_SCORE` | `85` | Minimum quality score (0–100) |
| `SEO_MIN_SCORE` | `60` | Minimum SEO score |
| `ENGAGEMENT_MIN_SCORE` | `65` | Minimum engagement score |

## Automation

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_GENERATE` | `true` | Auto-generate videos on schedule |
| `AUTO_UPLOAD` | `false` | Auto-upload approved videos |
| `AUTO_PUBLISH_ENABLED` | `true` | Auto-approve videos passing QA |
| `PIPELINE_PUBLISH_DELAY_MINUTES` | `15` | Delay between approval and upload |
| `SCHEDULER_INTERVAL_MINUTES` | `5` | Publish scheduler tick interval |
| `AUTOMATION_CHECK_INTERVAL_MINUTES` | `60` | Daily automation tick interval |
| `AUTOMATION_MAX_CONCURRENT_CHANNELS` | `1` | Parallel channel pipelines |

## Retry Handling

| Variable | Default | Description |
|----------|---------|-------------|
| `RETRY_MAX_RETRIES` | `3` | Pipeline stage retry limit |
| `RETRY_BASE_BACKOFF_SECONDS` | `30` | First backoff (doubles each attempt) |
| `SCHEDULER_MAX_RETRIES` | `3` | Upload scheduler retry limit |
| `SCHEDULER_BASE_BACKOFF_SECONDS` | `60` | First upload retry backoff |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | `json` or `plain` |
