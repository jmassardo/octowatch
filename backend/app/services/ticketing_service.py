"""Ticketing service: create/update tickets in Jira and GitHub Issues."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import structlog
from atlassian import Jira
from github import Github, GithubException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection import Detection
from app.models.integration import Ticket, TicketingConfig

logger = structlog.get_logger(__name__)


async def get_ticketing_config(
    session: AsyncSession,
    config_id: int,
) -> TicketingConfig | None:
    result = await session.execute(select(TicketingConfig).where(TicketingConfig.id == config_id))
    return result.scalar_one_or_none()


async def list_ticketing_configs(
    session: AsyncSession,
    org: str | None = None,
) -> list[TicketingConfig]:
    stmt = select(TicketingConfig).where(TicketingConfig.enabled.is_(True))
    if org:
        stmt = stmt.where(TicketingConfig.org == org)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _get_credential(config: TicketingConfig) -> str:
    """Read credential from the env var named in config.credential_env_var (never hardcoded)."""
    env_var = config.credential_env_var
    if not env_var:
        raise ValueError(f"ticketing_config {config.id}: credential_env_var not set")
    token = os.environ.get(env_var, "").strip()
    if not token:
        raise ValueError(f"ticketing_config {config.id}: env var '{env_var}' is empty or unset")
    return token


async def create_ticket_for_detection(
    session: AsyncSession,
    detection: Detection,
    config: TicketingConfig,
    created_by: str,
) -> Ticket:
    """Create a ticket in the configured backend and persist a Ticket record."""
    external_id: str | None = None
    external_url: str | None = None

    try:
        if config.platform == "jira":
            external_id, external_url = await _create_jira_issue(detection, config)
        elif config.platform == "github":
            external_id, external_url = await _create_github_issue(detection, config)
        else:
            logger.warning("ticketing.unsupported_platform", platform=config.platform)
            raise ValueError(f"Unsupported ticketing platform: {config.platform}")
    except Exception as exc:
        logger.error(
            "ticketing.create_failed",
            platform=config.platform,
            detection_id=detection.id,
            error=str(exc),
        )
        raise

    ticket = Ticket(
        detection_id=detection.id,
        ticketing_config_id=config.id,
        platform=config.platform,
        external_id=external_id,
        external_url=external_url,
        status="open",
        created_by=created_by,
    )
    session.add(ticket)
    await session.flush()

    logger.info(
        "ticketing.ticket_created",
        platform=config.platform,
        external_id=external_id,
        detection_id=detection.id,
    )
    return ticket


async def sync_ticket_statuses(session: AsyncSession) -> int:
    """Sync ticket status from external platforms. Returns count of updated tickets."""
    stmt = select(Ticket).where(Ticket.status.notin_(["closed", "resolved", "done"]))
    result = await session.execute(stmt)
    tickets = result.scalars().all()

    updated = 0
    for ticket in tickets:
        if not ticket.ticketing_config_id:
            continue
        config = await get_ticketing_config(session, ticket.ticketing_config_id)
        if not config or not config.enabled:
            continue
        try:
            if config.platform == "jira":
                new_status = await _get_jira_issue_status(ticket, config)
            elif config.platform == "github":
                new_status = await _get_github_issue_status(ticket, config)
            else:
                continue

            if new_status and new_status != ticket.status:
                ticket.status = new_status
                ticket.updated_at = datetime.now(UTC)
                updated += 1
        except Exception as exc:
            logger.warning(
                "ticketing.sync_failed",
                ticket_id=ticket.id,
                external_id=ticket.external_id,
                error=str(exc),
            )

    if updated:
        await session.flush()

    return updated


async def _create_jira_issue(
    detection: Detection,
    config: TicketingConfig,
) -> tuple[str, str]:
    """Create a Jira issue. Returns (issue_key, browse_url)."""
    token = _get_credential(config)
    extra: dict[str, Any] = config.extra_config or {}

    jira = Jira(
        url=config.base_url,
        token=token,
    )

    project_key = extra.get("project_key", "SEC")
    issue_type = extra.get("issue_type", "Bug")
    priority_map = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    jira_priority = priority_map.get(detection.severity, "Medium")

    description = (
        f"*Detection ID:* {detection.id}\n\n"
        f"*Actor:* {detection.actor or 'N/A'}\n"
        f"*Org:* {detection.org or 'N/A'}\n"
        f"*Severity:* {detection.severity}\n"
        f"*Confidence:* {detection.confidence} ({detection.confidence_score:.2f})\n\n"
        f"*Description:*\n{detection.description}"
    )

    issue_dict = {
        "project": {"key": project_key},
        "summary": f"[Security Alert] {detection.title}",
        "description": description,
        "issuetype": {"name": issue_type},
        "priority": {"name": jira_priority},
    }

    # Use synchronous Jira client in a thread pool in production;
    # for now call directly (blocking) — acceptable in Celery worker context
    new_issue = jira.issue_create(fields=issue_dict)
    issue_key = new_issue.get("key") or new_issue.get("id", "UNKNOWN")
    browse_url = f"{config.base_url.rstrip('/')}/browse/{issue_key}"

    return str(issue_key), browse_url


async def _create_github_issue(
    detection: Detection,
    config: TicketingConfig,
) -> tuple[str, str]:
    """Create a GitHub Issue. Returns (issue_number_str, html_url)."""
    token = _get_credential(config)
    extra: dict[str, Any] = config.extra_config or {}
    repo_slug = extra.get("repo", "")  # e.g. "org/repo"

    if not repo_slug:
        raise ValueError(f"ticketing_config {config.id}: extra_config.repo not set")

    gh = Github(token)
    repo = gh.get_repo(repo_slug)

    label_name = extra.get("label", "security-alert")
    body = (
        f"## Security Detection\n\n"
        f"**Detection ID:** {detection.id}\n"
        f"**Actor:** {detection.actor or 'N/A'}\n"
        f"**Org:** {detection.org or 'N/A'}\n"
        f"**Severity:** {detection.severity}\n"
        f"**Confidence:** {detection.confidence} ({detection.confidence_score:.2f})\n\n"
        f"### Description\n\n{detection.description}"
    )

    try:
        label = repo.get_label(label_name)
    except GithubException:
        label = repo.create_label(label_name, "d73a4a")

    issue = repo.create_issue(
        title=f"[Security Alert] {detection.title}",
        body=body,
        labels=[label],
    )

    return str(issue.number), issue.html_url


async def _get_jira_issue_status(
    ticket: Ticket,
    config: TicketingConfig,
) -> str | None:
    try:
        token = _get_credential(config)
        jira = Jira(url=config.base_url, token=token)
        issue = jira.issue(ticket.external_id)
        return issue["fields"]["status"]["name"].lower()
    except Exception:
        return None


async def _get_github_issue_status(
    ticket: Ticket,
    config: TicketingConfig,
) -> str | None:
    try:
        token = _get_credential(config)
        extra: dict[str, Any] = config.extra_config or {}
        repo_slug = extra.get("repo", "")
        if not repo_slug:
            return None

        gh = Github(token)
        repo = gh.get_repo(repo_slug)
        issue = repo.get_issue(int(ticket.external_id))
        return issue.state  # "open" or "closed"
    except Exception:
        return None
