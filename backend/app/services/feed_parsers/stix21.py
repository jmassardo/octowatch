"""STIX 2.1 JSON bundle parser — extracts indicators from simple equality patterns."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.services.feed_parsers.base import NormalizedIndicator, ParseResult

logger = structlog.get_logger(__name__)

# Map STIX indicator pattern object types to our indicator types
_STIX_TYPE_MAP: dict[str, str] = {
    "domain-name": "domain",
    "ipv4-addr": "ip",
    "ipv6-addr": "ip",
    "email-addr": "commit_author_email",
    "user-account": "github_username",
    "software": "package_name",
    "url": "domain",
}

# Regex for simple STIX equality patterns: [type:property = 'value']
_SIMPLE_PATTERN_RE = re.compile(r"\[\s*([a-z0-9\-]+):(\S+)\s*=\s*'([^']+)'\s*\]")


class STIX21Parser:
    """Parse STIX 2.1 JSON bundles, extracting indicators from simple equality patterns.

    Only supports simple single-comparison patterns like:
        [domain-name:value = 'evil.com']
    Complex patterns with AND/OR/MATCHES are logged as skipped.
    """

    def parse(self, content: str, config: dict[str, Any]) -> ParseResult:
        result = ParseResult()

        try:
            bundle = json.loads(content)
        except json.JSONDecodeError as exc:
            result.warnings.append(f"Invalid JSON: {exc}")
            return result

        if not isinstance(bundle, dict):
            result.warnings.append("STIX bundle must be a JSON object")
            return result

        objects = bundle.get("objects", [])
        if not isinstance(objects, list):
            result.warnings.append("STIX bundle 'objects' must be an array")
            return result

        # Index campaigns and relationships for attribution
        campaigns = _index_campaigns(objects)
        relationships = _index_relationships(objects)

        # Extract campaign info from first campaign SDO
        if campaigns:
            first_campaign = next(iter(campaigns.values()))
            result.campaign_name = first_campaign.get("name")
            result.campaign_description = first_campaign.get("description")
            result.campaign_severity = _stix_severity(first_campaign.get("confidence"))

        for obj in objects:
            if not isinstance(obj, dict) or obj.get("type") != "indicator":
                continue

            pattern = obj.get("pattern", "")
            stix_id = obj.get("id", "")
            stix_confidence = obj.get("confidence")

            # Only handle simple single-comparison patterns
            match = _SIMPLE_PATTERN_RE.search(pattern)
            if not match:
                result.skipped_count += 1
                result.warnings.append(f"Unsupported STIX pattern (skipped): {pattern[:120]}")
                continue

            stix_type = match.group(1)
            value = match.group(3)

            indicator_type = _STIX_TYPE_MAP.get(stix_type)
            if not indicator_type:
                result.skipped_count += 1
                result.warnings.append(f"Unknown STIX object type '{stix_type}' (skipped)")
                continue

            # Resolve campaign attribution via relationships
            campaign_name = _resolve_campaign(stix_id, relationships, campaigns)

            metadata: dict[str, Any] = {"stix_id": stix_id}
            labels = obj.get("labels", [])
            if labels:
                metadata["labels"] = labels
            kill_chain = obj.get("kill_chain_phases", [])
            if kill_chain:
                metadata["kill_chain_phases"] = kill_chain

            result.indicators.append(
                NormalizedIndicator(
                    indicator_type=indicator_type,
                    value=value,
                    confidence=_normalize_confidence(stix_confidence),
                    severity=_stix_severity(stix_confidence),
                    campaign_name=campaign_name or result.campaign_name,
                    source_reference=obj.get("external_references", [{}])[0].get("url")
                    if obj.get("external_references")
                    else None,
                    metadata=metadata,
                    external_id=stix_id,
                )
            )

        return result


def _index_campaigns(objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a lookup of STIX campaign SDOs by id."""
    return {
        obj["id"]: obj for obj in objects if isinstance(obj, dict) and obj.get("type") == "campaign"
    }


def _index_relationships(
    objects: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Build indicator_id → [campaign_id, ...] mapping from relationship SDOs."""
    rels: dict[str, list[str]] = {}
    for obj in objects:
        if not isinstance(obj, dict) or obj.get("type") != "relationship":
            continue
        if obj.get("relationship_type") != "indicates":
            continue
        source = obj.get("source_ref", "")
        target = obj.get("target_ref", "")
        if source.startswith("indicator--") and target.startswith("campaign--"):
            rels.setdefault(source, []).append(target)
    return rels


def _resolve_campaign(
    indicator_id: str,
    relationships: dict[str, list[str]],
    campaigns: dict[str, dict[str, Any]],
) -> str | None:
    """Resolve campaign name for an indicator via relationship SDOs."""
    campaign_ids = relationships.get(indicator_id, [])
    for cid in campaign_ids:
        campaign = campaigns.get(cid)
        if campaign:
            return campaign.get("name")
    return None


def _normalize_confidence(stix_confidence: int | None) -> float:
    """Convert STIX confidence (0-100) to our scale (0.0-1.0)."""
    if stix_confidence is None:
        return 0.7
    return max(0.0, min(1.0, stix_confidence / 100.0))


def _stix_severity(stix_confidence: int | None) -> str:
    """Map STIX confidence to severity level."""
    if stix_confidence is None:
        return "medium"
    if stix_confidence >= 85:
        return "critical"
    if stix_confidence >= 65:
        return "high"
    if stix_confidence >= 40:
        return "medium"
    return "low"
