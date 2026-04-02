"""Query router: run user-submitted queries + manage query templates."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.audit_trail import AuditTrail
from app.schemas.query import QueryRunRequest, QueryRunResponse, QueryTemplate, QueryTemplateCreate
from app.services.query_service import QueryValidationError, execute_query
from app.services.rbac_service import get_user_scope

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# In-memory query template store (production: use DB table)
_QUERY_TEMPLATES: dict[int, dict] = {}
_template_counter = 0


def _get_client_ip(request: Request) -> str | None:
    """Extract the client IP from the request."""
    return request.client.host if request.client else None


@router.post("/run", response_model=QueryRunResponse, dependencies=[Depends(verify_csrf)])
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


@router.post("/validate", response_model=dict)
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
                pass

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
) -> list[QueryTemplate]:
    """List available query templates."""
    return [QueryTemplate(**t) for t in _QUERY_TEMPLATES.values()]


@router.post("/templates", response_model=QueryTemplate, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: QueryTemplateCreate,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
) -> QueryTemplate:
    """Create a new query template."""
    global _template_counter
    _template_counter += 1
    template = QueryTemplate(
        id=_template_counter,
        name=payload.name,
        description=payload.description,
        sql=payload.sql,
        created_by=current_user.github_login,
        created_at=datetime.now(UTC).isoformat(),
    )
    _QUERY_TEMPLATES[_template_counter] = template.model_dump()
    return template


@router.get("/templates/{template_id}", response_model=QueryTemplate)
async def get_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
) -> QueryTemplate:
    """Get a query template by ID."""
    t = _QUERY_TEMPLATES.get(template_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return QueryTemplate(**t)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
) -> Response:
    """Delete a query template."""
    if template_id not in _QUERY_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    del _QUERY_TEMPLATES[template_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/templates/{template_id}/run", response_model=QueryRunResponse)
async def run_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> QueryRunResponse:
    """Execute a saved query template."""
    t = _QUERY_TEMPLATES.get(template_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    try:
        return await execute_query(db, sql=t["sql"], scope=scope)
    except (QueryValidationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
