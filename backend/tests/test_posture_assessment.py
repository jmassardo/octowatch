"""Unit tests for posture assessment detection rules.

Covers:
- run_posture_assessment orchestration
- _evaluate_posture_rule dispatch
- _evaluate_org_posture field checks
- _evaluate_repo_posture field checks
- _evaluate_missing_bp missing branch protection
- _evaluate_bp_posture branch protection field checks
- _write_posture_detection dedup & creation
- _auto_resolve_posture_detections auto-resolution
- _POSTURE_OPS operator correctness
- _enrich_org_settings REST enrichment
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.detection_service import (
    _auto_resolve_posture_detections,
    _evaluate_bp_posture,
    _evaluate_missing_bp,
    _evaluate_org_posture,
    _evaluate_posture_rule,
    _evaluate_repo_posture,
    _write_posture_detection,
    run_posture_assessment,
)

# ── Fake model helpers ────────────────────────────────────────────────────────


class FakeRule:
    """Lightweight stand-in for RuleDefinition."""

    def __init__(
        self,
        *,
        id: int = 1,
        slug: str = "test-rule",
        name: str = "Test Rule",
        description: str = "A test rule",
        logic_type: str = "posture",
        logic_config: dict[str, Any] | None = None,
        default_severity: str = "high",
        default_confidence: str = "high",
        version: int = 1,
        enabled: bool = True,
        status: str = "active",
    ):
        self.id = id
        self.slug = slug
        self.name = name
        self.description = description
        self.logic_type = logic_type
        self.logic_config = logic_config or {}
        self.default_severity = default_severity
        self.default_confidence = default_confidence
        self.version = version
        self.enabled = enabled
        self.status = status


class FakeOrg:
    """Lightweight stand-in for EnterpriseOrg."""

    def __init__(
        self,
        *,
        id: int = 1,
        org_login: str = "my-org",
        two_factor_required: bool | None = None,
        ip_allow_list_enabled: bool | None = None,
        default_repo_permission: str | None = None,
        members_can_fork_private_repos: bool | None = None,
        members_can_create_public_repos: bool | None = None,
    ):
        self.id = id
        self.org_login = org_login
        self.two_factor_required = two_factor_required
        self.ip_allow_list_enabled = ip_allow_list_enabled
        self.default_repo_permission = default_repo_permission
        self.members_can_fork_private_repos = members_can_fork_private_repos
        self.members_can_create_public_repos = members_can_create_public_repos


class FakeRepo:
    """Lightweight stand-in for Repository."""

    def __init__(
        self,
        *,
        id: int = 1,
        org: str = "my-org",
        repo_name: str = "my-repo",
        visibility: str = "private",
        archived: bool = False,
        default_branch: str | None = "main",
    ):
        self.id = id
        self.org = org
        self.repo_name = repo_name
        self.visibility = visibility
        self.archived = archived
        self.default_branch = default_branch


class FakeBP:
    """Lightweight stand-in for RepoBranchProtection."""

    def __init__(
        self,
        *,
        id: int = 1,
        org: str = "my-org",
        repo_name: str = "my-repo",
        branch: str = "main",
        required_reviews: int = 0,
        enforce_admins: bool = False,
    ):
        self.id = id
        self.org = org
        self.repo_name = repo_name
        self.branch = branch
        self.required_reviews = required_reviews
        self.enforce_admins = enforce_admins


class FakeDetection:
    """Lightweight stand-in for Detection."""

    def __init__(
        self,
        *,
        id: int = 1,
        rule_id: int = 1,
        status: str = "open",
        context_data: dict[str, Any] | None = None,
    ):
        self.id = id
        self.rule_id = rule_id
        self.status = status
        self.context_data = context_data or {}


def _mock_scalars(items: list[Any]) -> MagicMock:
    """Build a mock result whose ``.scalars().all()`` returns *items*."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = items
    return mock


def _mock_scalar_one(item: Any | None) -> MagicMock:
    """Build a mock result whose ``.scalar_one_or_none()`` returns *item*."""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = item
    return mock


# ── _POSTURE_OPS tests ───────────────────────────────────────────────────────


