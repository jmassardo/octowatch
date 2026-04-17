"""Posture router: enterprise / org / repo security posture drill-down."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.models.detection import Detection, RuleDefinition
from app.models.github_sync import EnterpriseOrg, Repository
from app.schemas.posture import (
    BreadcrumbItem,
    OrgPosture,
    PostureCheckResult,
    PostureResponse,
    RepoPosture,
    RepoSummary,
)
from app.services.rbac_service import get_user_scope

router = APIRouter(prefix="/posture", tags=["posture"])

_SEVERITY_WEIGHT = {"critical": 10, "high": 7, "medium": 4, "low": 2, "info": 1}
_OPEN_STATUSES = ("open", "investigating")


def _compute_score(checks: list[PostureCheckResult]) -> float:
    """Score = passing_weight / total_weight × 100."""
    if not checks:
        return 100.0
    total = sum(_SEVERITY_WEIGHT.get(c.severity, 1) for c in checks)
    passing = sum(_SEVERITY_WEIGHT.get(c.severity, 1) for c in checks if c.status == "pass")
    return round((passing / total) * 100, 1) if total else 100.0


def _check_from_detection(rule: RuleDefinition, det: Detection) -> PostureCheckResult:
    return PostureCheckResult(
        rule_id=rule.id,
        rule_name=rule.name,
        category=rule.category,
        severity=det.severity,
        status=det.status,
        title=det.title,
        description=det.description or "",
        detection_id=det.id,
        context_data=det.context_data or {},
        triggered_at=det.triggered_at,
    )


def _check_pass(rule: RuleDefinition) -> PostureCheckResult:
    return PostureCheckResult(
        rule_id=rule.id,
        rule_name=rule.name,
        category=rule.category,
        severity=rule.default_severity,
        status="pass",
        title=rule.name,
        description=rule.description or "",
    )


async def _load_rules(db: AsyncSession) -> dict[str, list[RuleDefinition]]:
    """Load all enabled rules, bucketed by logic_type group."""
    result = await db.execute(select(RuleDefinition).where(RuleDefinition.enabled.is_(True)))
    rules = result.scalars().all()
    posture = [r for r in rules if r.logic_type == "posture"]
    event_based = [r for r in rules if r.logic_type != "posture"]
    return {"posture": posture, "event": event_based}


async def _load_open_detections(
    db: AsyncSession,
    scope_orgs: list[str] | None,
    org_filter: str | None = None,
    repo_filter: str | None = None,
) -> list[Detection]:
    stmt = select(Detection).where(Detection.status.in_(_OPEN_STATUSES))
    if org_filter:
        stmt = stmt.where(Detection.org == org_filter)
    if repo_filter:
        stmt = stmt.where(Detection.repo == repo_filter)
    if scope_orgs:
        stmt = stmt.where(Detection.org.in_(scope_orgs))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _build_repo_posture(
    repo: Repository,
    repo_rules: list[RuleDefinition],
    event_rules: list[RuleDefinition],
    detections: list[Detection],
) -> RepoPosture:
    """Build posture for a single repo."""
    checks: list[PostureCheckResult] = []
    repo_dets = [d for d in detections if d.repo == repo.repo_name and d.org == repo.org]

    # Posture rules applicable to repos
    for rule in repo_rules:
        det = next((d for d in repo_dets if d.rule_id == rule.id), None)
        checks.append(_check_from_detection(rule, det) if det else _check_pass(rule))

    # Event-based detections for this repo
    event_det_ids = {r.id for r in event_rules}
    event_checks = [
        _check_from_detection(next(r for r in event_rules if r.id == d.rule_id), d)
        for d in repo_dets
        if d.rule_id in event_det_ids
    ]

    all_checks = checks + event_checks
    return RepoPosture(
        repo_name=repo.repo_name,
        org=repo.org,
        visibility=repo.visibility,
        default_branch=repo.default_branch,
        archived=repo.archived or False,
        fork=repo.fork or False,
        pushed_at=repo.pushed_at,
        score=_compute_score(all_checks),
        checks=all_checks,
        detection_count=len(event_checks),
    )


def _build_org_posture(
    org: EnterpriseOrg,
    org_rules: list[RuleDefinition],
    repo_rules: list[RuleDefinition],
    event_rules: list[RuleDefinition],
    repos: list[Repository],
    detections: list[Detection],
    include_repos: bool = False,
) -> OrgPosture:
    """Build posture for one org."""
    org_dets = [d for d in detections if d.org == org.org_login]

    # Org-level posture checks
    checks: list[PostureCheckResult] = []
    for rule in org_rules:
        det = next((d for d in org_dets if d.rule_id == rule.id and not d.repo), None)
        checks.append(_check_from_detection(rule, det) if det else _check_pass(rule))

    # Org-level event detections (no repo)
    event_det_ids = {r.id for r in event_rules}
    org_event_checks = [
        _check_from_detection(next(r for r in event_rules if r.id == d.rule_id), d)
        for d in org_dets
        if d.rule_id in event_det_ids and not d.repo
    ]
    checks.extend(org_event_checks)

    org_repos = [r for r in repos if r.org == org.org_login]
    repo_postures = [_build_repo_posture(r, repo_rules, event_rules, detections) for r in org_repos]

    # Score: 40% org checks, 60% repo avg
    org_check_score = _compute_score(checks)
    repo_avg = (
        sum(rp.score for rp in repo_postures) / len(repo_postures) if repo_postures else 100.0
    )
    score = round(org_check_score * 0.4 + repo_avg * 0.6, 1)

    # Repo summary
    passing = sum(1 for rp in repo_postures if rp.score >= 80)
    warning = sum(1 for rp in repo_postures if 50 <= rp.score < 80)
    failing = sum(1 for rp in repo_postures if rp.score < 50)

    return OrgPosture(
        org_login=org.org_login,
        score=score,
        two_factor_required=org.two_factor_required,
        default_repo_permission=org.default_repo_permission,
        members_can_fork_private_repos=org.members_can_fork_private_repos,
        members_can_create_public_repos=org.members_can_create_public_repos,
        ip_allow_list_enabled=org.ip_allow_list_enabled,
        checks=checks,
        repos=repo_postures if include_repos else None,
        repo_summary=RepoSummary(
            total=len(repo_postures),
            passing=passing,
            warning=warning,
            failing=failing,
        ),
        detection_count=len(org_event_checks),
    )


def _classify_rules(
    posture_rules: list[RuleDefinition],
    detections: list[Detection] | None = None,
) -> tuple[list[RuleDefinition], list[RuleDefinition]]:
    """Split posture rules into org-level and repo-level.

    When ``entity`` is missing from ``logic_config``, fall back to detection
    data: if a rule produced any detection with a ``repo`` value it is treated
    as a repo-level rule.
    """
    repo_det_rule_ids: set[int] = set()
    if detections:
        repo_det_rule_ids = {d.rule_id for d in detections if d.repo}

    org_rules: list[RuleDefinition] = []
    repo_rules: list[RuleDefinition] = []
    for r in posture_rules:
        cfg = r.logic_config or {}
        entity = cfg.get("entity", "")
        if entity in ("repo", "repository"):
            repo_rules.append(r)
        elif not entity and r.id in repo_det_rule_ids:
            repo_rules.append(r)
        else:
            org_rules.append(r)
    return org_rules, repo_rules


@router.get("", response_model=PostureResponse)
async def get_posture(
    org: str | None = Query(None, description="Filter to a specific org"),
    repo: str | None = Query(None, description="Filter to a specific repo"),
    search: str | None = Query(None, description="Search by name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> PostureResponse:
    """Security posture drill-down: enterprise → org → repo."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    rules = await _load_rules(db)
    event_rules = rules["event"]
    detections = await _load_open_detections(db, scope.scoped_orgs, org, repo)
    org_rules, repo_rules = _classify_rules(rules["posture"], detections)

    # Last sync timestamp
    sync_result = await db.execute(
        text("SELECT MAX(completed_at) FROM enterprise_sync_runs WHERE status = 'completed'")
    )
    last_sync_at = sync_result.scalar_one_or_none()

    # ── Repo-level drill-down ──────────────────────────────────────────
    if org and repo:
        repo_result = await db.execute(
            select(Repository).where(Repository.org == org, Repository.repo_name == repo)
        )
        repo_obj = repo_result.scalar_one_or_none()
        if not repo_obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")

        rp = _build_repo_posture(repo_obj, repo_rules, event_rules, detections)
        return PostureResponse(
            level="repo",
            score=rp.score,
            repo=rp,
            breadcrumb=[
                BreadcrumbItem(label="Posture", href="/posture"),
                BreadcrumbItem(label=org, href=f"/posture/{org}"),
                BreadcrumbItem(label=repo),
            ],
            last_sync_at=last_sync_at,
        )

    # ── Org-level drill-down ───────────────────────────────────────────
    if org:
        org_result = await db.execute(select(EnterpriseOrg).where(EnterpriseOrg.org_login == org))
        org_obj = org_result.scalar_one_or_none()
        if not org_obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

        repos_result = await db.execute(select(Repository).where(Repository.org == org))
        repos = list(repos_result.scalars().all())

        op = _build_org_posture(
            org_obj,
            org_rules,
            repo_rules,
            event_rules,
            repos,
            detections,
            include_repos=True,
        )

        # Paginate repos within the org posture
        all_repos = op.repos or []
        if search:
            q = search.lower()
            all_repos = [r for r in all_repos if q in r.repo_name.lower()]

        total = len(all_repos)
        offset = (page - 1) * page_size
        op.repos = all_repos[offset : offset + page_size]

        return PostureResponse(
            level="org",
            score=op.score,
            org=op,
            breadcrumb=[
                BreadcrumbItem(label="Posture", href="/posture"),
                BreadcrumbItem(label=org),
            ],
            last_sync_at=last_sync_at,
            page=page,
            page_size=page_size,
            total=total,
            has_next=(offset + page_size < total),
        )

    # ── Enterprise-level overview ──────────────────────────────────────
    orgs_result = await db.execute(select(EnterpriseOrg))
    orgs = list(orgs_result.scalars().all())
    if scope.scoped_orgs:
        orgs = [o for o in orgs if o.org_login in scope.scoped_orgs]

    repos_result = await db.execute(select(Repository))
    repos = list(repos_result.scalars().all())
    if scope.scoped_orgs:
        repos = [r for r in repos if r.org in scope.scoped_orgs]

    # Build all org postures (needed for enterprise score)
    all_org_postures = [
        _build_org_posture(o, org_rules, repo_rules, event_rules, repos, detections) for o in orgs
    ]

    enterprise_score = (
        round(sum(op.score for op in all_org_postures) / len(all_org_postures), 1)
        if all_org_postures
        else 100.0
    )

    # Apply search filter
    filtered = all_org_postures
    if search:
        q = search.lower()
        filtered = [op for op in filtered if q in op.org_login.lower()]

    total = len(filtered)
    offset = (page - 1) * page_size
    paginated = filtered[offset : offset + page_size]

    return PostureResponse(
        level="enterprise",
        score=enterprise_score,
        orgs=paginated,
        breadcrumb=[BreadcrumbItem(label="Posture")],
        last_sync_at=last_sync_at,
        page=page,
        page_size=page_size,
        total=total,
        has_next=(offset + page_size < total),
    )
