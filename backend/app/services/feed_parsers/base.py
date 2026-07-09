"""Base types and protocol for feed parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class NormalizedIndicator:
    """Common shape for all parsed threat intelligence indicators."""

    indicator_type: str
    value: str
    confidence: float = 0.7
    severity: str = "medium"
    campaign_name: str | None = None
    campaign_description: str | None = None
    source_reference: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    suggested_action_filters: list[str] = field(default_factory=list)
    external_id: str | None = None


@dataclass
class ParseResult:
    """Result of parsing a feed, including warnings and skip counts."""

    indicators: list[NormalizedIndicator] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_count: int = 0
    campaign_name: str | None = None
    campaign_description: str | None = None
    campaign_severity: str | None = None
    campaign_references: list[str] = field(default_factory=list)
    campaign_mitre_attack: list[str] = field(default_factory=list)
    suggested_rules: list[dict[str, Any]] | None = None


class FeedParser(Protocol):
    """Protocol for all feed parsers."""

    def parse(self, content: str, config: dict[str, Any]) -> ParseResult: ...
