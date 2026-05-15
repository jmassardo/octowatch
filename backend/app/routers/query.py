"""Query router: run user-submitted queries + manage query templates."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.audit_trail import AuditTrail
from app.models.query_template import QueryTemplate as QueryTemplateModel
from app.models.saved_query import SavedQuery as SavedQueryModel
from app.rate_limit import limiter
from app.schemas.query import (
    QueryRunRequest,
    QueryRunResponse,
    QueryTemplate,
    QueryTemplateCreate,
    SavedQueryCreate,
    SavedQueryResponse,
    SavedQueryUpdate,
    ScheduleQueryRequest,
    SchemaColumn,
    SchemaTable,
    ShareQueryRequest,
)
from app.services.nl_query_service import NLQueryService
from app.services.query_service import ALLOWED_TABLES, QueryValidationError, execute_query
from app.services.rbac_service import get_user_scope
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP from the request using trusted-proxy-aware logic."""
    return get_client_ip(request)


@router.post("/run", response_model=QueryRunResponse, dependencies=[Depends(verify_csrf)])
@limiter.limit("30/minute")
async def run_query(
    payload: QueryRunRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> QueryRunResponse:
    """Execute a user-submitted SQL query with AST validation and scope injection."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    client_ip = _get_client_ip(request)
    try:
        result = await execute_query(db, sql=payload.sql, scope=scope)

        # Audit log: successful query execution
        trail = AuditTrail(
            user_login=current_user.github_login,
            user_github_id=current_user.github_id,
            ip_address=client_ip,
            action_type="query.executed",
            resource_type="query_explorer",
            parameters={
                "sql": payload.sql[:500],
                "row_count": result["row_count"],
                "execution_ms": result["execution_ms"],
            },
            outcome="success",
        )
        db.add(trail)
        await db.commit()

        return result
    except (QueryValidationError, ValueError) as exc:
        # Audit log: blocked query
        try:
            trail = AuditTrail(
                user_login=current_user.github_login,
                user_github_id=current_user.github_id,
                ip_address=client_ip,
                action_type="query.blocked",
                resource_type="query_explorer",
                parameters={"sql": payload.sql[:500], "reason": str(exc)},
                outcome="denied",
                error_detail=str(exc),
            )
            db.add(trail)
            await db.commit()
        except Exception:
            logger.warning(
                "audit.write_failed",
                user=current_user.github_login,
                action="query.blocked",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Audit log: query execution error
        try:
            await db.rollback()
            trail = AuditTrail(
                user_login=current_user.github_login,
                user_github_id=current_user.github_id,
                ip_address=client_ip,
                action_type="query.blocked",
                resource_type="query_explorer",
                parameters={"sql": payload.sql[:500], "reason": str(exc)},
                outcome="denied",
                error_detail=str(exc),
            )
            db.add(trail)
            await db.commit()
        except Exception:
            logger.warning(
                "audit.write_failed",
                user=current_user.github_login,
                action="query.error",
            )
        # Log the full error details server-side
        logger.exception(
            "query.execution_error",
            user=current_user.github_login,
            sql_preview=payload.sql[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query execution failed. Check query syntax and try again.",
        ) from exc


@router.post("/validate", response_model=dict, dependencies=[Depends(verify_csrf)])
async def validate_query(
    payload: QueryRunRequest,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate a SQL query without executing it. Returns validation result."""
    from app.services.query_service import validate_and_prepare

    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    try:
        rewritten_sql, params = validate_and_prepare(payload.sql, scope)

        # Validate against the actual schema using EXPLAIN (no execution).
        # EXPLAIN supports bound parameters via text(), avoiding SQL injection.
        from sqlalchemy import text as sa_text

        try:
            await db.execute(sa_text("SET LOCAL ROLE readonly_query_user"))
            # Security: rewritten_sql is validated through pglast AST parsing.
            # Bind parameters are passed separately via SQLAlchemy text().
            await db.execute(sa_text(f"EXPLAIN {rewritten_sql}"), params)
        except Exception as db_exc:
            logger.warning(
                "query.validation_failed",
                error=str(db_exc),
            )
            return {"valid": False, "error": "Query validation failed against the database schema."}
        finally:
            try:
                await db.execute(sa_text("RESET ROLE"))
            except Exception:
                logger.debug("query.reset_role_failed_after_validation")

        return {
            "valid": True,
            "rewritten_sql": rewritten_sql,
        }
    except QueryValidationError as exc:
        return {"valid": False, "error": str(exc)}


@router.get("/templates", response_model=list[QueryTemplate])
async def list_templates(
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> list[QueryTemplate]:
    """List available query templates."""
    result = await db.execute(
        select(QueryTemplateModel).order_by(QueryTemplateModel.created_at.desc())
    )
    return [QueryTemplate.model_validate(row) for row in result.scalars().all()]


@router.post(
    "/templates",
    response_model=QueryTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_template(
    payload: QueryTemplateCreate,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> QueryTemplate:
    """Create a new query template."""
    template = QueryTemplateModel(
        name=payload.name,
        description=payload.description,
        sql=payload.sql,
        created_by=current_user.github_login,
        org_slug=payload.org_slug,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return QueryTemplate.model_validate(template)


@router.get("/templates/{template_id}", response_model=QueryTemplate)
async def get_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> QueryTemplate:
    """Get a query template by ID."""
    result = await db.execute(
        select(QueryTemplateModel).where(QueryTemplateModel.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return QueryTemplate.model_validate(template)


@router.delete("/templates/{template_id}", dependencies=[Depends(verify_csrf)])
async def delete_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a query template."""
    result = await db.execute(
        select(QueryTemplateModel).where(QueryTemplateModel.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await db.delete(template)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/templates/{template_id}/run",
    response_model=QueryRunResponse,
    dependencies=[Depends(verify_csrf)],
)
async def run_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> QueryRunResponse:
    """Execute a saved query template."""
    result = await db.execute(
        select(QueryTemplateModel).where(QueryTemplateModel.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    try:
        return await execute_query(db, sql=template.sql, scope=scope)
    except (QueryValidationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── Saved Queries (User's Own) ────────────────────────────────────────────────


@router.post(
    "/saved",
    response_model=SavedQueryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_saved_query(
    payload: SavedQueryCreate,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> SavedQueryResponse:
    """Save a query with name, description, and optional tags."""
    saved = SavedQueryModel(
        name=payload.name,
        description=payload.description,
        sql_text=payload.sql_text,
        owner_login=current_user.github_login,
        tags=payload.tags,
    )
    db.add(saved)
    await db.flush()
    await db.refresh(saved)
    return SavedQueryResponse.model_validate(saved)


@router.get("/saved", response_model=list[SavedQueryResponse])
async def list_saved_queries(
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> list[SavedQueryResponse]:
    """List the current user's saved queries."""
    result = await db.execute(
        select(SavedQueryModel)
        .where(SavedQueryModel.owner_login == current_user.github_login)
        .order_by(SavedQueryModel.updated_at.desc())
    )
    return [SavedQueryResponse.model_validate(row) for row in result.scalars().all()]


@router.put(
    "/saved/{query_id}",
    response_model=SavedQueryResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_saved_query(
    query_id: int,
    payload: SavedQueryUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> SavedQueryResponse:
    """Update a saved query owned by the current user."""
    result = await db.execute(select(SavedQueryModel).where(SavedQueryModel.id == query_id))
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found")
    if saved.owner_login != current_user.github_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the query owner")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(SavedQueryModel).where(SavedQueryModel.id == query_id).values(**update_data)
        )
        await db.flush()
        await db.refresh(saved)
    return SavedQueryResponse.model_validate(saved)


@router.delete("/saved/{query_id}", dependencies=[Depends(verify_csrf)])
async def delete_saved_query(
    query_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a saved query owned by the current user."""
    result = await db.execute(select(SavedQueryModel).where(SavedQueryModel.id == query_id))
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found")
    if saved.owner_login != current_user.github_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the query owner")
    await db.delete(saved)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Query Sharing ─────────────────────────────────────────────────────────────


@router.post(
    "/saved/{query_id}/share",
    response_model=SavedQueryResponse,
    dependencies=[Depends(verify_csrf)],
)
async def share_query(
    query_id: int,
    payload: ShareQueryRequest,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> SavedQueryResponse:
    """Share a saved query with other users by their GitHub logins."""
    result = await db.execute(select(SavedQueryModel).where(SavedQueryModel.id == query_id))
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found")
    if saved.owner_login != current_user.github_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the query owner")

    existing: list[str] = saved.shared_with or []
    merged = list(set(existing) | set(payload.logins))
    await db.execute(
        update(SavedQueryModel)
        .where(SavedQueryModel.id == query_id)
        .values(shared_with=merged, is_shared=True)
    )
    await db.flush()
    await db.refresh(saved)
    return SavedQueryResponse.model_validate(saved)


@router.get("/shared", response_model=list[SavedQueryResponse])
async def list_shared_queries(
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> list[SavedQueryResponse]:
    """List queries that have been shared with the current user."""
    login = current_user.github_login
    result = await db.execute(
        select(SavedQueryModel)
        .where(
            SavedQueryModel.is_shared.is_(True),
            SavedQueryModel.owner_login != login,
            or_(
                SavedQueryModel.shared_with.contains([login]),
                SavedQueryModel.shared_with.is_(None),
            ),
        )
        .order_by(SavedQueryModel.updated_at.desc())
    )
    return [SavedQueryResponse.model_validate(row) for row in result.scalars().all()]


# ── Query Scheduling ──────────────────────────────────────────────────────────


@router.post(
    "/saved/{query_id}/schedule",
    response_model=SavedQueryResponse,
    dependencies=[Depends(verify_csrf)],
)
async def schedule_query(
    query_id: int,
    payload: ScheduleQueryRequest,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> SavedQueryResponse:
    """Set or update a cron schedule for a saved query.

    Stores schedule metadata — actual execution is handled by the beat worker.
    """
    result = await db.execute(select(SavedQueryModel).where(SavedQueryModel.id == query_id))
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved query not found")
    if saved.owner_login != current_user.github_login:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the query owner")

    await db.execute(
        update(SavedQueryModel)
        .where(SavedQueryModel.id == query_id)
        .values(schedule_cron=payload.cron, schedule_enabled=payload.enabled)
    )
    await db.flush()
    await db.refresh(saved)
    return SavedQueryResponse.model_validate(saved)


# ── Schema Introspection ─────────────────────────────────────────────────────


# Schema metadata for autocomplete — derived from the ALLOWED_TABLES
# plus column definitions from the events/detections models.
_SCHEMA_CACHE: list[SchemaTable] | None = None


def _build_schema() -> list[SchemaTable]:
    """Build schema metadata for the allowed query tables.

    Returns table and column info for client-side autocomplete.
    We hard-code columns rather than introspecting at runtime to avoid
    requiring a live database connection and to keep the response fast.
    """
    schema_map: dict[str, list[SchemaColumn]] = {
        "events": [
            SchemaColumn(name="id", type="bigint"),
            SchemaColumn(name="action", type="text"),
            SchemaColumn(name="namespace", type="text"),
            SchemaColumn(name="actor", type="text"),
            SchemaColumn(name="org", type="text"),
            SchemaColumn(name="repo", type="text"),
            SchemaColumn(name="source_ip", type="inet"),
            SchemaColumn(name="geo_country_code", type="text"),
            SchemaColumn(name="geo_city", type="text"),
            SchemaColumn(name="created_at", type="timestamptz"),
            SchemaColumn(name="data", type="jsonb"),
        ],
        "detections": [
            SchemaColumn(name="id", type="bigint"),
            SchemaColumn(name="title", type="text"),
            SchemaColumn(name="severity", type="text"),
            SchemaColumn(name="status", type="text"),
            SchemaColumn(name="actor", type="text"),
            SchemaColumn(name="org", type="text"),
            SchemaColumn(name="repo", type="text"),
            SchemaColumn(name="triggered_at", type="timestamptz"),
        ],
        "events_hourly": [
            SchemaColumn(name="bucket_hour", type="timestamptz"),
            SchemaColumn(name="org", type="text"),
            SchemaColumn(name="namespace", type="text"),
            SchemaColumn(name="action", type="text"),
            SchemaColumn(name="event_count", type="bigint"),
        ],
        "events_daily_actor": [
            SchemaColumn(name="bucket_day", type="timestamptz"),
            SchemaColumn(name="actor", type="text"),
            SchemaColumn(name="org", type="text"),
            SchemaColumn(name="namespace", type="text"),
            SchemaColumn(name="event_count", type="bigint"),
        ],
        "detections_daily": [
            SchemaColumn(name="bucket_day", type="timestamptz"),
            SchemaColumn(name="severity", type="text"),
            SchemaColumn(name="status", type="text"),
            SchemaColumn(name="detection_count", type="bigint"),
        ],
        "behavioral_baselines": [
            SchemaColumn(name="id", type="bigint"),
            SchemaColumn(name="actor", type="text"),
            SchemaColumn(name="org", type="text"),
            SchemaColumn(name="feature", type="text"),
            SchemaColumn(name="baseline_value", type="float"),
            SchemaColumn(name="updated_at", type="timestamptz"),
        ],
    }
    tables: list[SchemaTable] = []
    for tbl_name in sorted(ALLOWED_TABLES):
        columns = schema_map.get(tbl_name, [])
        tables.append(SchemaTable(table=tbl_name, columns=columns))
    return tables


@router.get("/schema", response_model=list[SchemaTable])
async def get_schema(
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
) -> list[SchemaTable]:
    """Return available tables and columns for query editor autocomplete."""
    global _SCHEMA_CACHE  # noqa: PLW0603
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = _build_schema()
    return _SCHEMA_CACHE


# ── Natural language query ────────────────────────────────────────────────────

_nl_service = NLQueryService()


class NLQueryRequest(BaseModel):
    """Request body for natural-language query translation."""

    query: str = Field(..., min_length=3, max_length=2000)


class NLInterpretationResponse(BaseModel):
    """A single SQL interpretation of a natural-language query."""

    sql: str
    description: str
    confidence: float


@router.post(
    "/nl",
    response_model=list[NLInterpretationResponse],
    dependencies=[Depends(verify_csrf)],
)
@limiter.limit("30/minute")
async def translate_natural_language(
    payload: NLQueryRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("queries", "execute")),
    db: AsyncSession = Depends(get_db),
) -> list[NLInterpretationResponse]:
    """Translate a natural-language question into SQL interpretations.

    Returns up to 5 SQL queries ranked by confidence.  The user can review,
    edit, and execute the generated SQL through the standard query/run endpoint.
    RBAC scope injection is applied when the SQL is eventually executed.
    """
    interpretations = _nl_service.translate(payload.query)

    if not interpretations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not interpret query. Try rephrasing with specific terms.",
        )

    return [
        NLInterpretationResponse(
            sql=i.sql,
            description=i.description,
            confidence=round(i.confidence, 2),
        )
        for i in interpretations
    ]
