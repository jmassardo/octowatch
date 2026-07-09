"""Unit tests for feed parser registry and individual parsers."""

from __future__ import annotations

import json

import pytest

from app.services.feed_parsers import get_parser
from app.services.feed_parsers.base import ParseResult
from app.services.feed_parsers.custom_json import CustomJSONParser
from app.services.feed_parsers.openssf import OpenSSFParser
from app.services.feed_parsers.plaintext import PlaintextParser
from app.services.feed_parsers.stix21 import STIX21Parser

# ─── Registry tests ──────────────────────────────────────────────────────────


class TestRegistry:
    def test_get_plaintext_parser(self) -> None:
        parser = get_parser("plaintext")
        assert isinstance(parser, PlaintextParser)

    def test_get_custom_json_parser(self) -> None:
        parser = get_parser("custom_json")
        assert isinstance(parser, CustomJSONParser)

    def test_get_stix21_parser(self) -> None:
        parser = get_parser("stix21")
        assert isinstance(parser, STIX21Parser)

    def test_get_openssf_parser(self) -> None:
        parser = get_parser("openssf_package_analysis")
        assert isinstance(parser, OpenSSFParser)

    def test_unknown_parser_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown parser type"):
            get_parser("nonexistent")


# ─── Plaintext parser tests ──────────────────────────────────────────────────


class TestPlaintextParser:
    def test_basic_domain_list(self) -> None:
        content = "evil.com\nbad.org\nmalware.net"
        result = PlaintextParser().parse(content, {})
        assert len(result.indicators) == 3
        assert result.indicators[0].value == "evil.com"
        assert result.indicators[0].indicator_type == "domain"
        assert result.indicators[0].confidence == 0.70

    def test_comments_and_blanks_skipped(self) -> None:
        content = "# header\nevil.com\n\n// another comment\nbad.org\n   \n"
        result = PlaintextParser().parse(content, {})
        assert len(result.indicators) == 2

    def test_csv_first_column(self) -> None:
        content = "evil.com,malware,2024-01-01\nbad.org,phishing,2024-02-01"
        result = PlaintextParser().parse(content, {})
        assert result.indicators[0].value == "evil.com"
        assert result.indicators[1].value == "bad.org"

    def test_custom_indicator_type_via_config(self) -> None:
        content = "192.168.1.1\n10.0.0.1"
        result = PlaintextParser().parse(content, {"indicator_type": "ip"})
        assert all(i.indicator_type == "ip" for i in result.indicators)

    def test_custom_confidence_via_config(self) -> None:
        content = "evil.com"
        result = PlaintextParser().parse(content, {"confidence": 0.95})
        assert result.indicators[0].confidence == 0.95

    def test_empty_content(self) -> None:
        result = PlaintextParser().parse("", {})
        assert len(result.indicators) == 0
        assert not result.warnings


# ─── Custom JSON parser tests ────────────────────────────────────────────────


_SAMPLE_CUSTOM_JSON = json.dumps(
    {
        "schema_version": "1.0",
        "campaign": {
            "name": "Miasma",
            "description": "npm supply chain worm targeting CI/CD secrets",
            "severity": "critical",
            "references": ["https://example.com/advisory-123"],
            "mitre_attack": ["T1195.002", "T1528"],
        },
        "indicators": [
            {
                "type": "github_username",
                "values": ["asteroiddao", "liuende501"],
                "context": "Exfiltration accounts",
                "confidence": 0.95,
                "severity": "critical",
            },
            {
                "type": "package_name",
                "values": ["npm:evil-package"],
                "confidence": 0.90,
                "severity": "high",
            },
        ],
        "suggested_rules": [
            {
                "name": "Miasma Actor Push",
                "action_filters": ["git.push"],
                "match_field": "actor",
                "indicator_types": ["github_username"],
                "severity": "critical",
            }
        ],
    }
)


