"""Feed parser registry for structured threat intelligence formats."""

from __future__ import annotations

from app.services.feed_parsers.base import NormalizedIndicator, ParseResult
from app.services.feed_parsers.registry import get_parser

__all__ = ["NormalizedIndicator", "ParseResult", "get_parser"]
