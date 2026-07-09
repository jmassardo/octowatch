"""Parser registry — maps parser_type strings to parser implementations."""

from __future__ import annotations

from app.services.feed_parsers.base import FeedParser
from app.services.feed_parsers.custom_json import CustomJSONParser
from app.services.feed_parsers.openssf import OpenSSFParser
from app.services.feed_parsers.plaintext import PlaintextParser
from app.services.feed_parsers.stix21 import STIX21Parser

PARSER_REGISTRY: dict[str, type[FeedParser]] = {
    "plaintext": PlaintextParser,  # type: ignore[dict-item]
    "custom_json": CustomJSONParser,  # type: ignore[dict-item]
    "stix21": STIX21Parser,  # type: ignore[dict-item]
    "openssf_package_analysis": OpenSSFParser,  # type: ignore[dict-item]
}


def get_parser(parser_type: str) -> FeedParser:
    """Instantiate a parser for the given type. Raises ValueError for unknown types."""
    cls = PARSER_REGISTRY.get(parser_type)
    if cls is None:
        supported = ", ".join(sorted(PARSER_REGISTRY.keys()))
        raise ValueError(f"Unknown parser type: {parser_type!r}. Supported: {supported}")
    return cls()  # type: ignore[return-value]