class TestPostureOps:
    def test_eq_true(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["eq"](False, False) is True

    def test_eq_false(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["eq"](True, False) is False

    def test_ne_true(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["ne"](True, False) is True

    def test_lt_true(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["lt"](0, 1) is True

    def test_lt_none(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["lt"](None, 1) is False

    def test_lte_equal(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["lte"](1, 1) is True

    def test_gt(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["gt"](2, 1) is True

    def test_gte(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["gte"](1, 1) is True

    def test_in_list(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["in"]("write", ["write", "admin"]) is True

    def test_in_not_found(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["in"]("read", ["write", "admin"]) is False

    def test_in_empty(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["in"]("read", []) is False

    def test_not_in(self) -> None:
        from app.services.detection_service import _POSTURE_OPS

        assert _POSTURE_OPS["not_in"]("read", ["write"]) is True


# ── _evaluate_org_posture tests ──────────────────────────────────────────────


class TestEvaluateOrgPosture:
    @pytest.mark.anyio
    async def test_returns_hit_when_field_matches(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(ip_allow_list_enabled=False)]),
        )
        rule = FakeRule(
            slug="posture-ip-allowlist-disabled",
            logic_config={
                "entity_type": "org",
                "check_type": "field_value",
                "field": "ip_allow_list_enabled",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1
        assert hits[0]["org"] == "my-org"
        assert hits[0]["actual_value"] is False
        assert "dedup_key" in hits[0]

    @pytest.mark.anyio
    async def test_skips_null_fields(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(ip_allow_list_enabled=None)]),
        )
        rule = FakeRule(
            logic_config={
                "field": "ip_allow_list_enabled",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0

    @pytest.mark.anyio
    async def test_no_hit_when_field_doesnt_match(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(two_factor_required=True)]),
        )
        rule = FakeRule(
            logic_config={
                "field": "two_factor_required",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0

    @pytest.mark.anyio
    async def test_in_operator_with_default_repo_permission(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(default_repo_permission="write")]),
        )
        rule = FakeRule(
            logic_config={
                "field": "default_repo_permission",
                "operator": "in",
                "value": ["write", "admin"],
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_unknown_operator_returns_empty(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(two_factor_required=True)]),
        )
        rule = FakeRule(
            logic_config={
                "field": "two_factor_required",
                "operator": "INVALID",
                "value": True,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0

    @pytest.mark.anyio
    async def test_multiple_orgs(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars(
                [
                    FakeOrg(
                        id=1,
                        org_login="org-a",
                        two_factor_required=False,
                    ),
                    FakeOrg(
                        id=2,
                        org_login="org-b",
                        two_factor_required=True,
                    ),
                    FakeOrg(
                        id=3,
                        org_login="org-c",
                        two_factor_required=False,
                    ),
                ]
            ),
        )
        rule = FakeRule(
            slug="posture-2fa",
            logic_config={
                "field": "two_factor_required",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 2
        assert {h["org"] for h in hits} == {"org-a", "org-c"}


# ── _evaluate_repo_posture tests ─────────────────────────────────────────────


class TestEvaluateRepoPosture:
    @pytest.mark.anyio
    async def test_public_repo_detected(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeRepo(visibility="public")]),
        )
        rule = FakeRule(
            slug="posture-public-repo",
            logic_config={
                "field": "visibility",
                "operator": "eq",
                "value": "public",
            },
        )
        hits = await _evaluate_repo_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1
        assert hits[0]["repo"] == "my-org/my-repo"

    @pytest.mark.anyio
    async def test_private_repo_not_detected(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeRepo(visibility="private")]),
        )
        rule = FakeRule(
            logic_config={
                "field": "visibility",
                "operator": "eq",
                "value": "public",
            },
        )
        hits = await _evaluate_repo_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0


# ── _evaluate_missing_bp tests ───────────────────────────────────────────────


class TestEvaluateMissingBP:
    @pytest.mark.anyio
    async def test_unprotected_repo_detected(self) -> None:
        session = AsyncMock()
        # First call: repos, second call: branch protections
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([FakeRepo(default_branch="main")]),
                _mock_scalars([]),  # No protections
            ],
        )
        rule = FakeRule(
            slug="posture-no-bp",
            logic_config={
                "entity_type": "branch_protection",
                "check_type": "missing_protection",
            },
        )
        hits = await _evaluate_missing_bp(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1
        assert hits[0]["field"] == "missing"
        assert hits[0]["actual_value"] is None

    @pytest.mark.anyio
    async def test_protected_repo_not_detected(self) -> None:
        session = AsyncMock()
        repo = FakeRepo(default_branch="main")
        bp = FakeBP(org="my-org", repo_name="my-repo", branch="main")
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([repo]),
                _mock_scalars([bp]),
            ],
        )
        rule = FakeRule(
            slug="posture-no-bp",
            logic_config={
                "entity_type": "branch_protection",
                "check_type": "missing_protection",
            },
        )
        hits = await _evaluate_missing_bp(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0

    @pytest.mark.anyio
    async def test_repo_without_default_branch_skipped(self) -> None:
        session = AsyncMock()
        # default_branch is None — should be excluded by query filter
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([]),  # No repos match filter
                _mock_scalars([]),
            ],
        )
        rule = FakeRule(
            slug="posture-no-bp",
            logic_config={
                "entity_type": "branch_protection",
                "check_type": "missing_protection",
            },
        )
        hits = await _evaluate_missing_bp(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0


# ── _evaluate_bp_posture tests ───────────────────────────────────────────────


class TestEvaluateBPPosture:
    @pytest.mark.anyio
    async def test_no_reviews_required(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeBP(required_reviews=0)]),
        )
        rule = FakeRule(
            slug="posture-no-review",
            logic_config={
                "field": "required_reviews",
                "operator": "lt",
                "value": 1,
            },
        )
        hits = await _evaluate_bp_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_admins_not_enforced(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeBP(enforce_admins=False)]),
        )
        rule = FakeRule(
            slug="posture-admins-not-enforced",
            logic_config={
                "field": "enforce_admins",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_bp_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_admins_enforced_not_hit(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeBP(enforce_admins=True)]),
        )
        rule = FakeRule(
            logic_config={
                "field": "enforce_admins",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_bp_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0


# ── _evaluate_posture_rule dispatch tests ────────────────────────────────────


class TestEvaluatePostureRule:
    @pytest.mark.anyio
    async def test_dispatches_to_org(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(two_factor_required=False)]),
        )
        rule = FakeRule(
            logic_config={
                "entity_type": "org",
                "check_type": "field_value",
                "field": "two_factor_required",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_posture_rule(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_dispatches_to_repo(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeRepo(visibility="public")]),
        )
        rule = FakeRule(
            logic_config={
                "entity_type": "repo",
                "check_type": "field_value",
                "field": "visibility",
                "operator": "eq",
                "value": "public",
            },
        )
        hits = await _evaluate_posture_rule(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_dispatches_missing_bp(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([FakeRepo()]),
                _mock_scalars([]),
            ],
        )
        rule = FakeRule(
            logic_config={
                "entity_type": "branch_protection",
                "check_type": "missing_protection",
            },
        )
        hits = await _evaluate_posture_rule(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_dispatches_bp_field_value(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeBP(required_reviews=0)]),
        )
        rule = FakeRule(
            logic_config={
                "entity_type": "branch_protection",
                "check_type": "field_value",
                "field": "required_reviews",
                "operator": "lt",
                "value": 1,
            },
        )
        hits = await _evaluate_posture_rule(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 1

    @pytest.mark.anyio
    async def test_unknown_entity_returns_empty(self) -> None:
        session = AsyncMock()
        rule = FakeRule(
            logic_config={"entity_type": "unknown_thing"},
        )
        hits = await _evaluate_posture_rule(
            session,
            rule,
            rule.logic_config,
        )
        assert len(hits) == 0


# ── _write_posture_detection tests ───────────────────────────────────────────


class TestWritePostureDetection:
    @pytest.mark.anyio
    async def test_creates_new_detection(self) -> None:
        session = AsyncMock()
        # With check_suppression patched, session.execute is called:
        #   1. dedup check (scalar_one_or_none -> None)
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one(None),  # dedup check
            ],
        )
        session.add = MagicMock()
        session.flush = AsyncMock()

        rule = FakeRule(
            id=42,
            slug="posture-test",
            logic_config={"confidence": 0.9},
        )
        hit = {
            "dedup_key": "posture:posture-test:my-org:",
            "org": "my-org",
            "repo": None,
            "entity_type": "org",
            "field": "two_factor_required",
            "actual_value": False,
            "expected_value": True,
        }

        with patch(
            "app.services.detection_service.check_suppression",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _write_posture_detection(
                session,
                rule,
                hit,
            )

        assert result is True
        session.add.assert_called_once()

    @pytest.mark.anyio
    async def test_dedup_updates_existing(self) -> None:
        session = AsyncMock()
        existing = FakeDetection(
            id=99,
            rule_id=42,
            context_data={
                "dedup_key": "posture:test:org:",
                "field": "old",
            },
        )
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one(existing),  # dedup check
                MagicMock(),  # update execute
            ],
        )

        rule = FakeRule(id=42, logic_config={"confidence": 0.9})
        hit = {
            "dedup_key": "posture:test:org:",
            "org": "org",
            "repo": None,
            "entity_type": "org",
            "field": "f",
            "actual_value": False,
            "expected_value": True,
        }

        with patch(
            "app.services.detection_service.check_suppression",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _write_posture_detection(
                session,
                rule,
                hit,
            )

        assert result is False  # Not a new detection
        # Should have executed an update for the existing detection
        assert session.execute.call_count == 2

    @pytest.mark.anyio
    async def test_suppressed_returns_false(self) -> None:
        session = AsyncMock()
        rule = FakeRule(id=42, logic_config={})
        hit = {
            "dedup_key": "posture:test:org:",
            "org": "org",
            "repo": None,
            "entity_type": "org",
            "field": "f",
            "actual_value": False,
            "expected_value": True,
        }

        fake_suppression = MagicMock()
        with patch(
            "app.services.detection_service.check_suppression",
            new_callable=AsyncMock,
            return_value=fake_suppression,
        ):
            result = await _write_posture_detection(
                session,
                rule,
                hit,
            )

        assert result is False


# ── _auto_resolve_posture_detections tests ───────────────────────────────────


class TestAutoResolvePostureDetections:
    @pytest.mark.anyio
    async def test_resolves_detection_not_in_active_keys(self) -> None:
        session = AsyncMock()
        det = FakeDetection(
            id=1,
            rule_id=10,
            status="open",
            context_data={"dedup_key": "posture:test:org:"},
        )
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([det]),  # query open detections
                MagicMock(),  # update
            ],
        )

        rules = [FakeRule(id=10)]
        active_keys: set[str] = set()  # Empty — nothing active

        await _auto_resolve_posture_detections(
            session,
            rules,
            active_keys,
        )

        # Should have executed two calls: select + update
        assert session.execute.call_count == 2

    @pytest.mark.anyio
    async def test_keeps_detection_in_active_keys(self) -> None:
        session = AsyncMock()
        det = FakeDetection(
            id=1,
            rule_id=10,
            status="open",
            context_data={
                "dedup_key": "posture:test:org:",
            },
        )
        session.execute = AsyncMock(
            return_value=_mock_scalars([det]),
        )

        rules = [FakeRule(id=10)]
        active_keys = {"posture:test:org:"}

        await _auto_resolve_posture_detections(
            session,
            rules,
            active_keys,
        )

        # Only 1 call: the select query. No update needed.
        assert session.execute.call_count == 1

    @pytest.mark.anyio
    async def test_empty_rules_does_nothing(self) -> None:
        session = AsyncMock()
        await _auto_resolve_posture_detections(session, [], set())
        session.execute.assert_not_called()

    @pytest.mark.anyio
    async def test_detection_without_dedup_key_skipped(self) -> None:
        session = AsyncMock()
        det = FakeDetection(
            id=1,
            rule_id=10,
            status="open",
            context_data={},  # No dedup_key
        )
        session.execute = AsyncMock(
            return_value=_mock_scalars([det]),
        )

        rules = [FakeRule(id=10)]
        await _auto_resolve_posture_detections(
            session,
            rules,
            set(),
        )

        # Only the select call — no update since no dedup_key
        assert session.execute.call_count == 1


