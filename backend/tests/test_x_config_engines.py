"""Tests for the 8 x_config detection engines added to _check_x_config_engine().

Covers: threat_intel_ip, dormant_account, self_action_check, external_fork_check,
unusual_actor_check, non_admin_check, sso_bypass_check, workflow_file_change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.detection_service import _check_x_config_engine

# ─── Helpers ──────────────────────────────────────────────────────────────────


class FakeEvent:
    """Minimal stand-in for AuditEvent."""

    def __init__(
        self,
        action: str = "repos.create",
        actor: str = "octocat",
        data: dict[str, Any] | None = None,
        source_ip: str | None = None,
        org: str | None = None,
        created_at: datetime | None = None,
        actor_is_bot: bool = False,
        event_id: int | None = None,
    ):
        self.id = event_id
        self.action = action
        self.actor = actor
        self.data = data or {}
        self.source_ip = source_ip
        self.org = org
        self.created_at = created_at or datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        self.actor_is_bot = actor_is_bot


class FakeRule:
    """Lightweight stub for RuleDefinition."""

    def __init__(self, logic_config: dict[str, Any]):
        self.id = 1
        self.name = "test-rule"
        self.logic_config = logic_config


def _make_rule(engine: str, **extra: Any) -> FakeRule:
    """Build a FakeRule whose logic_config.x_config uses the given engine."""
    x_config: dict[str, Any] = {"engine": engine, **extra}
    return FakeRule({"x_config": x_config})


def _mock_session_returning(rows: list[Any] | None = None, scalar: Any = "UNSET") -> AsyncMock:
    """Return an AsyncMock session with a configurable execute result."""
    mock_result = MagicMock()
    if scalar != "UNSET":
        mock_result.scalar_one_or_none.return_value = scalar
    if rows is not None:
        mock_result.scalars.return_value.all.return_value = rows
    session = AsyncMock(spec=["execute"])
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ─── threat_intel_ip ──────────────────────────────────────────────────────────


class TestThreatIntelIp:
    """Tests for the threat_intel_ip engine."""

    @pytest.mark.anyio
    async def test_match_returns_true(self) -> None:
        """IP found in threat intel → detection fires."""
        event = FakeEvent(source_ip="198.51.100.1", action="auth.login")
        rule = _make_rule("threat_intel_ip", check_field="source_ip", list_type="tor_exit_nodes")
        session = _mock_session_returning(scalar=MagicMock())  # found
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_match_returns_false(self) -> None:
        """IP not in threat intel → no detection."""
        event = FakeEvent(source_ip="10.0.0.1", action="auth.login")
        rule = _make_rule("threat_intel_ip", check_field="source_ip", list_type="tor_exit_nodes")
        session = _mock_session_returning(scalar=None)
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_source_ip_returns_false(self) -> None:
        """Event without source_ip → skip."""
        event = FakeEvent(action="auth.login")
        rule = _make_rule("threat_intel_ip", check_field="source_ip", list_type="tor_exit_nodes")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_db_error_returns_false(self) -> None:
        """DB error during check → safe fallback, no false detection."""
        event = FakeEvent(source_ip="198.51.100.1", action="auth.login")
        rule = _make_rule("threat_intel_ip", check_field="source_ip", list_type="tor_exit_nodes")
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_without_list_type_still_queries(self) -> None:
        """When list_type is omitted, query should still run without type filter."""
        event = FakeEvent(source_ip="198.51.100.1", action="auth.login")
        rule = _make_rule("threat_intel_ip", check_field="source_ip")
        session = _mock_session_returning(scalar=MagicMock())
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── dormant_account ──────────────────────────────────────────────────────────


class TestDormantAccount:
    """Tests for the dormant_account engine."""

    @pytest.mark.anyio
    async def test_dormant_returns_true(self) -> None:
        """No prior activity → account is dormant → detection fires."""
        event = FakeEvent(
            actor="ghost-user",
            action="repos.create",
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("dormant_account", inactivity_days=90)
        session = _mock_session_returning(scalar=None)  # no prior events
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_active_returns_false(self) -> None:
        """Prior activity found → account is active → no detection."""
        event = FakeEvent(
            actor="active-user",
            action="repos.create",
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("dormant_account", inactivity_days=90)
        session = _mock_session_returning(scalar=42)  # found prior event id
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_actor_returns_false(self) -> None:
        """Event with no actor → skip."""
        event = FakeEvent(action="repos.create")
        event.actor = None  # type: ignore[assignment]
        rule = _make_rule("dormant_account", inactivity_days=90)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_custom_inactivity_days(self) -> None:
        """Custom inactivity_days value is respected."""
        event = FakeEvent(
            actor="user",
            action="repos.create",
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("dormant_account", inactivity_days=30)
        session = _mock_session_returning(scalar=None)
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_db_error_returns_false(self) -> None:
        """DB error → safe fallback."""
        event = FakeEvent(actor="user", action="repos.create", event_id=1)
        rule = _make_rule("dormant_account", inactivity_days=90)
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]


# ─── self_action_check ────────────────────────────────────────────────────────


class TestSelfActionCheck:
    """Tests for the self_action_check engine."""

    @pytest.mark.anyio
    async def test_self_promotion_returns_true(self) -> None:
        """Actor == target user → self-action detected."""
        event = FakeEvent(
            actor="alice",
            action="team.change_member_role",
            data={"user": "alice", "role": "maintainer"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_different_user_returns_false(self) -> None:
        """Actor != target user → not a self-action."""
        event = FakeEvent(
            actor="alice",
            action="team.change_member_role",
            data={"user": "bob", "role": "maintainer"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_member_field_fallback(self) -> None:
        """Falls back to data.member when data.user is absent."""
        event = FakeEvent(
            actor="alice",
            action="team.change_member_role",
            data={"member": "alice"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_case_insensitive(self) -> None:
        """Comparison is case-insensitive."""
        event = FakeEvent(
            actor="Alice",
            action="team.change_member_role",
            data={"user": "alice"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_target_field_returns_false(self) -> None:
        """No target user in data → cannot determine self-action."""
        event = FakeEvent(
            actor="alice",
            action="team.change_member_role",
            data={"role": "maintainer"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_match_actor_to_target_false_passes_through(self) -> None:
        """When match_actor_to_target is false, engine passes through."""
        event = FakeEvent(actor="alice", action="team.change_member_role", data={})
        rule = _make_rule("self_action_check", match_actor_to_target=False)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_actor_returns_false(self) -> None:
        """Event with no actor → skip."""
        event = FakeEvent(action="team.change_member_role", data={"user": "alice"})
        event.actor = None  # type: ignore[assignment]
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_target_login_field(self) -> None:
        """Uses data.target_login as target."""
        event = FakeEvent(
            actor="alice",
            action="team.change_member_role",
            data={"target_login": "alice"},
        )
        rule = _make_rule("self_action_check", match_actor_to_target=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── external_fork_check ─────────────────────────────────────────────────────


class TestExternalForkCheck:
    """Tests for the external_fork_check engine."""

    @pytest.mark.anyio
    async def test_external_org_returns_true(self) -> None:
        """Fork to org not in enterprise → detection fires."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={"forkee_owner": "external-org"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = _mock_session_returning(scalar=None)  # not found in enterprise
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_internal_org_returns_false(self) -> None:
        """Fork to org in enterprise → no detection."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={"forkee_owner": "other-internal"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = _mock_session_returning(scalar=42)  # found in enterprise
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_same_org_returns_false(self) -> None:
        """Fork within the same org → not external."""
        event = FakeEvent(
            action="repo.fork",
            org="my-org",
            data={"forkee_owner": "my-org"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_forkee_fullname_extraction(self) -> None:
        """Extracts org from forkee full_name (org/repo)."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={"forkee": "external-org/my-repo"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = _mock_session_returning(scalar=None)  # not found
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_fork_org_returns_false(self) -> None:
        """No fork destination org in event data → skip."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_check_disabled_passes_through(self) -> None:
        """When check_org_membership is false, engine passes through."""
        event = FakeEvent(action="repo.fork", data={})
        rule = _make_rule("external_fork_check", check_org_membership=False)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_db_error_returns_false(self) -> None:
        """DB error → safe fallback."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={"forkee_owner": "external-org"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_fork_org_field_fallback(self) -> None:
        """Falls back to fork_org, then target_org."""
        event = FakeEvent(
            action="repo.fork",
            org="internal-org",
            data={"fork_org": "external-org"},
        )
        rule = _make_rule("external_fork_check", check_org_membership=True)
        session = _mock_session_returning(scalar=None)
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── unusual_actor_check ─────────────────────────────────────────────────────


