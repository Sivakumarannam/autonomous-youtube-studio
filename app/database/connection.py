"""Database connection helpers.

The engine is intentionally *lazy* — it is created only when first used
(``init_db``, ``get_db``, or ``_get_engine()``).  This means the module can
be imported without any live database present, which keeps unit-test
start-up clean.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _build_asyncpg_url(raw: str) -> str:
    """Normalise a database URL to use the asyncpg driver.

    * Strips the ``sslmode`` query parameter (asyncpg uses the ``ssl``
      parameter instead; leaving ``sslmode`` causes a driver-level error).
    * Replaces the ``postgresql://`` / ``postgres://`` scheme with
      ``postgresql+asyncpg://``.
    * URLs that already use a different scheme (e.g. ``sqlite+aiosqlite``)
      are returned unchanged.
    """
    # Strip sslmode
    parsed = urlparse(raw)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    raw = urlunparse(parsed._replace(query=new_query))

    # Swap driver
    for old_prefix in ("postgresql://", "postgres://"):
        if raw.startswith(old_prefix):
            return raw.replace(old_prefix, "postgresql+asyncpg://", 1)

    return raw


# ---------------------------------------------------------------------------
# Lazy engine / session factory
# ---------------------------------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        raw_url = os.environ.get("DATABASE_URL", "")

        # Fallback: read from app settings when env var is absent
        if not raw_url:
            from app.core.config import settings  # late import — avoids cycles
            raw_url = settings.database_url

        # Always run through the normalizer to scrub sslmode parameters
        db_url = _build_asyncpg_url(raw_url) if raw_url else ""

        if db_url.startswith("sqlite"):
            _engine = create_async_engine(db_url, echo=False)
        else:
            # Enforce SSL for cloud databases (Neon, RDS, etc.) unless the
            # original DATABASE_URL explicitly disables it (sslmode=disable),
            # which Replit's internal helium Postgres requires.
            raw_url = os.environ.get("DATABASE_URL", "")
            ssl_disabled = "sslmode=disable" in raw_url
            connect_args = {} if ssl_disabled else {"ssl": True}
            _engine = create_async_engine(
                db_url,
                echo=False,
                pool_pre_ping=True,
                # Recycle connections proactively rather than relying only on
                # pool_pre_ping (which only checks health at checkout time,
                # not while a connection is actively held). Neon's serverless
                # Postgres drops idle/long-lived connections; a video render
                # can hold a connection checked out for several minutes with
                # no DB activity in between, so pre_ping alone doesn't catch
                # it, and the final "mark complete" write fails with
                # "connection is closed". 180s keeps connections well under
                # Neon's own idle-disconnect window.
                pool_recycle=180,
                pool_size=10,
                max_overflow=20,
                connect_args=connect_args,
            )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# Public alias — callers outside this module should prefer this name
get_session_factory = _get_session_factory


# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # The route handler completed without raising. Most routes
            # already call session.commit() themselves, so this is a
            # safety-net no-op in the common case. If the underlying
            # connection was dropped in between (e.g. a Neon idle-connection
            # drop) this commit has nothing left to persist — its failure
            # shouldn't turn an already-successful response into a 500.
            try:
                await session.commit()
            except Exception as exc:
                from sqlalchemy.exc import DBAPIError, InterfaceError as SAInterfaceError

                if isinstance(exc, (SAInterfaceError, DBAPIError)):
                    logger.warning(
                        "Safety-net commit failed after request completed "
                        "(connection likely dropped) — response already "
                        "succeeded, ignoring.",
                        error=str(exc),
                    )
                else:
                    await session.rollback()
                    raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialise the DB connection pool.

    Schema management is handled exclusively by Alembic migrations.
    create_all() is intentionally removed from this path so that silent
    schema drift (missing columns on existing tables) is impossible.

    Set DEV_AUTO_CREATE_TABLES=true (or dev_auto_create_tables=true in .env)
    to restore the old create_all() behaviour for throw-away local dev
    environments.  Never set this in staging or production.
    """
    from app.core.config import settings  # late import — avoids cycles

    if settings.dev_auto_create_tables:
        async with _get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(
            "Database initialized",
            schema_mode="create_all (dev_auto_create_tables=true)",
        )
    else:
        logger.info(
            "Database initialized",
            schema_mode="alembic-only",
        )


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    logger.info("Database connections closed")
