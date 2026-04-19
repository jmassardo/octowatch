"""Unit tests for setup schemas validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.setup import (
    GitHubAppSetup,
    GitHubOAuthSetup,
    InitialAdminsSetup,
    SettingUpdate,
    SetupLoginRequest,
    SetupStatusResponse,
    TLSSetup,
)


class TestSetupLoginRequest:
    def test_valid_token(self) -> None:
        req = SetupLoginRequest(token="my-setup-token")
        assert req.token == "my-setup-token"

    def test_empty_token_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SetupLoginRequest(token="")


class TestGitHubOAuthSetup:
    def test_valid_payload(self) -> None:
        payload = GitHubOAuthSetup(client_id="my-id", client_secret="my-secret")
        assert payload.client_id == "my-id"
        assert payload.client_secret == "my-secret"

    def test_empty_client_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GitHubOAuthSetup(client_id="", client_secret="secret")

    def test_empty_client_secret_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GitHubOAuthSetup(client_id="id", client_secret="")


class TestGitHubAppSetup:
    def test_valid_payload(self) -> None:
        pem = "-----BEGIN RSA PRIVATE KEY-----\n" + ("A" * 200) + "\n-----END RSA PRIVATE KEY-----"
        payload = GitHubAppSetup(
            app_id="12345",
            private_key_pem=pem,
            enterprise_slug="my-enterprise",
        )
        assert payload.app_id == "12345"
        assert payload.sync_enabled is True
        assert payload.sync_interval_days == 1

    def test_invalid_slug_rejected(self) -> None:
        pem = "-----BEGIN RSA PRIVATE KEY-----\n" + ("A" * 200) + "\n-----END RSA PRIVATE KEY-----"
        with pytest.raises(ValidationError):
            GitHubAppSetup(
                app_id="12345",
                private_key_pem=pem,
                enterprise_slug="invalid slug!",
            )

    def test_short_private_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GitHubAppSetup(
                app_id="12345",
                private_key_pem="too-short",
                enterprise_slug="my-enterprise",
            )

    def test_interval_out_of_range(self) -> None:
        pem = "-----BEGIN RSA PRIVATE KEY-----\n" + ("A" * 200) + "\n-----END RSA PRIVATE KEY-----"
        with pytest.raises(ValidationError):
            GitHubAppSetup(
                app_id="12345",
                private_key_pem=pem,
                enterprise_slug="my-enterprise",
                sync_interval_days=0,
            )
        with pytest.raises(ValidationError):
            GitHubAppSetup(
                app_id="12345",
                private_key_pem=pem,
                enterprise_slug="my-enterprise",
                sync_interval_days=91,
            )


class TestTLSSetup:
    def test_defaults(self) -> None:
        setup = TLSSetup()
        assert setup.cert_pem == ""
        assert setup.key_pem == ""
        assert setup.generate_self_signed is False

    def test_self_signed_flag(self) -> None:
        setup = TLSSetup(generate_self_signed=True)
        assert setup.generate_self_signed is True


class TestSettingUpdate:
    def test_valid_update(self) -> None:
        update = SettingUpdate(value="new-value", description="A description")
        assert update.value == "new-value"
        assert update.description == "A description"

    def test_empty_value_allowed(self) -> None:
        """min_length=0 means empty strings are OK."""
        update = SettingUpdate(value="")
        assert update.value == ""


class TestSetupStatusResponse:
    def test_setup_required_true(self) -> None:
        resp = SetupStatusResponse(setup_required=True)
        assert resp.setup_required is True

    def test_setup_required_false(self) -> None:
        resp = SetupStatusResponse(setup_required=False, setup_token_hint="")
        assert resp.setup_required is False


class TestInitialAdminsSetup:
    def test_valid_single_admin(self) -> None:
        payload = InitialAdminsSetup(admin_logins=["octocat"])
        assert payload.admin_logins == ["octocat"]

    def test_valid_multiple_admins(self) -> None:
        payload = InitialAdminsSetup(admin_logins=["alice", "bob", "charlie"])
        assert len(payload.admin_logins) == 3

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InitialAdminsSetup(admin_logins=[])

    def test_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InitialAdminsSetup()  # type: ignore[call-arg]
