import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings
from app.web.auth import require_dashboard_auth
from app.core.exceptions import (
    YouTubeStudioException,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    PipelineError,
    PublishError,
)
from app.core.logging import get_logger, setup_logging
from app.database.connection import init_db, close_db
from app.llm_providers.factory import get_llm_provider

logger = get_logger(__name__)


def _client_ip(request: Request) -> str:
    """Prefer real client IP behind Caddy / reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return get_remote_address(request) or "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()

    logger.info(
        "Starting Autonomous YouTube Studio",
        env=settings.app_env,
    )

    await init_db()
    logger.info("Database ready")

    from app.agents.video_agent.video_hook_overlay_patch import apply_video_hook_overlay_patch
