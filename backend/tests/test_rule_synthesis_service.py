"""Tests for rule_synthesis_service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rule_synthesis_service import (
    RULE_TEMPLATES,
    RuleTemplate,
    synthesize_rules_for_campaign,
)


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    return session


class TestRuleTemplates:
    """Test that rule templates are correctly defined."""

    def test_all_indicator_types_have_templates(self):
        """Verify expected indicator types are covered."""
        expected = {
            "github_username",
            "commit_author_email",
            "package_name",
            "npm_scope",
            "action_ref",
            "ip",
            "domain",
        }
        assert set(RULE_TEMPLATES.keys()) == expected

    def test_template_structure(self):
        """Each template must have required fields."""
        for itype, tmpl in RULE_TEMPLATES.items():
            assert isinstance(tmpl, RuleTemplate), f"{itype} not a RuleTemplate"
            assert tmpl.display_name, f"{itype} missing display_name"
            assert tmpl.action_filters, f"{itype} missing action_filters"
            assert tmpl.engine, f"{itype} missing engine"
            assert tmpl.match_field, f"{itype} missing match_field"

    def test_github_username_template(self):
        tmpl = RULE_TEMPLATES["github_username"]
        assert tmpl.engine == "threat_intel_actor"
        assert tmpl.action_filters == ["*"]
        assert tmpl.default_severity == "critical"

    def test_action_ref_template(self):
        tmpl = RULE_TEMPLATES["action_ref"]
        assert tmpl.engine == "threat_intel_action_ref"
        assert "workflows.prepared_workflow_job" in tmpl.action_filters

    def test_ip_template_severity(self):
        """IP indicators default to high (not critical)."""
        tmpl = RULE_TEMPLATES["ip"]
        assert tmpl.default_severity == "high"


class TestSynthesizeRulesForCampaign:
    """Test rule synthesis logic."""

    @pytest.mark.asyncio
    async def test_creates_rules_for_known_types(self, mock_session):
        """Should create a rule for each supported indicator type."""
        # Mock: no existing rule
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        indicator_types = {"github_username", "action_ref"}

        rule_ids = await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=42,
            campaign_name="Evil Campaign",
            campaign_slug="evil-campaign",
            indicator_types=indicator_types,
        )

        # Should have created 2 rules (one per type)
        assert len(rule_ids) == 2
        # session.add should have been called twice
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_unknown_indicator_types(self, mock_session):
        """Unknown indicator types should be skipped without error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        rule_ids = await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=1,
            campaign_name="Test",
            campaign_slug="test",
            indicator_types={"unknown_type", "also_unknown"},
        )

        assert rule_ids == []
        assert mock_session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_updates_existing_rule(self, mock_session):
        """If rule with same slug exists, update it rather than create."""
        existing_rule = MagicMock()
        existing_rule.id = 99
        existing_rule.status = "active"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_rule
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        rule_ids = await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=5,
            campaign_name="Updated Campaign",
            campaign_slug="updated-campaign",
            indicator_types={"github_username"},
        )

        assert rule_ids == [99]
        # Should NOT call session.add (update in place)
        assert mock_session.add.call_count == 0
        # Should have updated fields
        assert existing_rule.campaign_id == 5
        assert existing_rule.updated_by == "system:rule_synthesis"

    @pytest.mark.asyncio
    async def test_re_enables_expired_rule(self, mock_session):
        """Expired rules should be re-enabled on update."""
        existing_rule = MagicMock()
        existing_rule.id = 77
        existing_rule.status = "expired"
        existing_rule.enabled = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_rule
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=3,
            campaign_name="Revived",
            campaign_slug="revived",
            indicator_types={"npm_scope"},
        )

        assert existing_rule.enabled is True
        assert existing_rule.status == "active"
        assert existing_rule.expires_at is None

    @pytest.mark.asyncio
    async def test_uses_suggested_rule_overrides(self, mock_session):
        """Suggested rules from feed should override template defaults."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        suggested = [
            {
                "indicator_type": "github_username",
                "action_filters": ["org.add_member"],
                "severity": "medium",
                "confidence": 0.7,
            }
        ]

        await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=10,
            campaign_name="Custom",
            campaign_slug="custom",
            indicator_types={"github_username"},
            suggested_rules=suggested,
        )

        # Verify the rule was created with overridden values
        added_rule = mock_session.add.call_args[0][0]
        assert added_rule.default_severity == "medium"
        assert added_rule.logic_config["action_filters"] == ["org.add_member"]
        assert added_rule.logic_config["confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_slug_format(self, mock_session):
        """Rule slug should follow feed-{campaign_slug}-{indicator_type} pattern."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=1,
            campaign_name="Evil Corp",
            campaign_slug="evil-corp",
            indicator_types={"ip"},
        )

        added_rule = mock_session.add.call_args[0][0]
        assert added_rule.slug == "feed-evil-corp-ip"

    @pytest.mark.asyncio
    async def test_logic_config_structure(self, mock_session):
        """Verify the logic_config has correct structure for engine matching."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=7,
            campaign_name="Test",
            campaign_slug="test",
            indicator_types={"action_ref"},
        )

        added_rule = mock_session.add.call_args[0][0]
        config = added_rule.logic_config
        assert "x_config" in config
        assert config["x_config"]["engine"] == "threat_intel_action_ref"
        assert config["x_config"]["indicator_type"] == "action_ref"
        assert config["x_config"]["campaign_id"] == 7
        assert config["x_config"]["check_field"] == "data.workflow_action"

    @pytest.mark.asyncio
    async def test_campaign_severity_propagates(self, mock_session):
        """Campaign severity should be used as rule severity."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        await synthesize_rules_for_campaign(
            mock_session,
            campaign_id=1,
            campaign_name="High Sev",
            campaign_slug="high-sev",
            indicator_types={"package_name"},
            campaign_severity="high",
        )

        added_rule = mock_session.add.call_args[0][0]
        assert added_rule.default_severity == "high"