class TestCustomJSONParser:
    def test_full_feed(self) -> None:
        result = CustomJSONParser().parse(_SAMPLE_CUSTOM_JSON, {})
        assert len(result.indicators) == 3
        assert result.campaign_name == "Miasma"
        assert result.campaign_severity == "critical"
        assert result.campaign_mitre_attack == ["T1195.002", "T1528"]

    def test_campaign_attribution(self) -> None:
        result = CustomJSONParser().parse(_SAMPLE_CUSTOM_JSON, {})
        for ind in result.indicators:
            if ind.indicator_type == "github_username":
                assert ind.campaign_name == "Miasma"
                assert ind.confidence == 0.95
                assert ind.severity == "critical"

    def test_action_filters_wired(self) -> None:
        result = CustomJSONParser().parse(_SAMPLE_CUSTOM_JSON, {})
        username_inds = [i for i in result.indicators if i.indicator_type == "github_username"]
        assert username_inds[0].suggested_action_filters == ["git.push"]

    def test_mitre_in_metadata(self) -> None:
        result = CustomJSONParser().parse(_SAMPLE_CUSTOM_JSON, {})
        assert result.indicators[0].metadata.get("mitre_attack") == ["T1195.002", "T1528"]

    def test_invalid_json(self) -> None:
        result = CustomJSONParser().parse("not json", {})
        assert len(result.indicators) == 0
        assert any("Invalid JSON" in w for w in result.warnings)

    def test_schema_validation_failure(self) -> None:
        result = CustomJSONParser().parse(json.dumps({"bad": "data"}), {})
        assert len(result.indicators) == 0
        assert any("Schema validation failed" in w for w in result.warnings)

    def test_no_campaign(self) -> None:
        content = json.dumps(
            {
                "schema_version": "1.0",
                "indicators": [{"type": "domain", "values": ["evil.com"]}],
            }
        )
        result = CustomJSONParser().parse(content, {})
        assert len(result.indicators) == 1
        assert result.campaign_name is None
        assert result.indicators[0].campaign_name is None

    def test_empty_values_skipped(self) -> None:
        content = json.dumps(
            {
                "schema_version": "1.0",
                "indicators": [{"type": "domain", "values": ["evil.com", "", "  "]}],
            }
        )
        result = CustomJSONParser().parse(content, {})
        assert len(result.indicators) == 1
        assert result.skipped_count == 2


# ─── STIX 2.1 parser tests ───────────────────────────────────────────────────


_SAMPLE_STIX_BUNDLE = json.dumps(
    {
        "type": "bundle",
        "id": "bundle--001",
        "objects": [
            {
                "type": "campaign",
                "id": "campaign--abc",
                "name": "APT-X",
                "description": "Advanced persistent threat",
                "confidence": 90,
            },
            {
                "type": "indicator",
                "id": "indicator--001",
                "pattern": "[domain-name:value = 'evil.example.com']",
                "pattern_type": "stix",
                "confidence": 85,
                "labels": ["malicious-activity"],
                "external_references": [{"url": "https://example.com/advisory"}],
            },
            {
                "type": "indicator",
                "id": "indicator--002",
                "pattern": "[ipv4-addr:value = '10.0.0.1']",
                "pattern_type": "stix",
                "confidence": 60,
            },
            {
                "type": "indicator",
                "id": "indicator--003",
                "pattern": "[file:hashes.'SHA-256' = 'abc123']",
                "pattern_type": "stix",
            },
            {
                "type": "relationship",
                "id": "relationship--001",
                "relationship_type": "indicates",
                "source_ref": "indicator--001",
                "target_ref": "campaign--abc",
            },
        ],
    }
)


