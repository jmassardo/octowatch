"""OctoWatch-native JSON feed parser with campaign and indicator support."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.services.feed_parsers.base import NormalizedIndicator, ParseResult

logger = structlog.get_logger(__name__)


# ─── Pydantic validation models for the custom JSON schema ────────────────────


class CampaignInfo(BaseModel):
    """Campaign metadata in a custom JSON feed."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    severity: str = Field(default="critical", pattern=r"^(critical|high|medium|low)$")
    references: list[str] = Field(default_factory=list)
    mitre_attack: list[str] = Field(default_factory=list)


class IndicatorGroup(BaseModel):
    """A group of indicators sharing the same type and context."""

    type: str = Field(..., min_length=1)
    values: list[str] = Field(..., min_length=1)
    context: str | None = None
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    severity: str = Field(default="medium", pattern=r"^(critical|high|medium|low)$")
    expires_at: str | None = None


class SuggestedRule(BaseModel):
    """Rule suggestion embedded in a custom JSON feed."""

    name: str
    action_filters: list[str] = Field(default_factory=list)
    match_field: str | None = None
    indicator_types: list[str] = Field(default_factory=list)
    severity: str = "critical"


class CustomJSONFeed(BaseModel):
    """Top-level schema for OctoWatch-native threat intel feeds."""

    schema_version: str = "1.0"
    campaign: CampaignInfo | None = None
    indicators: list[IndicatorGroup]
    suggested_rules: list[SuggestedRule] = Field(default_factory=list)


# ─── Parser implementation ────────────────────────────────────────────────────


class CustomJSONParser:
    """Parse OctoWatch-native JSON threat intel feeds."""

    def parse(self, content: str, config: dict[str, Any]) -> ParseResult:
        import json

        result = ParseResult()

        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            result.warnings.append(f"Invalid JSON: {exc}")
            return result

        try:
            feed = CustomJSONFeed.model_validate(raw)
        except ValidationError as exc:
            result.warnings.append(f"Schema validation failed: {exc.error_count()} errors")
            for err in exc.errors()[:5]:
                result.warnings.append(f"  {'.'.join(str(p) for p in err['loc'])}: {err['msg']}")
            return result

        # Extract campaign info
        if feed.campaign:
            result.campaign_name = feed.campaign.name
            result.campaign_description = feed.campaign.description
            result.campaign_severity = feed.campaign.severity
            result.campaign_references = feed.campaign.references
            result.campaign_mitre_attack = feed.campaign.mitre_attack

        # Extract indicators
        for group in feed.indicators:
            expires_at = _parse_datetime(group.expires_at) if group.expires_at else None
            action_filters = _action_filters_for_type(group.type, feed.suggested_rules)

            for value in group.values:
                value = value.strip()
                if not value:
                    result.skipped_count += 1
                    continue

                metadata: dict[str, Any] = {}
                if group.context:
                    metadata["context"] = group.context
                if feed.campaign and feed.campaign.mitre_attack:
                    metadata["mitre_attack"] = feed.campaign.mitre_attack

                result.indicators.append(
                    NormalizedIndicator(
                        indicator_type=group.type,
                        value=value,
                        confidence=group.confidence,
                        severity=group.severity,
                        campaign_name=feed.campaign.name if feed.campaign else None,
                        source_reference=(
                            feed.campaign.references[0]
                            if feed.campaign and feed.campaign.references
                            else None
                        ),
                        expires_at=expires_at,
                        metadata=metadata,
                        suggested_action_filters=action_filters,
                    )
                )

        return result


def _parse_datetime(value: str) -> datetime | None:
    """Try to parse an ISO 8601 datetime string."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _action_filters_for_type(indicator_type: str, rules: list[SuggestedRule]) -> list[str]:
    """Find action filters from suggested rules that match this indicator type."""
    filters: list[str] = []
    for rule in rules:
        if indicator_type in rule.indicator_types:
            filters.extend(rule.action_filters)
    return list(dict.fromkeys(filters))  # dedupe preserving order
