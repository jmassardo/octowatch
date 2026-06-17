---
applyTo: "backend/**"
---

# Backend Instructions

## Framework & Patterns
- FastAPI with async/await throughout. All route handlers and service functions are `async def`.
- SQLAlchemy 2.x ORM with `AsyncSession`. Use `Mapped[]` type annotations and `mapped_column()`.
- Dependency injection via `Depends()` for database sessions (`get_db`), authentication (`require_permission`).
- Raw SQL uses `text()` with named parameters: `text("SELECT * FROM events WHERE org = :org")`, passed as dicts.

## File Organization
- **Models** (`app/models/`): One file per domain. All inherit from `Base` (defined in `audit_event.py`). Use `Mapped[type]` annotations.
- **Routers** (`app/routers/`): One file per API domain. Register in `main.py` via `app.include_router()`.
- **Services** (`app/services/`): Business logic. Functions accept `db: AsyncSession` as first param, return `dict[str, Any]`.
- **Workers** (`app/workers/`): Celery tasks. Use `@shared_task` or `@celery_app.task`. Enqueue with `.delay()`.

## Conventions
- Start every file with `from __future__ import annotations`
- Use `structlog.get_logger(__name__)` for logging, not `print()` or stdlib `logging`
- Service functions begin with `await _check_feature_enabled(db)` guard
- Router endpoints use `org: str | None = Query(None)` for org filtering
- Alembic migrations: sequential `0001_`, `0002_` naming. Use `op.add_column`, `op.execute` for data migration.

## Testing
- pytest with `@pytest.mark.asyncio` for async tests
- Mock database with `AsyncMock(spec=AsyncSession)`
- Run: `cd backend && pytest tests/ -x -q`

## Validation
```bash
ruff check .          # Lint
ruff format --check . # Format
mypy .                # Types
pytest tests/ -x -q   # Tests
```