# ── run_posture_assessment integration tests ─────────────────────────────────


class TestRunPostureAssessment:
    @pytest.mark.anyio
    async def test_returns_zero_when_no_rules(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([]),
        )
        result = await run_posture_assessment(session)
        assert result == 0

    @pytest.mark.anyio
    async def test_processes_rules_and_returns_count(self) -> None:
        rule = FakeRule(
            id=1,
            slug="posture-2fa",
            logic_config={
                "entity_type": "org",
                "check_type": "field_value",
                "field": "two_factor_required",
                "operator": "eq",
                "value": False,
                "confidence": 0.95,
            },
        )
        org = FakeOrg(two_factor_required=False)

        session = AsyncMock()
        # Calls in order:
        # 1. Load posture rules
        # 2. _evaluate_org_posture query orgs
        # 3. check_suppression
        # 4. dedup check
        # 5. flush (after add)
        # 6. auto-resolve query
        session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([rule]),  # Load rules
                _mock_scalars([org]),  # Evaluate org
                _mock_scalars([]),  # check_suppression inner query
                _mock_scalar_one(None),  # dedup check
                MagicMock(),  # flush
                _mock_scalars([]),  # auto-resolve query
            ],
        )
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await run_posture_assessment(session)
        assert result == 1

    @pytest.mark.anyio
    async def test_handles_rule_evaluation_error(self) -> None:
        rule = FakeRule(
            id=1,
            slug="posture-bad",
            logic_config={"entity_type": "org"},
        )

        session = AsyncMock()
        call_count = 0

        async def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalars([rule])  # Load rules
            if call_count == 2:
                raise RuntimeError("DB error")  # Eval fails
            return _mock_scalars([])

        session.execute = AsyncMock(side_effect=side_effect)

        # Should not raise — errors are caught per-rule
        result = await run_posture_assessment(session)
        assert result == 0


