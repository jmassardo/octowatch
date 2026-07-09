"""Rule Synthesis Engine: auto-generate detection rules from feed indicators.

Creates one rule per indicator_type per campaign. Rules reference x_config engines
that query the indicators table at runtime, so adding new IOCs doesn't create
additional rules — just enriches the existing query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection import RuleDefinition

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RuleTemplate:
    """Template mapping an indicator_type to detection rule configuration."""

    display_name: str
    action_filters: list[str]
    engine: str
    match_field: str
    category: str = "supply_chain"
    logic_type: str = "pattern"
    default_severity: str = "critical"


# Maps indicator_type → rule template
RULE_TEMPLATES: dict[str, RuleTemplate] = {
    "github_username": RuleTemplate(
        display_name="Threat Actor Activity",
        action_filters=["*"],
        engine="threat_intel_actor",
        match_field="actor",
    ),
    "commit_author_email": RuleTemplate(
        display_name="Malicious Commit Author",
        action_filters=["git.push"],
        engine="threat_intel_commit_author",
        match_field="data.author_email",
    ),
    "package_name": RuleTemplate(
        display_name="Malicious Package",
        action_filters=["packages.package_version_published"],
        engine="threat_intel_field",
        match_field="data.package_name",
    ),
    "npm_scope": RuleTemplate(
        display_name="Malicious Package Scope",
        action_filters=["packages.package_version_published"],
        engine="threat_intel_scope",
        match_field="data.package_name",
    ),
    "action_ref": RuleTemplate(
        display_name="Malicious Action Reference",
        action_filters=["workflows.prepared_workflow_job", "git.push"],
        engine="threat_intel_action_ref",
        match_field="data.workflow_action",
    ),
    "ip": RuleTemplate(
        display_name="Threat Intel IP",
        action_filters=["*"],
        engine="threat_intel_ip",
        match_field="source_ip",
        default_severity="high",
    ),
    "domain": RuleTemplate(
        display_name="Malicious Domain",
        action_filters=["org.add_member", "org.update_webhook", "repo.create_webhook"],
        engine="threat_intel_field",
        match_field="data.config.url",
        default_severity="high",
    ),
}


async def synthesize_rules_for_campaign(
    session: AsyncSession,
    campaign_id: int,
    campaign_name: str,
    campaign_slug: str,
    indicator_types: set[str],
    *,
    campaign_severity: str = "critical",
    suggested_rules: list[dict[str, Any]] | None = None,
    feed_id: int | None = None,
) -> list[int]:
    """Generate or update feed-derived rules for a campaign.

    Creates one rule per indicator_type using the RULE_TEMPLATES mapping.
    Returns list of rule IDs created/updated.
    """
    rule_ids: list[int] = []

    # Build a lookup of suggested rule overrides by indicator_type
    overrides: dict[str, dict[str, Any]] = {}
    if suggested_rules:
        for sr in suggested_rules:
            itype = sr.get("indicator_type")
            if itype:
                overrides[itype] = sr

    for indicator_type in indicator_types:
        template = RULE_TEMPLATES.get(indicator_type)
        if not template:
            logger.debug(
                "rule_synthesis.no_template",
                indicator_type=indicator_type,
                campaign=campaign_name,
            )
            continue

        override = overrides.get(indicator_type, {})
        slug = f"feed-{campaign_slug}-{indicator_type}"

        # Build logic_config from template + overrides
        action_filters = override.get("action_filters", template.action_filters)
        severity = override.get("severity", campaign_severity or template.default_severity)

        logic_config: dict[str, Any] = {
            "action_filters": action_filters,
            "confidence": override.get("confidence", 0.85),
            "x_config": {
                "engine": template.engine,
                "check_field": template.match_field,
                "indicator_type": indicator_type,
                "campaign_id": campaign_id,
            },
        }

        rule_id = await _upsert_feed_rule(
            session,
            slug=slug,
            name=f"[{campaign_name}] {template.display_name}",
            description=(
                f"Auto-generated: detects {indicator_type} IOCs from campaign '{campaign_name}'"
            ),
            category=template.category,
            logic_type=template.logic_type,
            default_severity=severity,
            logic_config=logic_config,
            campaign_id=campaign_id,
        )
        rule_ids.append(rule_id)

    return rule_ids


async def disable_expired_feed_rules(session: AsyncSession) -> int:
    """Disable feed-derived rules whose expires_at has passed.

    Returns count of rules disabled.
    """
    result = await session.execute(
        text("""
            UPDATE rule_definitions
            SET enabled = FALSE,
                status = 'expired',
                updated_at = NOW(),
                updated_by = 'system:rule_synthesis'
            WHERE source = 'feed'
              AND enabled = TRUE
              AND expires_at IS NOT NULL
              AND expires_at < NOW()
            RETURNING id
        """)
    )
    disabled_ids = result.scalars().all()
    if disabled_ids:
        logger.info(
            "rule_synthesis.expired_rules_disabled",
            count=len(disabled_ids),
            rule_ids=list(disabled_ids),
        )
    return len(disabled_ids)


async def _upsert_feed_rule(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    description: str,
    category: str,
    logic_type: str,
    default_severity: str,
    logic_config: dict[str, Any],
    campaign_id: int,
) -> int:
    """Create or update a feed-derived rule definition.

    On conflict (slug already exists), update the logic_config, severity,
    and re-enable if previously expired. Returns the rule ID.
    """
    # Check if rule already exists
    existing = await session.execute(select(RuleDefinition).where(RuleDefinition.slug == slug))
    rule = existing.scalar_one_or_none()

    if rule:
        # Update existing rule
        rule.logic_config = logic_config
        rule.default_severity = default_severity
        rule.description = description
        rule.name = name
        rule.campaign_id = campaign_id
        rule.updated_by = "system:rule_synthesis"
        # Re-enable if it was expired
        if rule.status == "expired":
            rule.enabled = True
            rule.status = "active"
            rule.expires_at = None
        logger.debug(
            "rule_synthesis.rule_updated",
            slug=slug,
            rule_id=rule.id,
        )
        await session.flush()
        return rule.id
    else:
        # Create new rule
        new_rule = RuleDefinition(
            slug=slug,
            name=name,
            description=description,
            category=category,
            logic_type=logic_type,
            default_severity=default_severity,
            default_confidence="high",
            logic_config=logic_config,
            enabled=True,
            status="active",
            mode="active",
            version=1,
            source="feed",
            campaign_id=campaign_id,
            created_by="system:rule_synthesis",
        )
        session.add(new_rule)
        await session.flush()
        logger.info(
            "rule_synthesis.rule_created",
            slug=slug,
            rule_id=new_rule.id,
            campaign_id=campaign_id,
        )
        return new_rule.id
