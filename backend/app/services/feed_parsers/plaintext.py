"""Plaintext line-based feed parser (backwards-compatible default)."""

from __future__ import annotations

from typing import Any

from app.services.feed_parsers.base import NormalizedIndicator, ParseResult


class PlaintextParser:
    """Parse one-indicator-per-line feeds (domains, IPs, etc.)."""

    def parse(self, content: str, config: dict[str, Any]) -> ParseResult:
        result = ParseResult()
        indicator_type = config.get("indicator_type", "domain")
        confidence = config.get("confidence", 0.70)

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue

            # Support CSV: take first column
            value = line.split(",")[0].strip() if "," in line else line
            if not value:
                result.skipped_count += 1
                continue

            result.indicators.append(
                NormalizedIndicator(
                    indicator_type=indicator_type,
                    value=value,
                    confidence=confidence,
                    severity="medium",
                )
            )

        return result
