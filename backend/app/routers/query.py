"""Query router: run user-submitted queries + manage query templates."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.audit_trail import AuditTrail
from app.models.query_template import QueryTemplate as QueryTemplateModel
from app.rate_limit import limiter
from app.schemas.query import QueryRunRequest, QueryRunResponse, QueryTemplate, QueryTemplateCreate
from app.services.nl_query_service import NLQueryService
from app.services.query_service import QueryValidationError, execute_query
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
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
        # Clean the error message for the client
        error_msg = str(exc)
        for prefix in ["(sqlalchemy.dialects.postgresql.asyncpg.Error)", "(asyncpg."]:
            if prefix in error_msg:
                parts = error_msg.split(">: ", 1)
                if len(parts) > 1:
                    error_msg = parts[1]
        sql_idx = error_msg.find("\n[SQL:")
        if sql_idx == -1:
            sql_idx = error_msg.find("[SQL:")
        if sql_idx != -1:
            error_msg = error_msg[:sql_idx].strip()
        bg_idx = error_msg.find("(Background on this error")
        if bg_idx != -1:
            error_msg = error_msg[:bg_idx].strip()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query execution error: {error_msg}",
        ) from exc


@router.post("/validate", response_model=dict, dependencies=[Depends(verify_csrf)])
async def validate_query(
    payload: QueryRunRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate a SQL query without executing it. Returns validation result."""
    from app.services.query_service import validate_and_prepare

    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    try:
        rewritten_sql, params = validate_and_prepare(payload.sql, scope)

        # Use PREPARE to validate against the actual schema without executing
        import uuid

        from sqlalchemy import text as sa_text

        stmt_name = f"_validate_{uuid.uuid4().hex[:12]}"
        try:
            await db.execute(sa_text("SET LOCAL ROLE readonly_query_user"))
            # Substitute bind params for PREPARE (it doesn't support named params)
            prepare_sql = rewritten_sql
            for key, val in params.items():
                if isinstance(val, int):
                    prepare_sql = prepare_sql.replace(f":{key}", str(val))
                elif isinstance(val, list):
                    escaped = [str(v).replace("'", "''") for v in val]
                    arr = "ARRAY[" + ",".join(f"'{v}'" for v in escaped) + "]::text[]"
                    prepare_sql = prepare_sql.replace(f":{key}", arr)
            await db.execute(sa_text(f"PREPARE {stmt_name} AS {prepare_sql}"))
            await db.execute(sa_text(f"DEALLOCATE {stmt_name}"))
        except Exception as db_exc:
            error_msg = str(db_exc)
            # Extract the useful PostgreSQL error message
            clean = error_msg
            # Strip asyncpg class prefix
            if "<class 'asyncpg" in clean:
                parts = clean.split(">: ", 1)
                if len(parts) > 1:
                    clean = parts[1]
            # Strip SQLAlchemy wrapper
            if "(sqlalchemy" in clean:
                parts = clean.split(">: ", 1)
                if len(parts) > 1:
                    clean = parts[1]
            # Strip the [SQL: ...] suffix
            sql_idx = clean.find("\n[SQL:")
            if sql_idx == -1:
                sql_idx = clean.find("[SQL:")
            if sql_idx != -1:
                clean = clean[:sql_idx].strip()
            # Strip Background link
            bg_idx = clean.find("(Background on this error")
            if bg_idx != -1:
                clean = clean[:bg_idx].strip()
            return {"valid": False, "error": clean}
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
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
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
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
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
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