class TestSTIX21Parser:
    def test_simple_indicators(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        assert len(result.indicators) == 2
        assert result.skipped_count == 1  # file hash unsupported

    def test_domain_extracted(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        domain_ind = [i for i in result.indicators if i.indicator_type == "domain"]
        assert len(domain_ind) == 1
        assert domain_ind[0].value == "evil.example.com"
        assert domain_ind[0].confidence == 0.85

    def test_ip_extracted(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        ip_ind = [i for i in result.indicators if i.indicator_type == "ip"]
        assert len(ip_ind) == 1
        assert ip_ind[0].value == "10.0.0.1"

    def test_campaign_attribution_via_relationship(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        domain_ind = [i for i in result.indicators if i.indicator_type == "domain"][0]
        assert domain_ind.campaign_name == "APT-X"

    def test_stix_id_in_metadata(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        assert result.indicators[0].metadata.get("stix_id") == "indicator--001"

    def test_external_reference_as_source(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        domain_ind = [i for i in result.indicators if i.indicator_type == "domain"][0]
        assert domain_ind.source_reference == "https://example.com/advisory"

    def test_campaign_from_bundle(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        assert result.campaign_name == "APT-X"
        assert result.campaign_description == "Advanced persistent threat"

    def test_confidence_mapping(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        domain_ind = [i for i in result.indicators if i.indicator_type == "domain"][0]
        assert domain_ind.severity == "critical"  # 85 >= 85

        ip_ind = [i for i in result.indicators if i.indicator_type == "ip"][0]
        assert ip_ind.severity == "medium"  # 60 >= 40, < 65

    def test_invalid_json(self) -> None:
        result = STIX21Parser().parse("not json", {})
        assert len(result.indicators) == 0
        assert any("Invalid JSON" in w for w in result.warnings)

    def test_empty_bundle(self) -> None:
        result = STIX21Parser().parse(json.dumps({"type": "bundle", "objects": []}), {})
        assert len(result.indicators) == 0

    def test_unsupported_stix_type_warning(self) -> None:
        result = STIX21Parser().parse(_SAMPLE_STIX_BUNDLE, {})
        assert any("Unknown STIX object type" in w for w in result.warnings)


# ─── OpenSSF parser tests ────────────────────────────────────────────────────


_SAMPLE_OPENSSF = json.dumps(
    [
        {
            "package": {
                "name": "evil-pkg",
                "ecosystem": "npm",
                "version": "1.0.0",
                "maintainers": [
                    {"email": "attacker@evil.com"},
                ],
            },
            "analysis": {
                "verdict": "malicious",
                "behaviors": ["exfiltration", "code_execution"],
            },
            "url": "https://openssf.org/analysis/evil-pkg",
        },
        {
            "package": {
                "name": "safe-pkg",
                "ecosystem": "pypi",
                "version": "2.0.0",
            },
            "analysis": {"verdict": "benign"},
        },
    ]
)


class TestOpenSSFParser:
    def test_malicious_package_extracted(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        pkg_inds = [i for i in result.indicators if i.indicator_type == "package_name"]
        assert len(pkg_inds) == 1
        assert pkg_inds[0].value == "npm:evil-pkg"
        assert pkg_inds[0].confidence == 0.90

    def test_benign_skipped(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        assert result.skipped_count >= 1

    def test_maintainer_email_extracted(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        email_inds = [i for i in result.indicators if i.indicator_type == "commit_author_email"]
        assert len(email_inds) == 1
        assert email_inds[0].value == "attacker@evil.com"

    def test_ecosystem_in_metadata(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        pkg_ind = [i for i in result.indicators if i.indicator_type == "package_name"][0]
        assert pkg_ind.metadata.get("ecosystem") == "npm"
        assert pkg_ind.metadata.get("version") == "1.0.0"

    def test_action_filters_for_packages(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        pkg_ind = [i for i in result.indicators if i.indicator_type == "package_name"][0]
        assert "packages.package_created" in pkg_ind.suggested_action_filters

    def test_external_id_includes_version(self) -> None:
        result = OpenSSFParser().parse(_SAMPLE_OPENSSF, {})
        pkg_ind = [i for i in result.indicators if i.indicator_type == "package_name"][0]
        assert pkg_ind.external_id == "npm:evil-pkg@1.0.0"

    def test_single_object_input(self) -> None:
        single = json.dumps(
            {
                "package": {"name": "bad", "ecosystem": "pypi"},
                "analysis": {"verdict": "malicious"},
            }
        )
        result = OpenSSFParser().parse(single, {})
        assert len(result.indicators) == 1
        assert result.indicators[0].value == "pypi:bad"

    def test_invalid_json(self) -> None:
        result = OpenSSFParser().parse("not json", {})
        assert any("Invalid JSON" in w for w in result.warnings)

    def test_behavior_based_detection(self) -> None:
        """Package without explicit verdict but with malicious behaviors."""
        content = json.dumps(
            {
                "package": {"name": "sneaky", "ecosystem": "npm"},
                "analysis": {"behaviors": ["exfiltration"]},
            }
        )
        result = OpenSSFParser().parse(content, {})
        assert len(result.indicators) == 1


# ─── ParseResult structure tests ─────────────────────────────────────────────


class TestParseResult:
    def test_defaults(self) -> None:
        result = ParseResult()
        assert result.indicators == []
        assert result.warnings == []
        assert result.skipped_count == 0
        assert result.campaign_name is None
