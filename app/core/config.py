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

    app_name: str = "Autonomous YouTube Studio"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me-in-production"
    jwt_secret_key: str = "jwt-dev-secret"
    dashboard_auth_token: str = ""

    database_url: str = "sqlite+aiosqlite:///./youtube_studio.db"
    database_sync_url: str = "sqlite:///./youtube_studio.db"

    groq_api_key: str = ""
    gemini_api_key: str = ""
    llm_provider: str = "groq"

    storage_local_path: str = "./storage"
    storage_retention_days: int = 14

    background_music_enabled: bool = True
    background_music_volume_db: float = -22.0
    background_music_fade_in_ms: int = 1000
    background_music_fade_out_ms: int = 1500
    jamendo_client_id: str = ""

    low_ram_mode: bool = False
    video_quality_preset: str = "standard"
    caption_style: str = "karaoke"
    enable_ken_burns: bool = True
    enable_transitions: bool = True
    enable_cinematic_overlay: bool = True
    text_style_profile: str = "modern"
    presenter_enabled: bool = False
    run_internal_schedulers: bool = True

    hook_overlay_enabled: bool = True
    hook_overlay_duration_s: float = 1.5
    end_card_enabled: bool = True
    end_card_duration_s: float = 1.5
    end_card_text: str = "FOLLOW FOR MORE"
    watermark_enabled: bool = True
    watermark_path: str = ""
    watermark_opacity: float = 0.55
    watermark_size_pct: float = 0.14
    watermark_margin_px: int = 20
    watermark_position: str = "top-right"

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def _async_db(cls, v: str) -> str:
        if not v:
            return v
        return _make_async_url(str(v))

    @model_validator(mode="after")
    def _sync_db(self):
        if self.database_url:
            object.__setattr__(self, "database_sync_url", _make_sync_url(self.database_url))
        if self.low_ram_mode:
            object.__setattr__(self, "caption_style", "static")
            object.__setattr__(self, "video_quality_preset", "draft")
            object.__setattr__(self, "enable_ken_burns", False)
            object.__setattr__(self, "enable_transitions", False)
            object.__setattr__(self, "presenter_enabled", False)
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
