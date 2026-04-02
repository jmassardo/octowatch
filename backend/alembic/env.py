"""Alembic environment configuration.

Uses the DATABASE_URL environment variable (or app settings) for the
migration database connection. Supports both online (auto) and offline
(--sql) modes.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can autogenerate migrations
# (not used in this initial migration but needed for future auto-generation)
from app.models import *  # noqa: F401, F403, E402

target_metadata = None  # We use op.execute() for initial migration

# Override sqlalchemy.url from DATABASE_URL env var (strips +asyncpg for
# offline mode — alembic offline uses the sync URL in generated SQL scripts)
_raw_url = os.environ.get("DATABASE_URL", "")
_async_url = _raw_url  # keep asyncpg driver for online async migrations
if _raw_url:
    # Offline mode needs sync URL
    _sync_url = _raw_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "?sslmode=require", ""
    )
    config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an
    Engine is acceptable here as well. By skipping the Engine creation we don't
    even need a DBAPI to be available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (for asyncpg)."""
    connectable = create_async_engine(
        _async_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context (shouldn't happen with alembic CLI)
            import nest_asyncio

            nest_asyncio.apply()
            loop.run_until_complete(run_async_migrations())
        else:
            asyncio.run(run_async_migrations())
    except RuntimeError:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
