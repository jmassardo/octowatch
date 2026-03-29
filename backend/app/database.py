"""Async SQLAlchemy engine and session factory.

Import `AsyncSessionLocal` for database access. Use `get_db()` from deps.py
in FastAPI route handlers.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings


# Build SSL context for PostgreSQL TLS requirement
def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    return ctx


def _build_engine(*, use_null_pool: bool = False) -> AsyncEngine:
    """Build the async SQLAlchemy engine."""
    connect_args: dict[str, object] = {}
    if "sslmode=require" in settings.DATABASE_URL or "sslmode=verify" in settings.DATABASE_URL:
        connect_args["ssl"] = _make_ssl_context()

    kwargs: dict[str, object] = {
        "echo": settings.LOG_LEVEL == "DEBUG",
        "connect_args": connect_args,
    }
    if use_null_pool:
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 300

    return create_async_engine(settings.DATABASE_URL, **kwargs)


# Application engine (connection pool)
engine: AsyncEngine = _build_engine()

# Session factory
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session. Use via FastAPI Depends."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except (SQLAlchemyError, ConnectionRefusedError):
            await session.rollback()
            raise


async def warm_up_pool() -> None:
    """Open one connection to verify the pool is healthy at startup."""
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))


async def dispose_pool() -> None:
    """Close all idle connections in the pool on shutdown."""
    await engine.dispose()
