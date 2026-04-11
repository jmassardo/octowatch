"""GDPR right-to-erasure service.

Provides ``erase_user()`` which anonymises or deletes all data associated
with a given GitHub login across every relevant table, then records the
erasure in the application audit trail.

Anonymisation strategy:
- Replace actor identifiers with ``REDACTED-{sha256(login)[:8]}`` so that
  referential consistency is preserved without revealing the identity.
- Delete PII-heavy records (IdP enrichments, role assignments) outright.
- Keep events/detections for audit integrity but strip actor identity.
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_service import log_action

logger = structlog.get_logger(__name__)


def _redacted_token(github_login: str) -> str:
    """Deterministic pseudonym: ``REDACTED-<first-8-hex-of-sha256>``."""
    digest = hashlib.sha256(github_login.encode("utf-8")).hexdigest()
    return f"REDACTED-{digest[:8]}"


# Tables and their actor columns.
# ``mode`` is either "anonymize" (replace login with pseudonym) or "delete".
_ERASURE_TARGETS: list[dict[str, str]] = [
    {"table": "events", "column": "actor", "mode": "anonymize"},
    {"table": "detections", "column": "actor", "mode": "anonymize"},
    {"table": "audit_trail", "column": "user_login", "mode": "anonymize"},
    {"table": "behavioral_baselines", "column": "scope_key", "mode": "anonymize"},
    {"table": "idp_actor_enrichments", "column": "github_login", "mode": "delete"},
    {"table": "user_role_assignments", "column": "github_login", "mode": "delete"},
    {"table": "external_collaborators", "column": "github_login", "mode": "delete"},
]


async def erase_user(
    db: AsyncSession,
    github_login: str,
    *,
    authorized_by: str,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Erase/anonymise all data for *github_login*.

    Returns a summary dict with per-table affected row counts.
    """
    if not github_login:
        raise ValueError("github_login must not be empty")

    pseudonym = _redacted_token(github_login)
    summary: dict[str, int] = {}

    for target in _ERASURE_TARGETS:
        table = target["table"]
        column = target["column"]
        mode = target["mode"]

        try:
            if mode == "anonymize":
                result = await db.execute(
                    text(
                        f"UPDATE {table} SET {column} = :pseudonym "  # noqa: S608
                        f"WHERE {column} = :login"
                    ),
                    {"pseudonym": pseudonym, "login": github_login},
                )
            else:  # delete
                result = await db.execute(
                    text(
                        f"DELETE FROM {table} WHERE {column} = :login"  # noqa: S608
                    ),
                    {"login": github_login},
                )
            affected = int(getattr(result, "rowcount", 0) or 0)
            summary[table] = affected
        except Exception:
            logger.exception("gdpr.table_error", table=table, login=github_login)
            summary[table] = -1

    # Write a GDPR-specific audit trail entry
    await log_action(
        db,
        user_login=authorized_by,
        ip_address=ip_address,
        action_type="gdpr_erasure",
        resource_type="user",
        resource_id=github_login,
        parameters={
            "pseudonym": pseudonym,
            "affected_tables": summary,
        },
        outcome="success",
    )

    await db.commit()

    logger.info(
        "gdpr.erasure_complete",
        target_login=github_login,
        authorized_by=authorized_by,
        summary=summary,
    )

    return {
        "github_login": github_login,
        "pseudonym": pseudonym,
        "affected_tables": summary,
    }
