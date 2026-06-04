"""Rename org posture rules to describe desired secure state.

Rules now read as the desired state — pass means compliant, fail means not.
E.g. "2FA Required" passes when 2FA is enabled, fails when it's not.

Revision ID: 0063
Revises: 0062
"""

from sqlalchemy import text

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

# (old_slug, new_name, new_description)
_RENAMES = [
    (
        "posture-ip-allowlist-disabled",
        "IP Allow List Enabled",
        "Organization has IP allow list enabled to restrict access",
    ),
    (
        "posture-2fa-not-required",
        "2FA Required",
        "Organization requires two-factor authentication for all members",
    ),
    (
        "posture-default-repo-permission-write",
        "Default Repo Permission Read Only",
        "Organization grants read-only permission by default",
    ),
    (
        "posture-private-fork-allowed",
        "Private Fork Disabled",
        "Organization restricts forking of private repositories",
    ),
    (
        "posture-public-repo-creation-allowed",
        "Public Repo Creation Disabled",
        "Organization restricts members from creating public repositories",
    ),
    (
        "posture-no-branch-protection",
        "Branch Protection Enabled",
        "Non-archived repository default branch has branch protection",
    ),
    (
        "posture-branch-no-review-required",
        "Branch Protection Review Required",
        "Branch protection requires at least one approving review",
    ),
    (
        "posture-branch-admins-not-enforced",
        "Branch Protection Enforced on Admins",
        "Branch protection rules are enforced on administrators",
    ),
    (
        "posture-public-repo-in-enterprise",
        "Repository Visibility Private",
        "Enterprise repositories are not publicly accessible",
    ),
]


def upgrade() -> None:
    for slug, new_name, new_desc in _RENAMES:
        op.execute(
            text(
                "UPDATE rule_definitions SET name = :name, description = :desc WHERE slug = :slug"
            ).bindparams(name=new_name, desc=new_desc, slug=slug)
        )


def downgrade() -> None:
    # Restore original names
    _ORIGINALS = [
        (
            "posture-ip-allowlist-disabled",
            "IP Allow List Disabled",
            "Organisation does not have IP allow list enabled",
        ),
        (
            "posture-2fa-not-required",
            "2FA Not Required",
            "Organisation does not require two-factor authentication",
        ),
        (
            "posture-default-repo-permission-write",
            "Default Repo Permission Write or Admin",
            "Organisation grants write or admin permission by default",
        ),
        (
            "posture-private-fork-allowed",
            "Private Fork Allowed",
            "Organisation allows forking private repositories",
        ),
        (
            "posture-public-repo-creation-allowed",
            "Public Repo Creation Allowed",
            "Organisation allows creating public repositories",
        ),
        (
            "posture-no-branch-protection",
            "No Branch Protection on Default Branch",
            "Non-archived repo default branch has no branch protection",
        ),
        (
            "posture-branch-no-review-required",
            "Branch Protection No Review Required",
            "Branch protection requires zero approving reviews",
        ),
        (
            "posture-branch-admins-not-enforced",
            "Branch Protection Admins Not Enforced",
            "Branch protection does not enforce rules on admins",
        ),
        (
            "posture-public-repo-in-enterprise",
            "Public Repository in Enterprise",
            "Enterprise organisation contains a public repository",
        ),
    ]
    for slug, old_name, old_desc in _ORIGINALS:
        op.execute(
            text(
                "UPDATE rule_definitions SET name = :name, description = :desc WHERE slug = :slug"
            ).bindparams(name=old_name, desc=old_desc, slug=slug)
        )
