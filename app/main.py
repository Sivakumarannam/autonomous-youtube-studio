import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()

    logger.info(
        "Starting Autonomous YouTube Studio",
        env=settings.app_env,
    )

    # Initialize database
    await init_db()
    logger.info("Database ready")

    from app.agents.video_agent.video_hook_bootstrap import apply_video_hook_overlay_patch
    apply_video_hook_overlay_patch()

    from app.agents.video_agent.caption_clip_bootstrap import apply_caption_clip_patch
    apply_caption_clip_patch()

    try:
        from app.core.low_ram_bootstrap import apply_low_ram_patches
        apply_low_ram_patches()
    except Exception:
        pass

    # ── Security: warn loudly if JWT_SECRET_KEY is still the dev default ──
    # The default "jwt-dev-secret" is public knowledge (it's in the source
    # code). Any deployment that reaches this with the default intact has a
    # forged-token vulnerability. Crash in production; warn in development.
    _JWT_DEV_DEFAULT = "jwt-dev-secret"
    if settings.jwt_secret_key == _JWT_DEV_DEFAULT:
        _msg = (
            "SECURITY: JWT_SECRET_KEY is the hardcoded dev default "
            f'("{_JWT_DEV_DEFAULT}"). Set a strong random JWT_SECRET_KEY '
            "environment variable / secret immediately — JWTs can be forged."
        )
        if settings.app_env == "production":
            raise RuntimeError(_msg)
        else:
            logger.warning(_msg)

    # Reconcile pipeline runs orphaned by a container restart/redeploy.
    # Any row still marked RUNNING at this point cannot be genuinely
    # in-flight — this is a fresh process — so it was abandoned when the
    # previous container stopped mid-render. Left alone, these permanently
    # block automation for their channel (see has_running_for_channel() in
    # the automation scheduler), with no timeout to recover on its own.
    from sqlalchemy import select as _select

    from app.database.connection import get_session_factory as _get_session_factory
    from app.database.models.pipeline_run import PipelineRun as _PipelineRun
    from app.database.models.pipeline_run import PipelineStatus as _PipelineStatus

    try:
        _session_factory = _get_session_factory()
        async with _session_factory() as _session:
            _result = await _session.execute(
                _select(_PipelineRun).where(
                    _PipelineRun.status == _PipelineStatus.RUNNING
                )
            )
            _orphaned_runs = _result.scalars().all()
            for _run in _orphaned_runs:
                _run.status = _PipelineStatus.FAILED
                _run.failed_stage = _run.current_stage or "unknown"
                _run.current_stage = None
                _run.error_message = (
                    "Orphaned by a container restart/redeploy while this "
                    "run was in progress (found stuck at status=running on "
                    "startup)."
                )
            if _orphaned_runs:
                await _session.commit()
                logger.warning(
                    "Reconciled orphaned pipeline run(s) found stuck at "
                    "status=running from a previous process lifetime.",
                    count=len(_orphaned_runs),
                    pipeline_run_ids=[str(_r.id) for _r in _orphaned_runs],
                )
    except Exception as _exc:
        logger.error(
            "Startup pipeline-run reconciliation failed — any stuck runs "
            "from a previous process will remain stuck.",
            error=str(_exc),
        )

    # Ensure all required storage directories exist before any agent runs.
    # This is idempotent — safe to call on every boot.
    from pathlib import Path as _Path
    _base = _Path(settings.storage_local_path)
    for _subdir in (
        "audio", "videos", "thumbnails",
        "scripts/short", "scripts/long",
        "image_cache", "vector_db",
        "presenter", "frames",
        "branding", "music", "avatars",
    ):
        (_base / _subdir).mkdir(parents=True, exist_ok=True)
    logger.info("Storage directories ready", base=str(_base))

    # Run startup validation — logs warnings/errors but never prevents boot
    try:
        from app.core.health import run_all as _health_check
        await _health_check()
    except Exception as _hc_exc:
        logger.warning("Startup health check failed", error=str(_hc_exc))

    # Initialize LLM provider
    provider = get_llm_provider()
    logger.info(
        "LLM provider initialized",
        provider=provider.provider_name,
    )

    # ── Auto-seed chatbot knowledge base ───────────────────────────────────
    # Ingest the project overview doc on first boot (idempotent — skipped if
    # any KnowledgeDocs already exist in the DB).
    try:
        from pathlib import Path as _KbPath
        from app.database.connection import get_session_factory as _chat_sf
        from app.chatbot.knowledge_base import ingest_document as _ingest_doc, has_any_knowledge_docs as _has_kb
        _chat_session_factory = _chat_sf()
        async with _chat_session_factory() as _chat_db:
            if not await _has_kb(_chat_db):
                _overview = _KbPath("docs/project_overview.md")
                if _overview.exists():
                    await _ingest_doc(
                        session=_chat_db,
                        title="Project Overview & Pipeline",
                        text=_overview.read_text(encoding="utf-8"),
                        source_type="auto_seed",
                    )
                    logger.info("Chatbot KB seeded with project_overview.md")
    except Exception as _kb_exc:
        logger.warning("Chatbot KB auto-seed failed (non-fatal)", error=str(_kb_exc))

    # Start publish scheduler
    from app.scheduler.scheduler import get_scheduler
    scheduler = get_scheduler()

    # Start daily automation scheduler (Phase 6) — separate job/interval
    # from the publish scheduler above.
    from app.scheduler.automation_scheduler import get_automation_scheduler
    automation_scheduler = get_automation_scheduler()

    # Start Instagram 24-h cross-post scheduler
    from app.scheduler.instagram_scheduler import get_instagram_scheduler
    ig_scheduler = get_instagram_scheduler()

    # Start daily storage cleanup scheduler — removes old files from
    # storage/videos, storage/audio, storage/cache once past retention
    # (settings.storage_retention_days), skipping anything still in use
    # by an in-progress or unpublished pipeline run.
    from app.scheduler.storage_cleanup_scheduler import get_storage_cleanup_scheduler
    storage_cleanup_scheduler = get_storage_cleanup_scheduler()

    # Start daily Instagram token watchdog — auto-refreshes the long-lived
    # Instagram token before its ~60-day validity expires, and only
    # notifies if that automatic refresh actually fails.
    from app.scheduler.instagram_token_watchdog import get_instagram_token_watchdog
    instagram_token_watchdog = get_instagram_token_watchdog()

    if settings.run_internal_schedulers:
        scheduler.start()
        automation_scheduler.start()
        ig_scheduler.start()
        storage_cleanup_scheduler.start()
        instagram_token_watchdog.start()

    yield

    # Shutdown sequence
    instagram_token_watchdog.shutdown()
    storage_cleanup_scheduler.shutdown()
    ig_scheduler.stop()
    automation_scheduler.shutdown()
    scheduler.shutdown()

    try:
        if hasattr(provider, "close"):
            await provider.close()
            logger.info(
                "LLM provider closed",
                provider=provider.provider_name,
            )
    except Exception:
        logger.exception("Failed to close LLM provider")

    await close_db()

    # Close RAG vector store (releases SQLite connection + FAISS file handle)
    if settings.rag_research_enabled:
        try:
            from app.rag.vector_store import close_vector_store
            close_vector_store()
        except Exception:
            logger.exception("Failed to close RAG vector store")

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AI-powered autonomous YouTube content creation system",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Rate limiting (SlowAPI)
    # ------------------------------------------------------------------

    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    # CORS origins: debug → wildcard (no credentials, safe for local dev);
    # production → must be explicitly listed via the CORS_ORIGINS env var
    # (comma-separated). If it's not set in production, we do NOT fall back
    # to "*" anymore — that combined with allow_credentials=True let any
    # website make authenticated requests using your dashboard session
    # cookie. Same-origin requests (the dashboard calling its own API) and
    # Bearer-token API calls are unaffected either way — this only limits
    # which *other* websites' browsers are allowed to attach your cookie.
    import os as _os
    _cors_env = _os.environ.get("CORS_ORIGINS", "")
    if settings.app_debug:
        _cors_origins: list[str] = ["*"]
        _allow_credentials = False
    elif _cors_env:
        _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
        _allow_credentials = True
    else:
        _cors_origins = []
        _allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # CSRF guard — state-changing requests must originate from the same
    # host (enforced via Origin/Referer) OR carry HX-Request: true
    # (HTMX always sets this header; browsers cannot forge custom headers
    # cross-site, so this is a valid CSRF mitigation for HTMX apps).
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            # /api/* routes: Bearer token auth is itself a CSRF mitigation —
            # a cross-site attacker cannot read the token from another origin,
            # so any request carrying Authorization: Bearer is implicitly safe.
            if path.startswith("/api/"):
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    return await call_next(request)
            # /dashboard/* routes must come from HTMX or same-origin browser
            if path.startswith("/dashboard") or path.startswith("/api/"):
                hx_request = request.headers.get("HX-Request")
                origin = request.headers.get("Origin", "")
                referer = request.headers.get("Referer", "")
                host = request.headers.get("Host", "")
                same_origin = host and (
                    origin.endswith(host) or (referer and host in referer)
                )
                if not hx_request and not same_origin:
                    return JSONResponse(
                        {"detail": "CSRF check failed"},
                        status_code=403,
                    )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Request latency metric (Phase 5, item 4)
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def record_request_latency(request: Request, call_next):
        from app.monitoring.metrics import HTTP_REQUEST_DURATION_SECONDS

        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        route = request.scope.get("route")
        path_label = route.path if route is not None else request.url.path

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            path=path_label,
            status_code=response.status_code,
        ).observe(duration)
        return response

    # ------------------------------------------------------------------
    # Exception Handlers
    # ------------------------------------------------------------------

    @app.exception_handler(NotFoundError)
    async def not_found_handler(
        request: Request,
        exc: NotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(
        request: Request,
        exc: AuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_handler(
        request: Request,
        exc: AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(PipelineError)
    async def pipeline_error_handler(
        request: Request,
        exc: PipelineError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(PublishError)
    async def publish_error_handler(
        request: Request,
        exc: PublishError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(YouTubeStudioException)
    async def studio_exception_handler(
        request: Request,
        exc: YouTubeStudioException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            exc=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        )

    # ------------------------------------------------------------------
    # API Routers
    # ------------------------------------------------------------------

    from app.api.routes.health import router as health_router
    from app.api.routes.channels import router as channels_router
    from app.api.routes.topics import router as topics_router
    from app.api.routes.research import router as research_router
    from app.api.routes.scripts import router as scripts_router
    from app.api.routes.storyboards import router as storyboards_router
    from app.api.routes.thumbnails import router as thumbnails_router
    from app.api.routes.voice import router as voice_router
    from app.api.routes.video import router as video_router
    from app.api.routes.upload import router as upload_router
    from app.api.routes.analytics import router as analytics_router
    from app.api.routes.pipeline import router as pipeline_router
    from app.api.routes.publishing import router as publishing_router
    from app.api.routes.websocket import router as websocket_router
    from app.api.routes.dashboard import router as dashboard_router
    from app.api.routes.channel_automation import router as channel_automation_router
    from app.api.routes.internal_triggers import router as internal_triggers_router 
    # Shared auth dependency applied to every mutable API route
    _auth = [Depends(require_dashboard_auth)]

    # ------------------------------------------------------------------ login
    from fastapi import Form
    from fastapi.responses import HTMLResponse
    from app.web.auth import make_session_cookie, COOKIE_NAME
    from app.web.templates import templates as _templates

    @app.get("/login", include_in_schema=False, response_class=HTMLResponse)
    async def login_page(request: Request, next: str = "/dashboard", error: str = ""):
        return _templates.TemplateResponse(
            request, "login.html", {"next": next, "error": error}
        )

    @app.post("/login", include_in_schema=False)
    @limiter.limit("5/minute")
    async def login_submit(
        request: Request,
        token: str = Form(...),
        next: str = Form(default="/dashboard"),
    ):
        import secrets as _sec
        from app.core.config import settings as _cfg
        if _cfg.dashboard_auth_token and _sec.compare_digest(token, _cfg.dashboard_auth_token):
            cookie_val = make_session_cookie(token)
            response = RedirectResponse(url=next, status_code=303)
            response.set_cookie(
                COOKIE_NAME,
                cookie_val,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,  # 7 days
            )
            return response
        return _templates.TemplateResponse(
            request, "login.html",
            {"next": next, "error": "Invalid token — try again."},
            status_code=401,
        )

    @app.get("/logout", include_in_schema=False)
    async def logout():
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(COOKIE_NAME)
        return response

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        # Inline SVG favicon — no static files needed
        from fastapi.responses import Response
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<rect width="32" height="32" rx="6" fill="#161925"/>'
            '<text x="6" y="24" font-size="20">🎬</text>'
            '</svg>'
        )
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard")

    # Public media: ONLY rendered videos (Instagram needs a direct HTTPS MP4 URL).
    # Do NOT expose audio/, scripts/, cache/, presenter/, etc.
    import os as _os
    from pathlib import Path as _StoragePath

    _storage_dir = _os.path.abspath(settings.storage_local_path)
    _videos_dir = str(_StoragePath(_storage_dir) / "videos")
    _StoragePath(_videos_dir).mkdir(parents=True, exist_ok=True)

    app.mount(
        "/storage/videos",
        StaticFiles(directory=_videos_dir, html=False, check_dir=True),
        name="storage-videos",
    )
    # Instagram / external fetch URL stays:
    #   {public_base_url}/storage/videos/{filename}.mp4

    app.include_router(health_router, tags=["health"])
    app.include_router(
        channels_router,
        prefix="/api/v1/channels",
        tags=["channels"],
        dependencies=_auth,
    )
    app.include_router(
        channel_automation_router,
        prefix="/api/v1/channels",
        tags=["channel-automation"],
        dependencies=_auth,
    )
    app.include_router(
        topics_router,
        prefix="/api/v1/topics",
        tags=["topics"],
        dependencies=_auth,
    )
    app.include_router(
        research_router,
        prefix="/api/v1/research",
        tags=["research"],
        dependencies=_auth,
    )
    app.include_router(
        scripts_router,
        prefix="/api/v1/scripts",
        tags=["scripts"],
        dependencies=_auth,
    )
    app.include_router(
        storyboards_router,
        prefix="/api/v1/storyboards",
        tags=["storyboards"],
        dependencies=_auth,
    )
    app.include_router(
        thumbnails_router,
        prefix="/api/v1/thumbnails",
        tags=["thumbnails"],
        dependencies=_auth,
    )
    app.include_router(
        voice_router,
        prefix="/api/v1/voice",
        tags=["voice"],
        dependencies=_auth,
    )
    app.include_router(
        video_router,
        prefix="/api/v1/videos",
        tags=["videos"],
        dependencies=_auth,
    )
    app.include_router(
        upload_router,
        prefix="/api/v1/uploads",
        tags=["uploads"],
        dependencies=_auth,
    )
    app.include_router(
        analytics_router,
        prefix="/api/v1/analytics",
        tags=["analytics"],
        dependencies=_auth,
    )
    app.include_router(
        pipeline_router,
        prefix="/api/v1/pipeline",
        tags=["pipeline"],
        dependencies=_auth,
    )
    app.include_router(
        publishing_router,
        prefix="/api/v1/publishing",
        tags=["publishing"],
        dependencies=_auth,
    )
    app.include_router(internal_triggers_router, tags=["internal"])
    # WebSocket stays open — HTMX bridge connects without auth headers
    app.include_router(websocket_router, prefix="/ws", tags=["websocket"])
    # Dashboard has its own per-request auth guard inside the router
    app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])

    # ── Chatbot routes ──────────────────────────────────────────────────────
    from app.api.routes.chat import ws_router as chat_ws_router
    from app.api.routes.chat import api_router as chat_api_router
    from app.api.routes.chat import dash_router as chat_dash_router

    app.include_router(chat_ws_router, prefix="/ws", tags=["chat"])
    app.include_router(chat_api_router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(chat_dash_router, prefix="/dashboard/partials", tags=["chat"])

    # ------------------------------------------------------------------
    # Monitoring (Phase 5, item 4)
    # ------------------------------------------------------------------

    @app.get("/metrics", tags=["monitoring"], dependencies=[Depends(require_dashboard_auth)])
    async def metrics() -> Response:
        from app.monitoring.metrics import render_latest

        body, content_type = render_latest()
        return Response(content=body, media_type=content_type)

    return app


app = create_app()
