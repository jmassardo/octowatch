"""Unit tests for the IdP service: SCIM filter value sanitization."""

from __future__ import annotations

import pytest

from app.services.idp_service import _sanitize_filter_value


class TestSanitizeFilterValue:
    """Tests for _sanitize_filter_value() to prevent SCIM/OData/query injection."""

    def test_plain_username_unchanged(self):
        assert _sanitize_filter_value("octocat") == "octocat"

    def test_email_address_unchanged(self):
        assert _sanitize_filter_value("user@example.com") == "user@example.com"

    def test_username_with_dash_unchanged(self):
        assert _sanitize_filter_value("my-user") == "my-user"

    def test_username_with_underscore_unchanged(self):
        assert _sanitize_filter_value("my_user") == "my_user"

    def test_username_with_dot_unchanged(self):
        assert _sanitize_filter_value("first.last") == "first.last"

    def test_username_with_plus_unchanged(self):
        assert _sanitize_filter_value("user+tag@example.com") == "user+tag@example.com"

    def test_strips_double_quotes(self):
        assert _sanitize_filter_value('user"inject') == "userinject"

    def test_strips_single_quotes(self):
        assert _sanitize_filter_value("user'inject") == "userinject"

    def test_strips_parentheses(self):
        assert _sanitize_filter_value("user(inject)") == "userinject"

    def test_strips_semicolons(self):
        assert _sanitize_filter_value("user;drop") == "userdrop"

    def test_strips_spaces(self):
        assert _sanitize_filter_value("user name") == "username"

    def test_strips_scim_filter_injection_attempt(self):
        # Attempt to inject: login eq "x" or 1 eq 1 or "
        malicious = 'x" or 1 eq 1 or "'
        result = _sanitize_filter_value(malicious)
        assert '"' not in result
        assert "'" not in result
        assert " " not in result

    def test_strips_odata_filter_injection(self):
        # Attempt to inject OData operators
        malicious = "user' or displayName eq 'admin"
        result = _sanitize_filter_value(malicious)
        assert "'" not in result
        assert " " not in result

    def test_strips_backslashes(self):
        assert _sanitize_filter_value("user\\inject") == "userinject"

    def test_strips_square_brackets(self):
        assert _sanitize_filter_value("user[0]") == "user0"

    def test_strips_asterisk(self):
        assert _sanitize_filter_value("user*") == "user"

    def test_raises_on_empty_result(self):
        with pytest.raises(ValueError, match="contains no valid characters"):
            _sanitize_filter_value("\"'();")

    def test_raises_on_only_spaces(self):
        with pytest.raises(ValueError, match="contains no valid characters"):
            _sanitize_filter_value("   ")

    def test_numeric_username(self):
        assert _sanitize_filter_value("12345") == "12345"

    def test_mixed_valid_invalid(self):
        assert _sanitize_filter_value("user<>name") == "username"

    def test_unicode_characters_stripped(self):
        # Unicode chars outside allowed set should be stripped
        result = _sanitize_filter_value("usérname")
        assert result == "usrname"
