"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ─── Required env vars must be set BEFORE any app.* imports ────────────────────
# The settings singleton is built at module import time.  Supply safe test
# defaults so any test that doesn't need a real DB/Valkey can still import ok.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "testsecretkey_for_unit_tests_only_32ch")
os.environ.setdefault("APP_BASE_URL", "http://localhost:8000")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("MINIO_AUDIT_BUCKET", "audit-logs")
os.environ.setdefault("MINIO_INGEST_USER", "minioadmin")
os.environ.setdefault("MINIO_INGEST_PASSWORD", "minioadmin")
os.environ.setdefault("GITHUB_RULES_REPO", "")
os.environ.setdefault("GITHUB_RULES_TOKEN", "")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ─── Test database ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite engine for unit tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a test DB session backed by an in-memory SQLite database."""
    session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


# ─── Valkey mock ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_valkey():
    """Provide a mock Valkey (redis) client for unit tests."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=0)
    client.ping = AsyncMock(return_value=True)
    client.pipeline = MagicMock(return_value=AsyncMock())
    return client


# ─── Auth helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_jwt_payload() -> dict[str, Any]:
    """Return a sample valid JWT payload."""
    return {
        "sub": "testuser",
        "github_id": 12345,
        "jti": "test-jti-1234",
        "exp": 9999999999,
        "iat": 1700000000,
    }


@pytest.fixture
def sample_session_data() -> dict[str, Any]:
    """Return a session data dict as stored in Valkey."""
    return {
        "github_login": "testuser",
        "github_id": 12345,
        "roles": ["analyst"],
        "scoped_orgs": ["my-org"],
        "scoped_repos": [],
        "scope_type": "scoped",
        "session_expires_at": "2099-01-01T00:00:00+00:00",
    }


@pytest.fixture
def authenticated_valkey(mock_valkey, sample_session_data):
    """Return a mock Valkey that simulates a valid session."""
    mock_valkey.get.return_value = json.dumps(sample_session_data)
    mock_valkey.exists.return_value = 1
    return mock_valkey


# ─── Sample event ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_event_dict() -> dict[str, Any]:
    """Return a minimal GitHub audit log event dict."""
    return {
        "action": "repos.create",
        "actor": "octocat",
        "actor_id": 583231,
        "org": "my-org",
        "repo": "my-org/hello-world",
        "@ip": "192.168.1.100",
        "@timestamp": int(datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC).timestamp() * 1000),
        "data": {"description": "A new repository"},
    }
