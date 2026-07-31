from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.connection import get_db
from app.llm_providers.factory import get_llm_provider

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/detailed")
async def health_detailed(session: AsyncSession = Depends(get_db)) -> dict:
    checks: dict = {}

    # Database
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # LLM Provider
    try:
        provider = get_llm_provider()
        ok = await provider.health_check()
        checks["llm_provider"] = "ok" if ok else "degraded"
        checks["llm_provider_name"] = provider.provider_name
    except Exception as e:
        checks["llm_provider"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in checks.values() if isinstance(v, str) and v != checks.get("llm_provider_name")) else "degraded"

    return {
        "status": overall,
        "service": settings.app_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }