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
        validation_alias=AliasChoices("app_secret_key", "APP_SECRET_KEY", "SESSION_SECRET"),
    )
    app_host: str = "0.0.0.0"
    app_port: int = 5000

    # Database
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
        if v and "localhost" not in v:
            return v
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

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-script:latest"
    ollama_num_threads: int = 4
    ollama_num_ctx_small: int = 4096
    ollama_num_ctx_large: int = 8192

    # YouTube API
    youtube_api_key: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_redirect_uri: str = ""
    youtube_category_id: str = "27"
    # Refresh-token lifetime tracking (Testing apps often ~7 days)
    youtube_token_issued_at: str = ""  # YYYY-MM-DD
    youtube_token_lifetime_days: int = 7
    youtube_token_warn_days: int = 2
    youtube_token_check_hours: int = 12

    # Stock Media APIs (free tier)
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    use_stock_photos: bool = True

    jamendo_client_id: str = ""

    voice_provider: str = "auto"
    voice_gender: str = "female"

    background_music_enabled: bool = True
    background_music_volume_db: float = -22.0  # voice-first Shorts mix; was -18
    background_music_fade_in_ms: int = 1000
    background_music_fade_out_ms: int = 1500

    caption_style: str = "karaoke"
    karaoke_highlight_color: str = "#FFD700"
    karaoke_base_color: str = "#FFFFFF"

    presenter_enabled: bool = False
    presenter_hf_space: str = "kevinwang676/SadTalker"
    presenter_hf_token: str = Field(
        default="",
        validation_alias=AliasChoices("presenter_hf_token", "hf_api_token", "HF_API_TOKEN"),
    )
    did_api_key: str = ""
    presenter_pip_position: str = "bottom-right"
    presenter_pip_size_pct: float = 0.28
    presenter_pip_margin_px: int = 24

    hook_overlay_enabled: bool = True
    hook_overlay_duration_s: float = 1.5

    watermark_enabled: bool = True
    watermark_path: str = "./storage/branding/logo.png"
    watermark_position: str = "top-right"
    watermark_size_pct: float = 0.14
    watermark_opacity: float = 0.55
    watermark_margin_px: int = 20

    end_card_enabled: bool = True
    end_card_text: str = "FOLLOW FOR MORE"
    end_card_duration_s: float = 2.5
    end_card_margin_px: int = 20

    storage_backend: Literal["local", "s3", "minio"] = "local"
    storage_local_path: str = "./storage"
    storage_retention_days: int = 14
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = ""
    aws_region: str = "ap-south-1"

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

    notification_whatsapp_enabled: bool = False
    whatsapp_phone: str = ""
    whatsapp_apikey: str = ""

    smtp_user: str = ""
    smtp_password: str = ""

    @model_validator(mode="after")
    def _auto_enable_notifications(self) -> "Settings":
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
    instagram_token_issued_at: str = ""
    instagram_token_warn_days: int = 2
    instagram_app_secret: str = Field(
        default="",
        validation_alias=AliasChoices("instagram_app_secret", "INSTAGRAM_APP_SECRET"),
    )
    public_base_url: str = ""

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "YouTubeStudio/1.0"

    auto_generate: bool = True
    auto_upload: bool = False
    auto_analytics: bool = True
    auto_optimization: bool = True

    quality_min_score: int = 70
    quality_min_score_short: int = 55
    seo_min_score: int = 60
    engagement_min_score: int = 65

    low_ram_mode: bool = False

    # Long-form under LOW_RAM (1 GB + swap): allowed with hard caps
    allow_long_form_on_low_ram: bool = True
    low_ram_long_max_duration_s: float = 480.0  # 8 minutes
    low_ram_long_max_scenes: int = 30
    low_ram_long_target_fps: int = 24

    video_quality_preset: Literal["draft", "standard", "high", "cinematic"] = "high"
    enable_transitions: bool = True
    enable_ken_burns: bool = True
    enable_image_enhance: bool = True
    enable_cinematic_overlay: bool = True
    text_style_profile: Literal["modern", "classic", "bold"] = "modern"
    image_prompt_enhance: bool = True

    @model_validator(mode="after")
    def _apply_low_ram_mode(self) -> "Settings":
        """Clamp heavy settings when running on ~1 GB VMs (Oracle Micro)."""
        if not self.low_ram_mode:
            return self
        self.caption_style = "static"
        if self.video_quality_preset in ("high", "cinematic"):
            self.video_quality_preset = "draft"
        self.enable_ken_burns = False
        self.enable_transitions = False
        return self

    pipeline_publish_delay_minutes: int = 15
    auto_publish_enabled: bool = True

    scheduler_interval_minutes: int = 5
    scheduler_trigger_secret: str = ""
    run_internal_schedulers: bool = True

    retry_max_retries: int = 3
    retry_base_backoff_seconds: int = 30

    scheduler_max_retries: int = 3
    scheduler_base_backoff_seconds: int = 60

    rag_research_enabled: bool = False
    rag_search_max_results: int = 5
    rag_crawl_timeout_seconds: int = 10
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_chunks_per_topic: int = 3
    rag_vector_db_path: str = "./storage/vector_db"
    serper_api_key: str = ""
    brave_api_key: str = ""

    jwt_secret_key: str = Field(
        default="jwt-dev-secret",
        validation_alias=AliasChoices(
            "jwt_secret_key", "JWT_SECRET_KEY", "APP_SECRET_KEY", "SESSION_SECRET"
        ),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    dashboard_auth_token: str = ""

    automation_max_concurrent_channels: int = 1
    automation_check_interval_minutes: int = 60
    automation_shorts_only_days: int = 15

    dev_auto_create_tables: bool = False

    voice_enabled: bool = False
    voice_max_heal_attempts: int = 2

    log_level: str = "INFO"
    log_format: str = "json"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