class TestUnusualActorCheck:
    """Tests for the unusual_actor_check engine."""

    @pytest.mark.anyio
    async def test_first_publish_returns_true(self) -> None:
        """No prior publish by actor → unusual → detection fires."""
        event = FakeEvent(
            actor="new-publisher",
            action="packages.package_version_published",
            data={"package_name": "my-lib"},
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("unusual_actor_check", scope="package")
        session = _mock_session_returning(scalar=None)  # no prior
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_repeat_publisher_returns_false(self) -> None:
        """Prior publish found → not unusual → no detection."""
        event = FakeEvent(
            actor="regular-publisher",
            action="packages.package_version_published",
            data={"package_name": "my-lib"},
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("unusual_actor_check", scope="package")
        session = _mock_session_returning(scalar=42)  # prior event exists
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_package_name_returns_false(self) -> None:
        """No package name in event data → skip."""
        event = FakeEvent(
            actor="user",
            action="packages.package_version_published",
            data={},
            event_id=100,
        )
        rule = _make_rule("unusual_actor_check", scope="package")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_actor_returns_false(self) -> None:
        """Event with no actor → skip."""
        event = FakeEvent(
            action="packages.package_version_published",
            data={"package_name": "lib"},
        )
        event.actor = None  # type: ignore[assignment]
        rule = _make_rule("unusual_actor_check", scope="package")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_db_error_returns_false(self) -> None:
        """DB error → safe fallback."""
        event = FakeEvent(
            actor="user",
            action="packages.package_version_published",
            data={"package_name": "lib"},
            event_id=1,
        )
        rule = _make_rule("unusual_actor_check", scope="package")
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_name_field_fallback(self) -> None:
        """Falls back to data.name when data.package_name missing."""
        event = FakeEvent(
            actor="user",
            action="packages.package_version_published",
            data={"name": "my-lib"},
            created_at=datetime(2024, 6, 15, tzinfo=UTC),
            event_id=100,
        )
        rule = _make_rule("unusual_actor_check", scope="package")
        session = _mock_session_returning(scalar=None)
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── non_admin_check ─────────────────────────────────────────────────────────


class TestNonAdminCheck:
    """Tests for the non_admin_check engine."""

    @pytest.mark.anyio
    async def test_non_admin_returns_true(self) -> None:
        """Actor is 'member' (not admin) → detection fires."""
        event = FakeEvent(actor="user1", action="audit_log_export.create", org="my-org")
        rule = _make_rule("non_admin_check", required_role="admin")
        session = _mock_session_returning(scalar="member")
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_admin_returns_false(self) -> None:
        """Actor is 'admin' → expected behaviour → no detection."""
        event = FakeEvent(actor="admin1", action="audit_log_export.create", org="my-org")
        rule = _make_rule("non_admin_check", required_role="admin")
        session = _mock_session_returning(scalar="admin")
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_owner_treated_as_admin(self) -> None:
        """Actor with 'owner' role treated as admin → no detection."""
        event = FakeEvent(actor="org-owner", action="audit_log_export.create", org="my-org")
        rule = _make_rule("non_admin_check", required_role="admin")
        session = _mock_session_returning(scalar="owner")
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_unknown_actor_returns_false(self) -> None:
        """Actor not in membership data → skip to avoid false positives."""
        event = FakeEvent(actor="mystery", action="audit_log_export.create", org="my-org")
        rule = _make_rule("non_admin_check", required_role="admin")
        session = _mock_session_returning(scalar=None)  # not found
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_actor_returns_false(self) -> None:
        """Event with no actor → skip."""
        event = FakeEvent(action="audit_log_export.create", org="my-org")
        event.actor = None  # type: ignore[assignment]
        rule = _make_rule("non_admin_check", required_role="admin")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_db_error_returns_false(self) -> None:
        """DB error → safe fallback."""
        event = FakeEvent(actor="user1", action="audit_log_export.create", org="my-org")
        rule = _make_rule("non_admin_check", required_role="admin")
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_org_still_queries(self) -> None:
        """When org is None, still queries membership (any org)."""
        event = FakeEvent(actor="user1", action="audit_log_export.create")
        event.org = None
        rule = _make_rule("non_admin_check", required_role="admin")
        session = _mock_session_returning(scalar="member")
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── sso_bypass_check ────────────────────────────────────────────────────────


class TestSsoBypassCheck:
    """Tests for the sso_bypass_check engine."""

    @pytest.mark.anyio
    async def test_pat_without_sso_returns_true(self) -> None:
        """PAT credential type with no SSO → bypass detected."""
        event = FakeEvent(
            action="auth.token_access",
            data={"credential_type": "pat"},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_sso_login_present_returns_false(self) -> None:
        """SSO login data present → no bypass."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={"sso_login": "alice@corp.com", "credential_type": "pat"},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_saml_auth_returns_false(self) -> None:
        """SAML authentication method → SSO was used."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={"authentication_method": "saml"},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_saml_data_present_returns_false(self) -> None:
        """SAML data present in event → SSO used."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={"saml": {"identity": "alice"}},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_oauth_token_without_sso_returns_true(self) -> None:
        """OAuth token type with no SSO indicators → bypass."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={"credential_type": "oauth_token"},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_token_id_present_returns_true(self) -> None:
        """Token ID present with no SSO → bypass."""
        event = FakeEvent(
            action="auth.token_access",
            data={"token_id": 12345},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_sso_no_non_sso_returns_false(self) -> None:
        """No SSO indicators AND no non-SSO indicators → don't fire."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_check_disabled_passes_through(self) -> None:
        """When check_sso_enforcement is false, engine passes through."""
        event = FakeEvent(action="auth.token_access", data={"credential_type": "pat"})
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=False)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_credential_type_sso_returns_false(self) -> None:
        """credential_type=sso → SSO was used."""
        event = FakeEvent(
            action="auth.oauth_access",
            data={"credential_type": "sso"},
        )
        rule = _make_rule("sso_bypass_check", check_sso_enforcement=True)
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]


# ─── workflow_file_change ─────────────────────────────────────────────────────


class TestWorkflowFileChange:
    """Tests for the workflow_file_change engine."""

    @pytest.mark.anyio
    async def test_matching_file_returns_true(self) -> None:
        """File matching .github/workflows/* → detection fires."""
        event = FakeEvent(
            action="git.push",
            data={"files": [".github/workflows/ci.yml", "README.md"]},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_matching_file_returns_false(self) -> None:
        """No files match pattern → no detection."""
        event = FakeEvent(
            action="git.push",
            data={"files": ["src/main.py", "README.md"]},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_head_commit_modified_files(self) -> None:
        """Files in head_commit.modified → checks pattern."""
        event = FakeEvent(
            action="git.push",
            data={
                "head_commit": {
                    "modified": [".github/workflows/deploy.yml"],
                }
            },
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_workflow_action_no_files_returns_false(self) -> None:
        """Workflow-related action with no file info → skip to avoid false positives."""
        event = FakeEvent(
            action="workflows.completed_workflow_run",
            data={},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_non_workflow_action_no_files_returns_false(self) -> None:
        """Non-workflow action with no file info → skip."""
        event = FakeEvent(
            action="git.push",
            data={},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is False  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_single_file_field(self) -> None:
        """Uses data.file when it's a single path."""
        event = FakeEvent(
            action="git.push",
            data={"file": ".github/workflows/test.yml"},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_no_pattern_passes_through(self) -> None:
        """No path_pattern configured → pass through."""
        event = FakeEvent(action="git.push", data={})
        rule = _make_rule("workflow_file_change")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_workflow_file_field(self) -> None:
        """Uses data.workflow_file for matching."""
        event = FakeEvent(
            action="workflows.completed_workflow_run",
            data={"workflow_file": ".github/workflows/ci.yml"},
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_head_commit_added_files(self) -> None:
        """Files in head_commit.added → checks pattern."""
        event = FakeEvent(
            action="git.push",
            data={
                "head_commit": {
                    "added": [".github/workflows/new-workflow.yml"],
                }
            },
        )
        rule = _make_rule("workflow_file_change", path_pattern=".github/workflows/*")
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]


# ─── Routing / integration ───────────────────────────────────────────────────


class TestXConfigEngineRouting:
    """Integration tests for _check_x_config_engine engine routing."""

    @pytest.mark.anyio
    async def test_no_x_config_returns_true(self) -> None:
        """No x_config in logic_config → True (basic pattern match sufficient)."""
        rule = FakeRule({"action_filters": ["repos.create"]})
        event = FakeEvent()
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_empty_x_config_returns_true(self) -> None:
        """Empty x_config dict → True."""
        rule = FakeRule({"x_config": {}})
        event = FakeEvent()
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_unknown_engine_returns_true(self) -> None:
        """Unknown engine → logs warning, returns True."""
        rule = _make_rule("totally_unknown_engine")
        event = FakeEvent()
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]

    @pytest.mark.anyio
    async def test_health_signal_returns_true(self) -> None:
        """health_signal engine → always True."""
        rule = _make_rule("health_signal", signal_type="aging_vulnerability")
        event = FakeEvent()
        session = AsyncMock()
        assert await _check_x_config_engine(event, rule, session) is True  # type: ignore[arg-type]