# ── Dedup key format tests ───────────────────────────────────────────────────


class TestDedupKeyFormat:
    @pytest.mark.anyio
    async def test_org_dedup_key_format(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeOrg(org_login="acme", ip_allow_list_enabled=False)]),
        )
        rule = FakeRule(
            slug="posture-ip",
            logic_config={
                "field": "ip_allow_list_enabled",
                "operator": "eq",
                "value": False,
            },
        )
        hits = await _evaluate_org_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert hits[0]["dedup_key"] == "posture:posture-ip:acme:"

    @pytest.mark.anyio
    async def test_repo_dedup_key_format(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars(
                [FakeRepo(org="acme", repo_name="web", visibility="public")]
            ),
        )
        rule = FakeRule(
            slug="posture-pub",
            logic_config={
                "field": "visibility",
                "operator": "eq",
                "value": "public",
            },
        )
        hits = await _evaluate_repo_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert hits[0]["dedup_key"] == "posture:posture-pub:acme:web"

    @pytest.mark.anyio
    async def test_bp_dedup_key_format(self) -> None:
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=_mock_scalars([FakeBP(org="acme", repo_name="web", required_reviews=0)]),
        )
        rule = FakeRule(
            slug="posture-rev",
            logic_config={
                "field": "required_reviews",
                "operator": "lt",
                "value": 1,
            },
        )
        hits = await _evaluate_bp_posture(
            session,
            rule,
            rule.logic_config,
        )
        assert hits[0]["dedup_key"] == "posture:posture-rev:acme:web"


