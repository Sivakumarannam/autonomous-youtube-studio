import os
from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, field_validator, model_validator


def _strip_sslmode(url: str) -> str:
    """Remove sslmode query param (not supported by asyncpg driver)."""
    if "sqlite" in url:
        return url
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


def _make_async_url(url: str) -> str:
    url = _strip_sslmode(url)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


def _make_sync_url(url: str) -> str:
    url = _strip_sslmode(url)
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Autonomous YouTube Studio"
    app_env: Literal["development", "testing", "production"] = "development"
    app_debug: bool = True
    app_secret_key: str = Field(
        default="dev-secret-key",
        # Accept APP_SECRET_KEY or SESSION_SECRET (Replit injects SESSION_SECRET
        # automatically; either name works so nothing needs renaming).
        validation_alias=AliasChoices("app_secret_key", "APP_SECRET_KEY", "SESSION_SECRET"),
    )
    app_host: str = "0.0.0.0"
    app_port: int = 5000

    # Database
    # Dev default: SQLite (zero-config, works out-of-the-box on Replit).
    # Production: set DATABASE_URL=postgresql://... env var and the validator
    # below will convert it to the asyncpg dialect automatically.
    database_url: str = "sqlite+aiosqlite:///./youtube_studio.db"
    database_sync_url: str = "sqlite:///./youtube_studio.db"

    @model_validator(mode="after")
    def _fix_database_urls(self) -> "Settings":
        raw = os.environ.get("DATABASE_URL", "") or self.database_url
        if raw:
            self.database_url = _make_async_url(raw)
            self.database_sync_url = _make_sync_url(raw)
        return self

    @field_validator("youtube_redirect_uri", mode="before")
    @classmethod
    def _resolve_redirect_uri(cls, v: str) -> str:
        """Use REPLIT_DEV_DOMAIN when running on Replit; fall back to localhost."""
        if v and "localhost" not in v:
            return v  # explicitly set to a real URL — trust it
        dev_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
        if dev_domain:
            return f"https://{dev_domain}/auth/callback"
        return v or "http://localhost:8000/auth/callback"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # LLM Provider
    llm_provider: Literal[
        "mock",
        "gemini",
        "openai",
        "anthropic",
        "ollama",
        "groq",
    ] = "mock"

    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Groq (free tier — 14,400 req/day, no credit card required)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-script:latest"

    # Recommended for your i5-1135G7
    ollama_num_threads: int = 4

    # Context windows
    ollama_num_ctx_small: int = 4096
    ollama_num_ctx_large: int = 8192

    # YouTube API
    youtube_api_key: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_redirect_uri: str = ""  # resolved dynamically — see validator below
    # YouTube video category ID. "27" = Education — better algorithmic
    # fit for a facts/trivia channel than the previous default "22"
    # (People & Blogs). Full list: developers.google.com/youtube/v3/docs/videoCategories
    youtube_category_id: str = "27"

    # ------------------------------------------------------------------
    # Stock Media APIs (free tier)
    # ------------------------------------------------------------------
    # Pexels: free stock photos/videos — https://www.pexels.com/api/
    pexels_api_key: str = ""
    # Pixabay: free stock photos/music — https://pixabay.com/api/docs/
    pixabay_api_key: str = ""
    # Whether to try Pexels before falling back to Pollinations AI
    use_stock_photos: bool = True

    # ------------------------------------------------------------------
    # Background Music (Jamendo — automated free-music fallback)
    # Free client_id at https://devportal.jamendo.com/
    # Used only if no local tracks are found in storage/music/
    # ------------------------------------------------------------------
    jamendo_client_id: str = ""

    # ------------------------------------------------------------------
    # Voice Provider
    # ------------------------------------------------------------------
    voice_provider: str = "auto"   # "auto" | "kokoro" | "piper" | "gtts" | "pyttsx3"
    voice_gender: str = "female"   # "female" | "male"

    # ------------------------------------------------------------------
    # Background Music
    # ------------------------------------------------------------------
    background_music_enabled: bool = True
    background_music_volume_db: float = -18.0   # dBFS; keep voice dominant
    background_music_fade_in_ms: int = 1000
    background_music_fade_out_ms: int = 1500

    # ------------------------------------------------------------------
    # Captions
    # ------------------------------------------------------------------
    # "karaoke": word-by-word highlighting using Whisper word timestamps
    # "static":  one caption line per scene (original behaviour)
    caption_style: str = "karaoke"   # "karaoke" | "static"
    karaoke_highlight_color: str = "#FFD700"   # gold highlight for active word
    karaoke_base_color: str = "#FFFFFF"        # colour for inactive words


    # ------------------------------------------------------------------
    # AI Presenter (Picture-in-Picture)
    # Provider is chosen at runtime by PRESENTER_PROVIDER env var:
    #   "sadtalker" (default, FREE — hosted HF Space)
    #   "did"       (PAID — D-ID API, use as a fallback if the free
    #                Space becomes unreliable)
    # ------------------------------------------------------------------
    presenter_enabled: bool = False

    # --- sadtalker provider settings (free, default) ---
    # Hugging Face Space id to call. The official "vinthony/SadTalker"
    # Space is currently in a broken "build error" state on HF's side
    # (unrelated to this code — a pinned dependency conflict in its
    # requirements.txt), so this defaults to a community duplicate that
    # is currently live. Verify status at huggingface.co/spaces/<id>
    # before relying on it, and swap in your own duplicated/private
    # Space id here if you want dedicated (non-shared) capacity.
    presenter_hf_space: str = "kevinwang676/SadTalker"
    # Optional HF token (https://huggingface.co/settings/tokens). Not
    # required for public Spaces, but avoids anonymous rate limiting and
    # is required if you duplicate the Space into a private one.
    # Aliased to HF_API_TOKEN so the same secret drives both the presenter
    # and the image-provider HF inference backend.
    presenter_hf_token: str = Field(
        default="",
        validation_alias=AliasChoices("presenter_hf_token", "hf_api_token", "HF_API_TOKEN"),
    )

    # --- did provider settings (paid fallback) ---
    # DID_API_KEY from your D-ID dashboard → API keys. Used as-is in the
    # `Authorization: Basic <key>` header — do not prefix with "Basic "
    # yourself here, that's added in did_presenter.py.
    did_api_key: str = ""

    # --- Still used by the rendering step regardless of provider ---
    # Position of the PiP bubble: "bottom-right" | "bottom-left" |
    # "top-right" | "top-left"
    presenter_pip_position: str = "bottom-right"
    # Bubble width as a fraction of video width (0.28 = 28%)
    presenter_pip_size_pct: float = 0.28
    # Margin from the frame edge, in pixels
    presenter_pip_margin_px: int = 24

    # ------------------------------------------------------------------
    # Hook headline overlay (first ~1.5s, distinct from karaoke captions)
    # ------------------------------------------------------------------
    hook_overlay_enabled: bool = True
    hook_overlay_duration_s: float = 1.5

    # ------------------------------------------------------------------
    # Channel watermark (persistent logo, low opacity, whole video)
    # ------------------------------------------------------------------
    watermark_enabled: bool = True
    # Put a small PNG (ideally transparent background) here — skipped
    # gracefully if the file doesn't exist, same pattern as avatars.
    watermark_path: str = "./storage/branding/logo.png"
    watermark_position: str = "top-right"  # top-right | top-left | bottom-right | bottom-left
    watermark_size_pct: float = 0.14       # width as a fraction of video width
    watermark_opacity: float = 0.55        # 0.0-1.0, low so it doesn't distract
    watermark_margin_px: int = 20

    # ------------------------------------------------------------------
    # End-card CTA (last ~1.5s of every video)
    # ------------------------------------------------------------------
    end_card_enabled: bool = True
    end_card_text: str = "FOLLOW FOR MORE"
    end_card_duration_s: float = 1.5
    end_card_margin_px: int = 20

    # Storage
    storage_backend: Literal["local", "s3", "minio"] = "local"
    storage_local_path: str = "./storage"
    # Days to keep files in storage/videos, storage/audio, and storage/cache
    # before the daily cleanup job deletes them. Only applies to files whose
    # corresponding Video/Upload DB record is already complete/published —
    # see app/scheduler/storage_cleanup_scheduler.py.
    storage_retention_days: int = 14
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = ""
    aws_region: str = "ap-south-1"

    # Notifications
    notification_email_enabled: bool = False
    notification_email_from: str = ""
    notification_email_password: str = ""
    notification_email_to: str = Field(
        default="",
        validation_alias=AliasChoices("notification_email_to", "notify_email_to"),
    )
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    notification_slack_enabled: bool = False
    slack_webhook_url: str = ""

    notification_discord_enabled: bool = False
    discord_webhook_url: str = ""

    notification_telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # WhatsApp via CallMeBot (free — https://www.callmebot.com/blog/free-api-whatsapp-messages/)
    notification_whatsapp_enabled: bool = False
    whatsapp_phone: str = ""
    whatsapp_apikey: str = ""

    # SMTP aliases (smtp_user / smtp_password) used when notification_email_from is not set
    smtp_user: str = ""
    smtp_password: str = ""

    @model_validator(mode="after")
    def _auto_enable_notifications(self) -> "Settings":
        """Auto-enable notification channels when credentials are present."""
        if not self.notification_email_enabled:
            sender = self.notification_email_from or self.smtp_user
            password = self.notification_email_password or self.smtp_password
            if sender and password and self.notification_email_to:
                self.notification_email_enabled = True
        if not self.notification_slack_enabled and self.slack_webhook_url:
            self.notification_slack_enabled = True
        if not self.notification_discord_enabled and self.discord_webhook_url:
            self.notification_discord_enabled = True
        if not self.notification_telegram_enabled and self.telegram_bot_token and self.telegram_chat_id:
            self.notification_telegram_enabled = True
        if not self.notification_whatsapp_enabled and self.whatsapp_phone and self.whatsapp_apikey:
            self.notification_whatsapp_enabled = True
        if not self.instagram_enabled and self.meta_access_token and self.instagram_business_account_id:
            self.instagram_enabled = True
        return self

    # Instagram automation
    # Secrets: INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID
    instagram_enabled: bool = False
    instagram_business_account_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "instagram_business_account_id",
            "INSTAGRAM_BUSINESS_ACCOUNT_ID",
        ),
    )
    meta_access_token: str = Field(
        default="",
        validation_alias=AliasChoices("meta_access_token", "instagram_access_token"),
    )
    # Used for Instagram webhook signature verification (not required for basic posting)
    instagram_app_secret: str = Field(
        default="",
        validation_alias=AliasChoices("instagram_app_secret", "INSTAGRAM_APP_SECRET"),
    )

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "YouTubeStudio/1.0"

    # Autonomous Mode
    auto_generate: bool = True
    auto_upload: bool = False
    auto_analytics: bool = True
    auto_optimization: bool = True

    # Quality Control
    quality_min_score: int = 70  # minimum score for long scripts
    quality_min_score_short: int = 55  # separate (lower) bar for short scripts
    seo_min_score: int = 60
    engagement_min_score: int = 65

    # ------------------------------------------------------------------
    # Video Quality Settings
    #
    # video_quality_preset:  "draft" (ultrafast/18fps), "standard" (medium/24fps),
    #                        "high" (slow/24fps), "cinematic" (slow/24fps + 2-pass).
    #                        Default "standard" balances quality and encode time.
    # enable_transitions:    Cross-fade between scenes (0.35 s dissolve).
    # enable_ken_burns:      Subtle zoom/pan effect on static image backgrounds.
    # enable_image_enhance:  PIL sharpness + contrast boost after AI image fetch.
    # enable_cinematic_overlay: Dark gradient overlay on backgrounds for readability.
    # text_style_profile:    "modern" (shadow+stroke), "classic" (plain), "bold".
    # image_prompt_enhance:  Append quality keywords to AI image prompts.
    # ------------------------------------------------------------------
    video_quality_preset: Literal["draft", "standard", "high", "cinematic"] = "high"
    enable_transitions: bool = True
    enable_ken_burns: bool = True
    enable_image_enhance: bool = True
    enable_cinematic_overlay: bool = True
    text_style_profile: Literal["modern", "classic", "bold"] = "modern"
    image_prompt_enhance: bool = True

    # Pipeline / Publishing
    # Delay between quality approval and Scheduler firing the actual YouTube upload.
    # Provides a manual-reject safety window. Configurable via env var.
    # Reduced to 15 minutes for local testing so uploads appear sooner.
    pipeline_publish_delay_minutes: int = 15

    # When True, pipeline auto-approves videos that pass quality and sets
    # scheduled_at = now() + pipeline_publish_delay_minutes.
    # Set to False to require a manual /approve API call instead.
    auto_publish_enabled: bool = True

    # Scheduler
    # How often (in minutes) the publish scheduler checks for due videos.
    scheduler_interval_minutes: int = 5
    scheduler_trigger_secret: str = ""
    run_internal_schedulers: bool = True   # set False via env var on Cloud Run

    # ------------------------------------------------------------------
    # Retry Manager — Surface A (Pipeline stages)
    #
    # retry_max_retries:         Max attempts before a PipelineRun is marked
    #                            permanently FAILED.  Stored on each new run so
    #                            in-flight runs are not affected by config changes.
    # retry_base_backoff_seconds: First backoff interval.  Doubles each attempt:
    #                            30 s → 60 s → 120 s …
    # ------------------------------------------------------------------
    retry_max_retries: int = 3
    retry_base_backoff_seconds: int = 30

    # ------------------------------------------------------------------
    # Retry Manager — Surface B (Scheduler upload call)
    #
    # Separate from the pipeline values because the scheduler runs
    # unattended and large YouTube uploads need a longer initial cooldown
    # before a 429/503 response is retried productively.  Starts at 60 s
    # (doubled from the pipeline's 30 s) so the sequence is:
    # 60 s → 120 s → 240 s …
    # ------------------------------------------------------------------
    scheduler_max_retries: int = 3
    scheduler_base_backoff_seconds: int = 60

    # ------------------------------------------------------------------
    # RAG Research (Phase 4)
    #
    # Disabled by default — set RAG_RESEARCH_ENABLED=true to activate.
    # When enabled, the script agents run a Search→Crawl→Extract→Embed→Store
    # pipeline before generation and inject the retrieved context into the
    # prompt.  Any failure falls back gracefully (warning logged, no crash).
    #
    # rag_research_enabled:        Master on/off switch.
    # rag_search_max_results:      URLs to fetch per topic (1-10 recommended).
    # rag_crawl_timeout_seconds:   Per-URL fetch timeout.
    # rag_chunk_size:              Characters per text chunk before embedding.
    # rag_chunk_overlap:           Overlap between consecutive chunks.
    # rag_chunks_per_topic:        Chunks to inject into the script prompt.
    # rag_vector_db_path:          Directory for FAISS index + SQLite metadata.
    # serper_api_key:              Optional Serper.dev key (paid Google results).
    # brave_api_key:               Optional Brave Search key.
    # ------------------------------------------------------------------
    rag_research_enabled: bool = False
    rag_search_max_results: int = 5
    rag_crawl_timeout_seconds: int = 10
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_chunks_per_topic: int = 3
    rag_vector_db_path: str = "./storage/vector_db"
    serper_api_key: str = ""
    brave_api_key: str = ""

    # JWT
    jwt_secret_key: str = Field(
        default="jwt-dev-secret",
        # Accept JWT_SECRET_KEY (preferred) or fall back to APP_SECRET_KEY /
        # SESSION_SECRET so a single shared secret covers both until a
        # dedicated JWT key is set.
        validation_alias=AliasChoices(
            "jwt_secret_key", "JWT_SECRET_KEY", "APP_SECRET_KEY", "SESSION_SECRET"
        ),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Dashboard / Metrics auth (Phase 5 follow-up)
    # Minimal shared-secret guard scoped ONLY to /dashboard and /metrics.
    # Does not affect the JWT-based auth used elsewhere in the app.
    dashboard_auth_token: str = ""

    # ------------------------------------------------------------------
    # Channel Automation (Phase 6) — Daily Automation Scheduler
    #
    # automation_max_concurrent_channels: asyncio.Semaphore size limiting
    #   how many channels' daily pipelines run concurrently, given this
    #   machine's 2-physical-core constraint. A channel whose semaphore
    #   acquire would block is skipped and retried on the next tick — the
    #   scheduler never blocks waiting.
    # automation_check_interval_minutes: how often the Daily Automation
    #   Scheduler ticks. Separate job/interval from the existing Publish
    #   Scheduler (scheduler_interval_minutes).
    # automation_shorts_only_days: cumulative_active_days threshold. At or
    #   below this value only a Short is created each processing day; above
    #   it, a Short is always created plus a conditional Long.
    # ------------------------------------------------------------------
    automation_max_concurrent_channels: int = 1
    automation_check_interval_minutes: int = 60
    automation_shorts_only_days: int = 15

    # ------------------------------------------------------------------
    # Schema management
    #
    # dev_auto_create_tables: when True, init_db() calls
    #   Base.metadata.create_all() at startup (old behaviour).
    #   This is a dev-only convenience flag for throw-away environments
    #   where running Alembic migrations is inconvenient.
    #   Alembic migrations are the ONLY mechanism for schema changes in
    #   staging/production — never set this to True outside local dev.
    # ------------------------------------------------------------------
    dev_auto_create_tables: bool = False

    # ------------------------------------------------------------------
    # Voice Stage (self-healing) — PipelineAgentService
    #
    # Voice generation is not invoked by the pipeline today; VideoAgentService
    # only passively looks up whatever Voice record happens to exist, so every
    # video renders silent unless a Voice record was created out-of-band.
    #
    # voice_enabled: gates the new pipeline stage entirely. Default False
    #   means zero behaviour change for any existing deployment until this is
    #   explicitly turned on.
    # voice_max_heal_attempts: local retry cap used ONLY inside
    #   _run_voice_stage() for artifact-incompleteness (VoiceAgentService
    #   returns without raising but the Voice record is not COMPLETE). This
    #   is a plain local counter — it is never written to
    #   PipelineRun.retry_count and never interacts with is_retryable_error();
    #   technical failures (exceptions) still propagate to the existing outer
    #   retry loop in run(), unchanged.
    # ------------------------------------------------------------------
    voice_enabled: bool = False
    voice_max_heal_attempts: int = 2

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()