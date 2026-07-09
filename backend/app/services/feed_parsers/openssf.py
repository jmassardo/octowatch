"""OpenSSF Package Analysis JSON output parser."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.feed_parsers.base import NormalizedIndicator, ParseResult

logger = structlog.get_logger(__name__)

# Map OpenSSF ecosystem names to canonical prefixes
_ECOSYSTEM_MAP: dict[str, str] = {
    "npm": "npm",
    "pypi": "pypi",
    "rubygems": "rubygems",
    "crates.io": "crates",
    "packagist": "packagist",
    "nuget": "nuget",
    "pub": "pub",
}


class OpenSSFParser:
    """Parse OpenSSF Package Analysis JSON output.

    Supports both single-result objects and arrays of results.
    Each result should contain package info and analysis verdicts.
    """

    def parse(self, content: str, config: dict[str, Any]) -> ParseResult:
        result = ParseResult()

        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            result.warnings.append(f"Invalid JSON: {exc}")
            return result

        # Support both single object and array
        items = raw if isinstance(raw, list) else [raw]

        for item in items:
            if not isinstance(item, dict):
                result.skipped_count += 1
                continue

            try:
                self._parse_item(item, result)
            except Exception as exc:
                result.skipped_count += 1
                result.warnings.append(f"Failed to parse item: {exc}")

        return result

    def _parse_item(self, item: dict[str, Any], result: ParseResult) -> None:
        """Parse a single Package Analysis result."""
        package = item.get("package", {})
        if not isinstance(package, dict):
            result.skipped_count += 1
            return

        name = package.get("name", "")
        ecosystem = package.get("ecosystem", "").lower()
        version = package.get("version", "")

        if not name:
            result.skipped_count += 1
            return

        # Canonical package identifier: ecosystem:name
        eco_prefix = _ECOSYSTEM_MAP.get(ecosystem, ecosystem)
        canonical_value = f"{eco_prefix}:{name}" if eco_prefix else name

        # Extract verdict / analysis results
        analysis = item.get("analysis", item.get("result", {}))
        if not isinstance(analysis, dict):
            analysis = {}

        verdict = analysis.get("verdict", item.get("verdict", ""))
        is_malicious = _is_malicious_verdict(verdict, analysis)

        if not is_malicious:
            result.skipped_count += 1
            return

        # Build metadata
        metadata: dict[str, Any] = {"ecosystem": ecosystem}
        if version:
            metadata["version"] = version
        behaviors = analysis.get("behaviors", [])
        if behaviors:
            metadata["behaviors"] = behaviors[:20]
        source_url = item.get("source_url") or item.get("url")
        if source_url:
            metadata["source_url"] = source_url

        # Extract maintainer info as a separate indicator
        maintainers = package.get("maintainers", [])
        for maint in maintainers:
            if isinstance(maint, dict):
                email = maint.get("email")
                if email:
                    result.indicators.append(
                        NormalizedIndicator(
                            indicator_type="commit_author_email",
                            value=email,
                            confidence=0.5,
                            severity="medium",
                            metadata={
                                "context": f"Maintainer of malicious package {canonical_value}",
                            },
                        )
                    )

        result.indicators.append(
            NormalizedIndicator(
                indicator_type="package_name",
                value=canonical_value,
                confidence=0.90,
                severity="high",
                source_reference=metadata.get("source_url"),
                metadata=metadata,
                suggested_action_filters=["packages.package_created", "packages.package_published"],
                external_id=f"{canonical_value}@{version}" if version else None,
            )
        )


def _is_malicious_verdict(
    verdict: str | Any,
    analysis: dict[str, Any],
) -> bool:
    """Determine if the analysis verdict indicates a malicious package."""
    if isinstance(verdict, str) and verdict:
        return verdict.lower() in ("malicious", "suspicious", "harmful")

    # Some formats use boolean verdicts
    if isinstance(verdict, bool):
        return verdict

    # Fallback: check for specific malicious behavior flags
    behaviors = analysis.get("behaviors", [])
    malicious_behaviors = {"exfiltration", "code_execution", "network_access", "file_system_access"}
    return bool(set(behaviors) & malicious_behaviors)