# ── Enrichment function tests ───────────────────────────────────────────────


class TestEnrichOrgSettings:
    @pytest.mark.anyio
    async def test_enriches_org_from_rest(self) -> None:
        from app.workers.github_sync_worker import _enrich_org_settings

        org = FakeOrg(id=1, org_login="my-org")
        mock_sf = MagicMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                _mock_scalars([org]),  # First call: select orgs
                MagicMock(),  # update
            ],
        )
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = mock_ctx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "two_factor_requirement_enabled": True,
            "default_repository_permission": "read",
            "members_can_fork_private_repositories": False,
            "members_can_create_public_repositories": False,
        }

        mock_rate = MagicMock()
        mock_rate.acquire = AsyncMock()
        mock_rate.release = MagicMock()
        mock_rate.update_from_headers = MagicMock()
        mock_rate.handle_rate_limit_response = AsyncMock()

        with patch(
            "app.workers.github_sync_worker._github_get",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            mock_token_mgr = MagicMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="token123")
            result = await _enrich_org_settings(
                mock_sf,
                "run-1",
                mock_token_mgr,
                mock_rate,
                org_inst_map={"my-org": 1},
                fallback_installation_id=1,
            )

        assert result == 1

    @pytest.mark.anyio
    async def test_handles_http_error_gracefully(self) -> None:
        from app.workers.github_sync_worker import _enrich_org_settings

        org = FakeOrg(id=1, org_login="my-org")
        mock_sf = MagicMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=_mock_scalars([org]),
        )
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_sf.return_value = mock_ctx

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        mock_rate = MagicMock()
        mock_rate.acquire = AsyncMock()
        mock_rate.release = MagicMock()
        mock_rate.update_from_headers = MagicMock()
        mock_rate.handle_rate_limit_response = AsyncMock()

        with patch(
            "app.workers.github_sync_worker._github_get",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            mock_token_mgr = MagicMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="token123")
            result = await _enrich_org_settings(
                mock_sf,
                "run-1",
                mock_token_mgr,
                mock_rate,
                org_inst_map={"my-org": 1},
                fallback_installation_id=1,
            )

        assert result == 0
