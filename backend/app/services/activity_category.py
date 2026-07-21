from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Exact action → category overrides (checked first)
_ACTION_OVERRIDES: dict[str, str] = {
    "git.clone": "passive",
    "git.fetch": "passive",
    "repo.access": "passive",
}

# Namespace → category mapping (checked second)
_NAMESPACE_MAP: dict[str, str] = {
    "git": "code",
    "org": "admin",
    "team": "admin",
    "business": "admin",
    "enterprise": "admin",
    "billing": "admin",
    "audit_log": "admin",
    "integration_installation": "admin",
    "oauth_application": "admin",
    "repo": "repo_mgmt",
    "workflows": "ci_cd",
    "copilot": "copilot",
    "secret_scanning": "security",
    "dependabot": "security",
    "code_scanning": "security",
}

# Webhook event type prefix → category (for webhook-sourced events)
_WEBHOOK_PREFIX_MAP: dict[str, str] = {
    "push": "code",
    "pull_request_review_comment": "code_review",
    "pull_request_review": "code_review",
    "pull_request": "code",
    "issues": "issue_mgmt",
    "issue_comment": "issue_mgmt",
    "projects_v2_item": "project_mgmt",
    "project_card": "project_mgmt",
    "discussion_comment": "discussion",
    "discussion": "discussion",
    "gollum": "documentation",
    "workflow_run": "ci_cd",
    "workflow_dispatch": "ci_cd",
    "check_run": "ci_cd",
    "check_suite": "ci_cd",
    "release": "release_mgmt",
    "secret_scanning_alert": "security",
    "dependabot_alert": "security",
    "code_scanning_alert": "security",
    "repository": "repo_mgmt",
}


def derive_activity_category(action: str) -> str:
    """Derive the activity category for a GitHub event action.

    Args:
        action: The event action string, e.g. "git.push", "pull_request.opened",
                "org.update_member", "workflows.completed_workflow_run"

    Returns:
        Activity category string (e.g. "code", "admin", "ci_cd").
        Returns "other" if no mapping matches.
    """
    # 1. Check exact action overrides
    if action in _ACTION_OVERRIDES:
        return _ACTION_OVERRIDES[action]

    # 2. Split into namespace.suffix
    parts = action.split(".", 1)
    namespace = parts[0]

    # 3. Check namespace map (covers audit log events)
    if namespace in _NAMESPACE_MAP:
        return _NAMESPACE_MAP[namespace]

    # 4. Check webhook prefix map (webhook events use event_type.action format)
    if namespace in _WEBHOOK_PREFIX_MAP:
        return _WEBHOOK_PREFIX_MAP[namespace]

    logger.debug("unmapped_activity_action", action=action)
    return "other"
