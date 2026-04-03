"""Rule management service: CRUD + version history + GitHub repo sync."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import structlog
import yaml
from github import Github, GithubException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.detection import RuleDefinition, RuleVersion
from app.schemas.detection import RuleCreate, RuleStatusUpdate

logger = structlog.get_logger(__name__)

_RULE_CACHE_TTL = 60  # seconds


def _rule_to_yaml(rule: RuleDefinition) -> str:
    """Serialise a rule to YAML for committing to GitHub."""
    data = {
        "name": rule.name,
        "slug": rule.slug,
        "description": rule.description,
        "logic_type": rule.logic_type,
        "logic_config": rule.logic_config,
        "default_severity": rule.default_severity,
        "enabled": rule.enabled,
        "status": rule.status,
        "version": rule.version,
    }
    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def _push_rule_to_github(rule: RuleDefinition, actor: str, message: str) -> None:
    """Commit the rule YAML to the configured GitHub repository.

    Silently skips (with a warning log) if GITHUB_RULES_REPO or
    GITHUB_RULES_TOKEN are not configured, so the service degrades
    gracefully in environments without GitHub rule sync.
    """
    repo_name = settings.GIT.GITHUB_RULES_REPO
    token = settings.GIT.GITHUB_RULES_TOKEN
    branch = settings.GIT.GITHUB_RULES_BRANCH

    if not repo_name or not token:
        logger.warning(
            "rule.github_sync_skipped",
            reason="GITHUB_RULES_REPO or GITHUB_RULES_TOKEN not configured",
            slug=rule.slug,
        )
        return

    path = f"rules/{rule.slug}.yaml"
    content = _rule_to_yaml(rule)

    try:
        gh = Github(token)
        repo = gh.get_repo(repo_name)
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(
                path=path,
                message=f"{message} [{actor}]",
                content=content,
                sha=existing.sha,  # type: ignore[union-attr]
                branch=branch,
            )
        except GithubException as exc:
            if exc.status == 404:
                repo.create_file(
                    path=path,
                    message=f"{message} [{actor}]",
                    content=content,
                    branch=branch,
                )
            else:
                raise
        logger.info("rule.github_synced", slug=rule.slug, repo=repo_name, path=path)
    except GithubException as exc:
        # Non-fatal: log and continue so rule mutations still succeed in DB
        logger.error(
            "rule.github_sync_failed",
            slug=rule.slug,
            status=exc.status,
            error=str(exc.data),
        )


async def list_rules(
    session: AsyncSession,
    *,
    enabled: bool | None = None,
    logic_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RuleDefinition], int]:
    base = select(RuleDefinition)
    if enabled is not None:
        base = base.where(RuleDefinition.enabled.is_(enabled))
    if logic_type:
        base = base.where(RuleDefinition.logic_type == logic_type)
    if status:
        base = base.where(RuleDefinition.status == status)

    from sqlalchemy import func

    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    stmt = base.order_by(RuleDefinition.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def get_rule_by_id(session: AsyncSession, rule_id: int) -> RuleDefinition | None:
    result = await session.execute(select(RuleDefinition).where(RuleDefinition.id == rule_id))
    return result.scalar_one_or_none()


async def get_rule_by_slug(session: AsyncSession, slug: str) -> RuleDefinition | None:
    result = await session.execute(select(RuleDefinition).where(RuleDefinition.slug == slug))
    return result.scalar_one_or_none()


async def create_rule(
    session: AsyncSession,
    payload: RuleCreate,
    created_by: str,
) -> RuleDefinition:
    rule = RuleDefinition(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        category=payload.category,
        default_severity=payload.default_severity,
        default_confidence=payload.default_confidence,
        logic_type=payload.logic_type,
        logic_config=payload.logic_config,
        enabled=payload.enabled,
        status="draft",
        version=1,
        created_by=created_by,
    )
    session.add(rule)
    await session.flush()

    # Write initial version snapshot
    await _create_version_snapshot(session, rule, created_by, comment="Initial version")

    _push_rule_to_github(rule, created_by, f"feat(rules): add {rule.slug} v{rule.version}")
    logger.info("rule.created", rule_id=rule.id, slug=rule.slug, actor=created_by)
    return rule


async def update_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    payload: RuleCreate,
    updated_by: str,
) -> RuleDefinition:
    # Detect real change
    old_config_hash = hashlib.sha256(
        json.dumps(rule.logic_config, sort_keys=True).encode()
    ).hexdigest()
    new_config_hash = hashlib.sha256(
        json.dumps(payload.logic_config, sort_keys=True).encode()
    ).hexdigest()

    rule.name = payload.name
    rule.description = payload.description
    rule.category = payload.category
    rule.default_severity = payload.default_severity
    rule.default_confidence = payload.default_confidence
    rule.logic_type = payload.logic_type
    rule.logic_config = payload.logic_config
    rule.enabled = payload.enabled
    rule.updated_by = updated_by
    rule.updated_at = datetime.now(UTC)

    if old_config_hash != new_config_hash:
        rule.version += 1
        await _create_version_snapshot(session, rule, updated_by)

    await session.flush()
    _push_rule_to_github(rule, updated_by, f"fix(rules): update {rule.slug} v{rule.version}")
    logger.info("rule.updated", rule_id=rule.id, slug=rule.slug, actor=updated_by)
    return rule


async def update_rule_status(
    session: AsyncSession,
    rule: RuleDefinition,
    payload: RuleStatusUpdate,
    updated_by: str,
) -> RuleDefinition:
    if payload.status not in ("draft", "active", "deprecated"):
        raise ValueError(f"Invalid status: {payload.status}")
    rule.status = payload.status
    rule.updated_at = datetime.now(UTC)
    await session.flush()
    logger.info(
        "rule.status_changed",
        rule_id=rule.id,
        new_status=payload.status,
        actor=updated_by,
    )
    return rule


async def delete_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    deleted_by: str,
) -> None:
    # Soft-delete: mark deprecated
    rule.status = "deprecated"
    rule.enabled = False
    rule.updated_at = datetime.now(UTC)
    await session.flush()
    _push_rule_to_github(rule, deleted_by, f"chore(rules): deprecate {rule.slug}")
    logger.info("rule.deleted", rule_id=rule.id, slug=rule.slug, actor=deleted_by)


async def get_rule_versions(
    session: AsyncSession,
    rule_id: int,
    limit: int = 20,
) -> list[RuleVersion]:
    result = await session.execute(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule_id)
        .order_by(RuleVersion.version.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _create_version_snapshot(
    session: AsyncSession,
    rule: RuleDefinition,
    actor: str,
    comment: str | None = None,
) -> RuleVersion:
    snapshot = RuleVersion(
        rule_id=rule.id,
        version=rule.version,
        logic_config=rule.logic_config,
        changed_by=actor,
        change_summary=comment,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def invalidate_rule_cache(valkey_client: Redis, rule_id: int) -> None:
    """Invalidate the Valkey cache for a single rule (called after mutations)."""
    key = f"rule:cache:{rule_id}"
    await valkey_client.delete(key)
    logger.debug("rule.cache_invalidated", rule_id=rule_id)
