from __future__ import annotations

import pytest

from app.services.activity_category import derive_activity_category


class TestExactOverrides:
    """Test that exact action overrides resolve to 'passive'."""

    @pytest.mark.parametrize(
        "action",
        [
            "git.clone",
            "git.fetch",
            "repo.access",
        ],
    )
    def test_passive_overrides(self, action: str) -> None:
        assert derive_activity_category(action) == "passive"


class TestNamespaceMapping:
    """Test namespace-based category resolution for audit log events."""

    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            ("git.push", "code"),
            ("git.create_branch", "code"),
            ("org.update_member", "admin"),
            ("org.invite_member", "admin"),
            ("team.add_member", "admin"),
            ("team.remove_repository", "admin"),
            ("business.update", "admin"),
            ("enterprise.remove_member", "admin"),
            ("billing.change_plan", "admin"),
            ("audit_log.export", "admin"),
            ("integration_installation.create", "admin"),
            ("oauth_application.create", "admin"),
            ("repo.create", "repo_mgmt"),
            ("repo.destroy", "repo_mgmt"),
            ("repo.rename", "repo_mgmt"),
            ("workflows.completed_workflow_run", "ci_cd"),
            ("workflows.cancel_workflow_run", "ci_cd"),
            ("copilot.enable", "copilot"),
            ("copilot.cfr_access", "copilot"),
            ("secret_scanning.alert_created", "security"),
            ("dependabot.alert_dismissed", "security"),
            ("code_scanning.upload_sarif", "security"),
        ],
    )
    def test_namespace_categories(self, action: str, expected: str) -> None:
        assert derive_activity_category(action) == expected


class TestWebhookPrefixMapping:
    """Test webhook event type prefix-based category resolution."""

    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            ("push", "code"),
            ("pull_request.opened", "code"),
            ("pull_request.closed", "code"),
            ("pull_request.merged", "code"),
            ("pull_request_review.submitted", "code_review"),
            ("pull_request_review.dismissed", "code_review"),
            ("pull_request_review_comment.created", "code_review"),
            ("pull_request_review_comment.deleted", "code_review"),
            ("issues.opened", "issue_mgmt"),
            ("issues.closed", "issue_mgmt"),
            ("issue_comment.created", "issue_mgmt"),
            ("issue_comment.edited", "issue_mgmt"),
            ("projects_v2_item.created", "project_mgmt"),
            ("projects_v2_item.archived", "project_mgmt"),
            ("project_card.moved", "project_mgmt"),
            ("discussion.created", "discussion"),
            ("discussion.answered", "discussion"),
            ("discussion_comment.created", "discussion"),
            ("gollum.updated", "documentation"),
            ("workflow_run.completed", "ci_cd"),
            ("workflow_run.requested", "ci_cd"),
            ("workflow_dispatch.created", "ci_cd"),
            ("check_run.completed", "ci_cd"),
            ("check_suite.completed", "ci_cd"),
            ("release.published", "release_mgmt"),
            ("release.created", "release_mgmt"),
            ("secret_scanning_alert.created", "security"),
            ("dependabot_alert.created", "security"),
            ("code_scanning_alert.fixed", "security"),
            ("repository.created", "repo_mgmt"),
            ("repository.deleted", "repo_mgmt"),
        ],
    )
    def test_webhook_categories(self, action: str, expected: str) -> None:
        assert derive_activity_category(action) == expected


class TestUnknownActions:
    """Test that unknown actions return 'other'."""

    @pytest.mark.parametrize(
        "action",
        [
            "unknown_event",
            "custom.action",
            "marketplace.purchase",
            "something_completely_new.fired",
        ],
    )
    def test_unknown_returns_other(self, action: str) -> None:
        assert derive_activity_category(action) == "other"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self) -> None:
        assert derive_activity_category("") == "other"

    def test_action_with_multiple_dots(self) -> None:
        # "org.update.member.role" should split on first dot only → namespace "org"
        assert derive_activity_category("org.update.member.role") == "admin"

    def test_action_no_dot(self) -> None:
        # "push" has no dot, namespace is "push" itself → matches webhook map
        assert derive_activity_category("push") == "code"

    def test_override_takes_precedence_over_namespace(self) -> None:
        # "git.clone" should be "passive", not "code" (git namespace)
        assert derive_activity_category("git.clone") == "passive"
        # "git.fetch" should be "passive", not "code" (git namespace)
        assert derive_activity_category("git.fetch") == "passive"
        # "repo.access" should be "passive", not "repo_mgmt" (repo namespace)
        assert derive_activity_category("repo.access") == "passive"

    def test_all_categories_reachable(self) -> None:
        """Verify that every expected category is reachable via at least one action."""
        expected_categories = {
            "code",
            "code_review",
            "issue_mgmt",
            "project_mgmt",
            "discussion",
            "documentation",
            "admin",
            "repo_mgmt",
            "ci_cd",
            "copilot",
            "security",
            "release_mgmt",
            "passive",
        }
        test_actions = {
            "code": "git.push",
            "code_review": "pull_request_review.submitted",
            "issue_mgmt": "issues.opened",
            "project_mgmt": "projects_v2_item.created",
            "discussion": "discussion.created",
            "documentation": "gollum.updated",
            "admin": "org.update_member",
            "repo_mgmt": "repo.create",
            "ci_cd": "workflows.completed_workflow_run",
            "copilot": "copilot.enable",
            "security": "secret_scanning.alert_created",
            "release_mgmt": "release.published",
            "passive": "git.clone",
        }
        for category in expected_categories:
            action = test_actions[category]
            assert derive_activity_category(action) == category
