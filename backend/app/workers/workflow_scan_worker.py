"""Workflow security analysis from audit log events.

Queue: baseline

Analyses ``workflows.*`` events already in the database to detect security
anti-patterns **without** making any GitHub API calls.  Detectable signals
from audit log event payloads:

  prepared_workflow_job:
    - Self-hosted runner usage  (is_hosted_runner=false)
    - High secret exposure      (secrets_passed_count >= threshold)
    - PR-triggered jobs         (job_workflow_ref contains @refs/pull/)

  created_workflow_run:
    - PAT-triggered workflows   (programmatic_access_type contains 'personal')
    - Public repo workflow runs (public_repo=true)

  completed_workflow_run:
    - Public repo workflow runs (public_repo=true)

Findings are stored in ``workflow_findings`` using upsert so repeated runs
are idempotent.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from celery import Task
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app
from app.models.workflow_finding import WorkflowFinding

logger = structlog.get_logger(__name__)


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


# ── Detection rules applied to audit-log events ─────────────────────────────


def _extract_workflow_path(job_workflow_ref: str) -> str:
    """Extract '.github/workflows/foo.yml' from a job_workflow_ref."""
    if not job_workflow_ref:
        return ".github/workflows/unknown.yml"
    # Dynamic/GitHub-managed workflows (e.g., /dynamic/dependabot/...)
    if job_workflow_ref.startswith("/dynamic/"):
        parts = job_workflow_ref.split("@")[0].strip("/").split("/")
        return (
            f".github/workflows/{'/'.join(parts[1:])}.yml"
            if len(parts) > 1
            else ".github/workflows/dynamic.yml"
        )
    match = re.search(r"(\.github/workflows/[^@]+)", job_workflow_ref)
    return match.group(1) if match else ".github/workflows/unknown.yml"


def _analyze_prepared_job(data: dict[str, Any], repo: str, org: str) -> list[dict]:
    """Analyze a prepared_workflow_job event for security issues."""
    findings: list[dict] = []
    wf_ref = data.get("job_workflow_ref", "")
    wf_path = _extract_workflow_path(wf_ref)
    job_name = data.get("job_name", "unknown")

    # 1. Self-hosted runner
    # GitHub audit log uses is_hosted_runner=false for self-hosted runners,
    # but also check runner_type field for alternative payload formats
    is_self_hosted = (
        data.get("is_hosted_runner") == False  # noqa: E712 – intentional equality check
        or str(data.get("runner_type", "")).lower() in ("self-hosted", "self_hosted")
    )
    if is_self_hosted:
        runner_name = data.get("runner_name", "unknown")
        runner_labels = data.get("runner_labels", [])
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "self-hosted-runner",
                "severity": "medium",
                "title": "Self-hosted runner detected",
                "description": (
                    f"Job '{job_name}' runs on self-hosted runner '{runner_name}' "
                    f"with labels {runner_labels}. Self-hosted runners require hardening "
                    f"as they persist state between jobs and may expose secrets."
                ),
                "details": {
                    "job_name": job_name,
                    "runner_name": runner_name,
                    "runner_labels": runner_labels,
                    "runner_group": data.get("runner_group_name"),
                },
                "suggested_fix": (
                    "Use GitHub-hosted runners when possible. If self-hosted runners "
                    "are required, run them in ephemeral mode, use separate runner groups "
                    "per trust level, and never run untrusted PR workflows on them."
                ),
            }
        )

    # 2. Secret exposure levels
    secrets_count = data.get("secrets_passed_count", 0) or 0
    if secrets_count >= 3:
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "excessive-secrets",
                "severity": "high",
                "title": f"High secret exposure ({secrets_count} secrets)",
                "description": (
                    f"Job '{job_name}' receives {secrets_count} secrets. Passing many "
                    f"secrets increases the blast radius if the workflow is compromised. "
                    f"Follow the principle of least privilege."
                ),
                "details": {
                    "job_name": job_name,
                    "secrets_passed_count": secrets_count,
                },
                "suggested_fix": (
                    "Reduce the number of secrets passed to each job. Use OIDC tokens "
                    "instead of long-lived credentials where possible. Split jobs so "
                    "each only receives the secrets it actually needs."
                ),
            }
        )
    elif secrets_count >= 2:
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "moderate-secrets",
                "severity": "low",
                "title": f"Multiple secrets passed to job ({secrets_count})",
                "description": (
                    f"Job '{job_name}' receives {secrets_count} secrets. "
                    f"Review whether all secrets are needed for this job."
                ),
                "details": {
                    "job_name": job_name,
                    "secrets_passed_count": secrets_count,
                },
                "suggested_fix": (
                    "Review the secrets passed to this job and remove any that are "
                    "not required. Consider using environment-level secrets."
                ),
            }
        )

    # 3. PR-triggered workflow (from fork context) — skip dynamic/GitHub-managed workflows
    if "@refs/pull/" in wf_ref and not wf_ref.startswith("/dynamic/"):
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "pr-triggered-workflow",
                "severity": "medium",
                "title": "Workflow triggered by pull request",
                "description": (
                    f"Job '{job_name}' was triggered from a pull request context "
                    f"({wf_ref}). PR-triggered workflows can be exploited if they "
                    f"have access to secrets or use pull_request_target."
                ),
                "details": {
                    "job_name": job_name,
                    "workflow_ref": wf_ref,
                },
                "suggested_fix": (
                    "Ensure PR-triggered workflows do not have write permissions or "
                    "access to repository secrets. Use pull_request (not pull_request_target) "
                    "for untrusted code. Never checkout PR code with pull_request_target."
                ),
            }
        )

    # 4. Reusable workflow chain (calling_workflow_refs present)
    calling_refs = data.get("calling_workflow_refs") or []
    if calling_refs:
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "reusable-workflow-chain",
                "severity": "low",
                "title": "Reusable workflow chain detected",
                "description": (
                    f"Job '{job_name}' is a reusable workflow called by: "
                    f"{', '.join(calling_refs[:3])}. Reusable workflows inherit the "
                    f"caller's permissions and secrets — ensure trust boundaries."
                ),
                "details": {
                    "job_name": job_name,
                    "calling_workflow_refs": calling_refs,
                },
                "suggested_fix": (
                    "Audit the calling workflows to ensure they don't grant excessive "
                    "permissions. Pin reusable workflow references to specific SHAs."
                ),
            }
        )

    # 5. Workflow running on non-default/slim runner image
    runner_labels = data.get("runner_labels") or []
    if any("slim" in str(label).lower() for label in runner_labels):
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "slim-runner-image",
                "severity": "low",
                "title": "Workflow uses slim runner image",
                "description": (
                    f"Job '{job_name}' runs on a slim runner image ({runner_labels}). "
                    f"Slim images have fewer pre-installed tools, which can be more secure "
                    f"but may lead to unexpected behavior if workflows install tools at runtime."
                ),
                "details": {
                    "job_name": job_name,
                    "runner_labels": runner_labels,
                },
                "suggested_fix": None,
            }
        )

    return findings


def _analyze_completed_run(data: dict[str, Any], repo: str, org: str) -> list[dict]:
    """Analyze a completed_workflow_run event for security issues."""
    findings: list[dict] = []
    wf_name = data.get("name", "unknown")
    wf_path = f".github/workflows/{wf_name.lower().replace(' ', '-')}.yml"
    head_branch = data.get("head_branch", "")
    conclusion = data.get("conclusion", "")

    # Public repo with workflow runs
    if data.get("public_repo") is True:
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "public-repo-workflow",
                "severity": "low",
                "title": "Workflow runs on public repository",
                "description": (
                    f"Workflow '{wf_name}' runs on a public repository. Public repos "
                    f"allow anyone to fork and submit PRs that trigger workflow runs. "
                    f"Ensure workflows don't expose secrets to fork PRs."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "head_branch": head_branch,
                    "conclusion": conclusion,
                },
                "suggested_fix": (
                    "Review workflow triggers for public repos. Avoid pull_request_target "
                    "with checkout. Use environment protection rules and manual approvals "
                    "for deployments from forks."
                ),
            }
        )

    return findings


def _analyze_created_run(data: dict[str, Any], repo: str, org: str) -> list[dict]:
    """Analyze a created_workflow_run event for security issues."""
    findings: list[dict] = []
    wf_name = data.get("name", "unknown")
    wf_path = f".github/workflows/{wf_name.lower().replace(' ', '-')}.yml"
    access_type = data.get("programmatic_access_type", "")
    event_trigger = data.get("event", "")
    actor = data.get("actor", "")

    # 1. PAT-triggered workflow
    if access_type and "personal access token" in access_type.lower():
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "pat-triggered-workflow",
                "severity": "medium",
                "title": "Workflow triggered via Personal Access Token",
                "description": (
                    f"Workflow '{wf_name}' was triggered using a {access_type}. "
                    f"PAT-triggered workflows may indicate automation that should "
                    f"use a GitHub App or fine-grained token instead."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "access_type": access_type,
                    "actor": actor,
                },
                "suggested_fix": (
                    "Replace classic PATs with GitHub App installation tokens or "
                    "fine-grained personal access tokens with minimal scopes."
                ),
            }
        )

    # 2. Schedule-triggered workflow (potential persistence vector)
    if event_trigger == "schedule":
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "schedule-triggered",
                "severity": "low",
                "title": f"Scheduled workflow: {wf_name}",
                "description": (
                    f"Workflow '{wf_name}' runs on a cron schedule. Scheduled workflows "
                    f"can be used as a persistence mechanism by attackers. Ensure this "
                    f"workflow is expected and review its actions periodically."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "actor": actor,
                    "trigger": event_trigger,
                },
                "suggested_fix": (
                    "Audit all scheduled workflows periodically. Ensure they use "
                    "pinned action versions and minimal permissions. Monitor for "
                    "unexpected schedule additions via audit log events."
                ),
            }
        )

    # 3. Bot/automation-triggered workflow
    if data.get("actor_is_bot") and event_trigger not in ("schedule", "dynamic"):
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "bot-triggered-workflow",
                "severity": "low",
                "title": f"Bot-triggered workflow: {actor}",
                "description": (
                    f"Workflow '{wf_name}' was triggered by bot '{actor}' via "
                    f"'{event_trigger}' event. Bot-triggered workflows should be "
                    f"reviewed to ensure they have appropriate permissions."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "actor": actor,
                    "trigger": event_trigger,
                    "access_type": access_type,
                },
                "suggested_fix": (
                    "Verify the bot has minimal required permissions. Review the "
                    "workflow for secrets access and write operations."
                ),
            }
        )

    # 4. Dependabot auto-updates (useful to track)
    if event_trigger == "dynamic" and "dependabot" in actor.lower():
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "dependabot-updates",
                "severity": "low",
                "title": f"Dependabot auto-update: {wf_name[:50]}",
                "description": (
                    f"Dependabot triggered workflow '{wf_name[:80]}' for automated "
                    f"dependency updates. While generally safe, review auto-merge "
                    f"settings and ensure Dependabot PRs go through CI checks."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "actor": actor,
                    "trigger": event_trigger,
                },
                "suggested_fix": (
                    "Ensure Dependabot PRs require passing CI checks before merge. "
                    "Review auto-merge rules and consider requiring approval for "
                    "major version bumps."
                ),
            }
        )

    # 5. workflow_run trigger (chained workflows)
    if event_trigger == "workflow_run":
        findings.append(
            {
                "repo": repo,
                "org": org,
                "workflow_path": wf_path,
                "rule_id": "chained-workflow",
                "severity": "low",
                "title": f"Chained workflow: {wf_name}",
                "description": (
                    f"Workflow '{wf_name}' is triggered by another workflow (workflow_run "
                    f"event). Chained workflows can escalate privileges if the downstream "
                    f"workflow has broader permissions than the trigger."
                ),
                "details": {
                    "workflow_name": wf_name,
                    "actor": actor,
                    "trigger": event_trigger,
                },
                "suggested_fix": (
                    "Review permissions of chained workflows. The downstream workflow "
                    "should not have broader access than necessary. Consider using "
                    "reusable workflows with explicit permission inheritance."
                ),
            }
        )

    return findings


# ── Main analysis logic ──────────────────────────────────────────────────────


async def _analyze_events() -> dict:
    """Analyze workflow events in the DB and create findings.

    Zero GitHub API calls — reads only from the events table.
    """
    session_factory = _make_session_factory()
    stats = {
        "events_analyzed": 0,
        "findings_created": 0,
        "repos_seen": 0,
    }

    all_findings: list[dict] = []
    repos_seen: set[str] = set()

    async with session_factory() as session:
        stmt = (
            select(
                text("repo"),
                text("org"),
                text("data"),
                text("action"),
            )
            .select_from(text("events"))
            .where(
                text(
                    "action IN ('workflows.prepared_workflow_job', "
                    "'workflows.completed_workflow_run', "
                    "'workflows.created_workflow_run')"
                )
            )
            .order_by(text("created_at DESC"))
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

    for repo, org, data, action in rows:
        if not repo or not org or not data:
            continue
        stats["events_analyzed"] += 1
        repos_seen.add(repo)

        if action == "workflows.prepared_workflow_job":
            all_findings.extend(_analyze_prepared_job(data, repo, org))
        elif action == "workflows.completed_workflow_run":
            all_findings.extend(_analyze_completed_run(data, repo, org))
        elif action == "workflows.created_workflow_run":
            all_findings.extend(_analyze_created_run(data, repo, org))

    stats["repos_seen"] = len(repos_seen)
    logger.info(
        "workflow_scan.events_analyzed",
        total_events=stats["events_analyzed"],
        raw_findings=len(all_findings),
        repos=stats["repos_seen"],
    )

    # Deduplicate: keep one finding per (repo, workflow_path, rule_id)
    deduped: dict[tuple[str, str, str], dict] = {}
    for f in all_findings:
        key = (f["repo"], f["workflow_path"], f["rule_id"])
        if key not in deduped:
            deduped[key] = f

    logger.info("workflow_scan.deduped_findings", count=len(deduped))

    # Persist via upsert
    if deduped:
        async with session_factory() as session:
            for finding in deduped.values():
                values = {
                    "repo": finding["repo"],
                    "org": finding["org"],
                    "workflow_path": finding["workflow_path"],
                    "rule_id": finding["rule_id"],
                    "severity": finding["severity"],
                    "title": finding["title"],
                    "description": finding["description"],
                    "details": finding.get("details", {}),
                    "suggested_fix": finding.get("suggested_fix"),
                    "scanned_at": datetime.now(UTC),
                }
                insert_stmt = pg_insert(WorkflowFinding).values(**values)
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=["repo", "workflow_path", "rule_id"],
                    set_={
                        "severity": values["severity"],
                        "title": values["title"],
                        "description": values["description"],
                        "details": values["details"],
                        "suggested_fix": values["suggested_fix"],
                        "scanned_at": values["scanned_at"],
                    },
                )
                await session.execute(upsert_stmt)
                stats["findings_created"] += 1
            await session.commit()

    logger.info("workflow_scan.complete", **stats)
    return stats


@celery_app.task(
    name="app.workers.workflow_scan_worker.scan_all_workflows",
    queue="baseline",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def scan_all_workflows(self: Task) -> dict:
    """Celery task: analyze workflow audit-log events for security issues.

    No GitHub API calls are made — reads events already in the DB.
    """
    logger.info("workflow_scan.task_started")
    return asyncio.run(_analyze_events())


# ── Event-driven scan ────────────────────────────────────────────────────────

# Workflow-related actions that trigger scanning
WORKFLOW_ACTIONS = frozenset(
    [
        "workflows.prepared_workflow_job",
        "workflows.completed_workflow_run",
        "workflows.created_workflow_run",
    ]
)

# Debounce TTL in seconds
_DEBOUNCE_TTL_SECONDS = 30


@celery_app.task(
    name="app.workers.workflow_scan_worker.scan_workflow_events",
    bind=True,
    max_retries=2,
)
def scan_workflow_events_task(self: Task, event_ids: list[int]) -> dict[str, int]:
    """Event-driven scan: analyze specific events for workflow security issues."""
    try:
        return asyncio.run(_scan_specific_events(event_ids))
    except Exception as exc:
        logger.error(
            "workflow_scan.event_driven_failed",
            event_ids=event_ids[:5],
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=30) from exc


async def _scan_specific_events(event_ids: list[int]) -> dict[str, int]:
    """Scan specific events for workflow security issues with debouncing.

    Steps:
    1. Load events by ID from DB
    2. Filter to workflow-relevant actions
    3. Debounce: skip if same org/repo/workflow_path was scanned in last 30s
    4. Create WorkflowScanActivity record
    5. Run analysis functions on each event
    6. Store findings (upsert)
    7. Update activity record with results
    """
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.models.workflow_scan_activity import WorkflowScanActivity

    stats: dict[str, int] = {
        "events_received": len(event_ids),
        "workflow_events": 0,
        "findings_created": 0,
        "scans_debounced": 0,
        "activities_created": 0,
    }

    tmp_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=settings.LOG_LEVEL == "DEBUG",
    )
    tmp_session_factory = async_sessionmaker(
        bind=tmp_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=True)

    try:
        # 1. Load events by ID
        async with tmp_session_factory() as session:
            result = await session.execute(
                select(
                    text("id"),
                    text("repo"),
                    text("org"),
                    text("data"),
                    text("action"),
                )
                .select_from(text("events"))
                .where(text(f"id IN ({','.join(str(eid) for eid in event_ids)})"))
            )
            rows = result.fetchall()

        # 2. Filter to workflow-relevant actions
        workflow_rows = [r for r in rows if r[4] in WORKFLOW_ACTIONS]
        stats["workflow_events"] = len(workflow_rows)

        if not workflow_rows:
            logger.info("workflow_scan.no_workflow_events", event_count=len(event_ids))
            return stats

        # Group events by (org, repo, workflow_path) for debouncing
        grouped: dict[tuple[str, str, str], list[Any]] = {}
        for row in workflow_rows:
            event_id, repo, org, data, action = row
            if not repo or not org or not data:
                continue

            # Extract workflow path from event data
            if action == "workflows.prepared_workflow_job":
                wf_path = _extract_workflow_path(data.get("job_workflow_ref", ""))
            else:
                wf_name = data.get("name", "unknown")
                wf_path = f".github/workflows/{wf_name.lower().replace(' ', '-')}.yml"

            key = (org, repo, wf_path)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(row)

        # 3. Debounce and process each group
        for (org, repo, wf_path), group_rows in grouped.items():
            debounce_key = f"wf_scan:{org}/{repo}/{wf_path}"
            group_event_ids = [r[0] for r in group_rows]

            # Check debounce
            existing = await valkey.get(debounce_key)
            if existing:
                stats["scans_debounced"] = stats["scans_debounced"] + 1
                logger.debug(
                    "workflow_scan.debounced",
                    org=org,
                    repo=repo,
                    workflow_path=wf_path,
                )
                continue

            # Set debounce key
            await valkey.setex(debounce_key, _DEBOUNCE_TTL_SECONDS, "1")

            # 4. Create activity record
            start_time = datetime.now(UTC)
            async with tmp_session_factory() as session:
                activity = WorkflowScanActivity(
                    trigger_event_ids=group_event_ids,
                    org=org,
                    repo=repo,
                    workflow_path=wf_path,
                    started_at=start_time,
                    status="running",
                    data_sources=["audit_log"],
                    checks_performed=[],
                    findings_count=0,
                )
                session.add(activity)
                await session.flush()
                activity_id = activity.id
                await session.commit()

            # 5. Run analysis on each event in the group
            all_findings: list[dict[str, Any]] = []
            checks_performed: set[str] = set()

            for row in group_rows:
                _event_id, row_repo, row_org, data, action = row
                if action == "workflows.prepared_workflow_job":
                    findings = _analyze_prepared_job(data, row_repo, row_org)
                    checks_performed.update(
                        [
                            "self-hosted-runner",
                            "excessive-secrets",
                            "pr-triggered-workflow",
                            "reusable-workflow-chain",
                            "slim-runner-image",
                        ]
                    )
                elif action == "workflows.completed_workflow_run":
                    findings = _analyze_completed_run(data, row_repo, row_org)
                    checks_performed.add("public-repo-workflow")
                elif action == "workflows.created_workflow_run":
                    findings = _analyze_created_run(data, row_repo, row_org)
                    checks_performed.update(
                        [
                            "pat-triggered-workflow",
                            "schedule-triggered",
                            "bot-triggered-workflow",
                            "dependabot-updates",
                            "chained-workflow",
                        ]
                    )
                else:
                    findings = []

                all_findings.extend(findings)

            # 6. Deduplicate and persist findings via upsert
            deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
            for f in all_findings:
                fkey = (f["repo"], f["workflow_path"], f["rule_id"])
                if fkey not in deduped:
                    deduped[fkey] = f

            findings_count = 0
            if deduped:
                async with tmp_session_factory() as session:
                    for finding in deduped.values():
                        values = {
                            "repo": finding["repo"],
                            "org": finding["org"],
                            "workflow_path": finding["workflow_path"],
                            "rule_id": finding["rule_id"],
                            "severity": finding["severity"],
                            "title": finding["title"],
                            "description": finding["description"],
                            "details": finding.get("details", {}),
                            "suggested_fix": finding.get("suggested_fix"),
                            "scanned_at": datetime.now(UTC),
                        }
                        insert_stmt = pg_insert(WorkflowFinding).values(**values)
                        upsert_stmt = insert_stmt.on_conflict_do_update(
                            index_elements=["repo", "workflow_path", "rule_id"],
                            set_={
                                "severity": values["severity"],
                                "title": values["title"],
                                "description": values["description"],
                                "details": values["details"],
                                "suggested_fix": values["suggested_fix"],
                                "scanned_at": values["scanned_at"],
                            },
                        )
                        await session.execute(upsert_stmt)
                        findings_count += 1
                    await session.commit()

            stats["findings_created"] = stats["findings_created"] + findings_count

            # 7. Update activity record
            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            async with tmp_session_factory() as session:
                result = await session.execute(
                    select(WorkflowScanActivity).where(WorkflowScanActivity.id == activity_id)
                )
                act = result.scalar_one()
                act.status = "completed"
                act.completed_at = end_time
                act.duration_ms = duration_ms
                act.findings_count = findings_count
                act.checks_performed = sorted(checks_performed)
                await session.commit()

            stats["activities_created"] = stats["activities_created"] + 1

        logger.info("workflow_scan.event_driven_complete", **stats)
        return stats
    finally:
        await valkey.aclose()
        await tmp_engine.dispose()
