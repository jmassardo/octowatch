"""Query router: run user-submitted queries + manage query templates."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.schemas.query import QueryRunRequest, QueryRunResponse, QueryTemplate, QueryTemplateCreate
from app.services.query_service import QueryValidationError, execute_query
from app.services.rbac_service import get_user_scope

router = APIRouter(prefix="/query", tags=["query"])

# In-memory query template store (production: use DB table)
_QUERY_TEMPLATES: dict[int, dict] = {}
_template_counter = 0


@router.post("/run", response_model=QueryRunResponse, dependencies=[Depends(verify_csrf)])
async def run_query(
    payload: QueryRunRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> QueryRunResponse:
    """Execute a user-submitted SQL query with AST validation and scope injection."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    try:
        result = await execute_query(db, sql=payload.sql, scope=scope)
        return result
    except (QueryValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
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
