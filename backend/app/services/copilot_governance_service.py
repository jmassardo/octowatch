"""Copilot governance policy evaluation service.

Evaluates defined governance policies against Copilot usage metrics:
- Seat classification: seats assigned to repos outside allowed classifications
- Acceptance threshold: unusually low acceptance rates that may signal issues
- Usage frequency: seats with very low usage that waste licence spend
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.copilot_policy import CopilotPolicy, CopilotPolicyViolation

logger = structlog.get_logger(__name__)


class CopilotGovernanceService:
    """Evaluate Copilot governance policies and record violations."""

    async def list_policies(
        self,
        db: AsyncSession,
        enabled_only: bool = False,
    ) -> list[CopilotPolicy]:
        """Return all policies, optionally filtered to enabled ones."""
        stmt = select(CopilotPolicy).order_by(CopilotPolicy.created_at.desc())
        if enabled_only:
            stmt = stmt.where(CopilotPolicy.enabled.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_policy(self, db: AsyncSession, policy_id: int) -> CopilotPolicy | None:
        """Return a single policy by ID."""
        result = await db.execute(select(CopilotPolicy).where(CopilotPolicy.id == policy_id))
        return result.scalar_one_or_none()

    async def create_policy(
        self,
        db: AsyncSession,
        *,
        name: str,
        description: str | None,
        policy_type: str,
        config: dict[str, Any],
        created_by: str,
    ) -> CopilotPolicy:
        """Create a new governance policy."""
        policy = CopilotPolicy(
            name=name,
            description=description,
            policy_type=policy_type,
            config=config,
            created_by=created_by,
        )
        db.add(policy)
        await db.flush()
        await db.refresh(policy)
        return policy

    async def update_policy(
        self,
        db: AsyncSession,
        policy_id: int,
        *,
        updates: dict[str, Any],
    ) -> CopilotPolicy | None:
        """Update an existing policy."""
        policy = await self.get_policy(db, policy_id)
        if policy is None:
            return None

        for key, value in updates.items():
            if hasattr(policy, key) and key not in ("id", "created_at", "created_by"):
                setattr(policy, key, value)

        await db.flush()
        await db.refresh(policy)
        return policy

    async def delete_policy(self, db: AsyncSession, policy_id: int) -> bool:
        """Delete a policy. Returns True if found and deleted."""
        policy = await self.get_policy(db, policy_id)
        if policy is None:
            return False
        await db.delete(policy)
        await db.flush()
        return True

    async def list_violations(
        self,
        db: AsyncSession,
        policy_id: int | None = None,
        limit: int = 100,
    ) -> list[CopilotPolicyViolation]:
        """List violations, optionally filtered by policy."""
        stmt = (
            select(CopilotPolicyViolation)
            .order_by(CopilotPolicyViolation.created_at.desc())
            .limit(limit)
        )
        if policy_id is not None:
            stmt = stmt.where(CopilotPolicyViolation.policy_id == policy_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def evaluate_policies(
        self,
        db: AsyncSession,
        metrics_data: dict[str, Any],
    ) -> list[CopilotPolicyViolation]:
        """Evaluate all enabled policies against current metrics.

        Parameters
        ----------
        db:
            Database session.
        metrics_data:
            Copilot metrics data dict with keys like ``seats``, ``acceptance_rate``,
            ``usage_summary``, etc.

        Returns
        -------
        list[CopilotPolicyViolation]
            Newly created violations.
        """
        policies = await self.list_policies(db, enabled_only=True)
        new_violations: list[CopilotPolicyViolation] = []

        for policy in policies:
            try:
                violations = self._evaluate_single_policy(policy, metrics_data)
                for v_data in violations:
                    violation = CopilotPolicyViolation(
                        policy_id=policy.id,
                        actor_login=v_data.get("actor_login"),
                        violation_details=v_data,
                    )
                    db.add(violation)
                    new_violations.append(violation)
            except Exception:
                logger.exception(
                    "copilot_governance.evaluate_failed",
                    policy_id=policy.id,
                    policy_name=policy.name,
                )

        if new_violations:
            await db.flush()

        return new_violations

    def _evaluate_single_policy(
        self,
        policy: CopilotPolicy,
        metrics_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluate a single policy. Returns list of violation detail dicts."""
        evaluator = _EVALUATORS.get(policy.policy_type)
        if evaluator is None:
            logger.warning(
                "copilot_governance.unknown_policy_type",
                policy_type=policy.policy_type,
            )
            return []
        result: list[dict[str, Any]] = evaluator(policy.config, metrics_data)
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Policy evaluators
# ──────────────────────────────────────────────────────────────────────────────


def _evaluate_acceptance_threshold(
    config: dict[str, Any],
    metrics_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flag users whose acceptance rate is below the configured threshold."""
    threshold = config.get("min_acceptance_rate", 10.0)
    window_days = config.get("window_days", 30)
    violations: list[dict[str, Any]] = []

    seats = metrics_data.get("seats", [])
    for seat in seats:
        if not isinstance(seat, dict):
            continue
        rate = seat.get("acceptance_rate")
        login = seat.get("login") or seat.get("assignee", {}).get("login")
        if rate is not None and rate < threshold and login:
            violations.append(
                {
                    "actor_login": login,
                    "type": "low_acceptance_rate",
                    "acceptance_rate": rate,
                    "threshold": threshold,
                    "window_days": window_days,
                    "message": (
                        f"User {login} has an acceptance rate of {rate:.1f}% "
                        f"(below {threshold}% threshold)"
                    ),
                }
            )

    return violations


def _evaluate_seat_classification(
    config: dict[str, Any],
    metrics_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flag seat assignments that violate repo classification rules."""
    allowed_classifications = set(config.get("allowed_classifications", []))
    violations: list[dict[str, Any]] = []

    seats = metrics_data.get("seats", [])
    for seat in seats:
        if not isinstance(seat, dict):
            continue
        classification = seat.get("repo_classification", "")
        login = seat.get("login") or seat.get("assignee", {}).get("login")
        if allowed_classifications and classification not in allowed_classifications and login:
            violations.append(
                {
                    "actor_login": login,
                    "type": "seat_classification_violation",
                    "classification": classification,
                    "allowed": list(allowed_classifications),
                    "message": (
                        f"User {login} has Copilot access for '{classification}' "
                        f"classified repos (allowed: {sorted(allowed_classifications)})"
                    ),
                }
            )

    return violations


def _evaluate_usage_frequency(
    config: dict[str, Any],
    metrics_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flag seats with very low usage (wasted licences)."""
    min_suggestions = config.get("min_suggestions_per_day", 1)
    window_days = config.get("window_days", 30)
    violations: list[dict[str, Any]] = []

    seats = metrics_data.get("seats", [])
    for seat in seats:
        if not isinstance(seat, dict):
            continue
        daily_suggestions = seat.get("daily_suggestions", 0)
        login = seat.get("login") or seat.get("assignee", {}).get("login")
        if daily_suggestions < min_suggestions and login:
            violations.append(
                {
                    "actor_login": login,
                    "type": "low_usage_frequency",
                    "daily_suggestions": daily_suggestions,
                    "min_required": min_suggestions,
                    "window_days": window_days,
                    "message": (
                        f"User {login} averages {daily_suggestions:.1f} suggestions/day "
                        f"(below {min_suggestions} minimum)"
                    ),
                }
            )

    return violations


_EVALUATORS: dict[str, Any] = {
    "acceptance_threshold": _evaluate_acceptance_threshold,
    "seat_classification": _evaluate_seat_classification,
    "usage_frequency": _evaluate_usage_frequency,
}
