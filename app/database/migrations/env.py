import os
import sys

BASE_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../..",
    )
)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import asyncio
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import Base and ALL models so Alembic can detect schema changes.
# Every model that maps to a table must be imported here.
from app.database.connection import Base
import app.database.models.channel          # noqa: F401
import app.database.models.topic            # noqa: F401
import app.database.models.research         # noqa: F401
import app.database.models.script           # noqa: F401
import app.database.models.storyboard       # noqa: F401
import app.database.models.video            # noqa: F401
import app.database.models.thumbnail        # noqa: F401
import app.database.models.upload           # noqa: F401
import app.database.models.analytics        # noqa: F401
import app.database.models.agent_log        # noqa: F401
import app.database.models.user             # noqa: F401
import app.database.models.quality_report   # noqa: F401
import app.database.models.voice            # noqa: F401
import app.database.models.pipeline_run     # noqa: F401
import app.database.models.channel_automation  # noqa: F401

from app.core.config import settings

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Override sqlalchemy.url with the value from application settings so
# a single source of truth (the .env file) drives both the app and migrations.
config.set_main_option("sqlalchemy.url", settings.database_sync_url)

# Interpret the config file for Python logging if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given SQL to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    # Get the configuration section dictionary
    section = config.get_section(config.config_ini_section, {})

    # Strip out any lingering sync-based sslmode options from the config section
    section.pop("sslmode", None)

    # Use the async URL (asyncpg driver) for online mode
    db_url = settings.database_url

    # Enforce SSL for PostgreSQL/Neon cloud databases; skip for SQLite and for
    # databases that explicitly set sslmode=disable in their connection string
    # (e.g. Replit's internal helium postgres which does not support SSL).
    raw_db_url = os.environ.get("DATABASE_URL", "")
    ssl_disabled = "sslmode=disable" in raw_db_url
    use_ssl = db_url.startswith("postgresql") and not ssl_disabled
    connect_args = {"ssl": True} if use_ssl else {}

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=db_url,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
