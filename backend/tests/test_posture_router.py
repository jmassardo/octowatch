"""Unit tests for the posture router (/api/v1/posture).

Covers:
- Score computation via _compute_score
- Rule classification via _classify_rules
- Check building helpers (_check_pass, _check_from_detection)
- Repo posture building via _build_repo_posture
- Org posture building via _build_org_posture
- Open detection loading via _load_open_detections
- Enterprise/org/repo level endpoint responses
- Scope enforcement (RBAC scoped orgs)
- 404 handling for missing org / repo
- Breadcrumb construction at each level
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.routers.posture import (
    _build_org_posture,
    _build_repo_posture,
    _check_from_detection,
    _check_pass,
    _classify_rules,
    _compute_score,
)
from app.schemas.posture import PostureCheckResult

# ── Fake model helpers ────────────────────────────────────────────────────────


class FakeRule:
    """Lightweight stand-in for RuleDefinition."""

    def __init__(
        self,
        *,
        id: int = 1,
        name: str = "Test Rule",
        slug: str = "test-rule",
        description: str = "A test rule",
        category: str = "access_control",
        default_severity: str = "high",
        default_confidence: str = "high",
        logic_type: str = "posture",
        logic_config: dict[str, Any] | None = None,
        enabled: bool = True,
        version: int = 1,
        status: str = "active",
    ):
        self.id = id
        self.name = name
        self.slug = slug
        self.description = description
        self.category = category
        self.default_severity = default_severity
        self.default_confidence = default_confidence
        self.logic_type = logic_type
        self.logic_config = logic_config or {}
        self.enabled = enabled
        self.version = version
        self.status = status


class FakeDetection:
    """Lightweight stand-in for Detection."""

    def __init__(
        self,
        *,
        id: int = 100,
        rule_id: int = 1,
        rule_version: int = 1,
        severity: str = "high",
        status: str = "open",
        title: str = "Detection title",
        description: str = "Detection desc",
        org: str | None = "my-org",
        repo: str | None = None,
        context_data: dict[str, Any] | None = None,
        triggered_at: datetime | None = None,
    ):
        self.id = id
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.severity = severity
        self.status = status
        self.title = title
        self.description = description
        self.org = org
        self.repo = repo
        self.context_data = context_data or {}
        self.triggered_at = triggered_at or datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)


class FakeOrg:
    """Lightweight stand-in for EnterpriseOrg."""

    def __init__(
        self,
        *,
        id: int = 1,
        org_login: str = "my-org",
        two_factor_required: bool | None = True,
        default_repo_permission: str | None = "read",
        members_can_fork_private_repos: bool | None = False,
        members_can_create_public_repos: bool | None = False,
        ip_allow_list_enabled: bool | None = True,
    ):
        self.id = id
        self.org_login = org_login
        self.two_factor_required = two_factor_required
        self.default_repo_permission = default_repo_permission
        self.members_can_fork_private_repos = members_can_fork_private_repos
        self.members_can_create_public_repos = members_can_create_public_repos
        self.ip_allow_list_enabled = ip_allow_list_enabled


class FakeRepo:
    """Lightweight stand-in for Repository."""

    def __init__(
        self,
        *,
        id: int = 10,
        org: str = "my-org",
        repo_name: str = "my-repo",
        visibility: str = "private",
        default_branch: str | None = "main",
        archived: bool = False,
        fork: bool = False,
        pushed_at: datetime | None = None,
    ):
        self.id = id
        self.org = org
        self.repo_name = repo_name
        self.visibility = visibility
        self.default_branch = default_branch
        self.archived = archived
        self.fork = fork
        self.pushed_at = pushed_at


# ── _compute_score ────────────────────────────────────────────────────────────


class TestComputeScore:
    """Tests for the score computation function."""

    def test_empty_checks_returns_100(self) -> None:
        assert _compute_score([]) == 100.0

    def test_all_passing_returns_100(self) -> None:
        checks = [
            PostureCheckResult(
                rule_id=1,
                rule_name="r1",
                category="access_control",
                severity="critical",
                status="pass",
                title="t1",
                description="d1",
            ),
            PostureCheckResult(
                rule_id=2,
                rule_name="r2",
                category="access_control",
                severity="high",
                status="pass",
                title="t2",
                description="d2",
            ),
        ]
        assert _compute_score(checks) == 100.0

    def test_all_failing_returns_0(self) -> None:
        checks = [
            PostureCheckResult(
                rule_id=1,
                rule_name="r1",
                category="access_control",
                severity="critical",
                status="open",
                title="t1",
                description="d1",
            ),
        ]
        assert _compute_score(checks) == 0.0

    def test_mixed_pass_fail_uses_severity_weights(self) -> None:
        checks = [
            PostureCheckResult(
                rule_id=1,
                rule_name="r1",
                category="access_control",
                severity="critical",
                status="pass",
                title="t1",
                description="d1",
            ),
            PostureCheckResult(
                rule_id=2,
                rule_name="r2",
                category="access_control",
                severity="low",
                status="open",
                title="t2",
                description="d2",
            ),
        ]
        # critical=10 passing, low=2 failing → 10/12 × 100 = 83.3
        assert _compute_score(checks) == 83.3

    def test_info_severity_weight(self) -> None:
        checks = [
            PostureCheckResult(
                rule_id=1,
                rule_name="r1",
                category="access_control",
                severity="info",
                status="open",
                title="t1",
                description="d1",
            ),
        ]
        # info=1 failing → 0/1 × 100 = 0.0
        assert _compute_score(checks) == 0.0

    def test_medium_weight(self) -> None:
        checks = [
            PostureCheckResult(
                rule_id=1,
                rule_name="r1",
                category="access_control",
                severity="medium",
                status="pass",
                title="t1",
                description="d1",
            ),
            PostureCheckResult(
                rule_id=2,
                rule_name="r2",
                category="access_control",
                severity="medium",
                status="open",
                title="t2",
                description="d2",
            ),
        ]
        # medium=4 each, 4/8 × 100 = 50.0
        assert _compute_score(checks) == 50.0


# ── _classify_rules ──────────────────────────────────────────────────────────


class TestClassifyRules:
    """Tests for splitting posture rules into org-level and repo-level."""

    def test_repo_entity_classified_as_repo_rule(self) -> None:
        rule = FakeRule(id=1, logic_config={"entity": "repo"})
        org_rules, repo_rules = _classify_rules([rule])
        assert len(org_rules) == 0
        assert len(repo_rules) == 1
        assert repo_rules[0].id == 1

    def test_repository_entity_classified_as_repo_rule(self) -> None:
        rule = FakeRule(id=1, logic_config={"entity": "repository"})
        org_rules, repo_rules = _classify_rules([rule])
        assert len(repo_rules) == 1

    def test_org_entity_classified_as_org_rule(self) -> None:
        rule = FakeRule(id=1, logic_config={"entity": "org"})
        org_rules, repo_rules = _classify_rules([rule])
        assert len(org_rules) == 1
        assert len(repo_rules) == 0

    def test_no_entity_defaults_to_org(self) -> None:
        rule = FakeRule(id=1, logic_config={})
        org_rules, repo_rules = _classify_rules([rule])
        assert len(org_rules) == 1

    def test_empty_list_returns_empty(self) -> None:
        org_rules, repo_rules = _classify_rules([])
        assert org_rules == []
        assert repo_rules == []

    def test_mixed_rules_correctly_classified(self) -> None:
        rules = [
            FakeRule(id=1, logic_config={"entity": "org"}),
            FakeRule(id=2, logic_config={"entity": "repo"}),
            FakeRule(id=3, logic_config={"entity": "repository"}),
            FakeRule(id=4, logic_config={}),
        ]
        org_rules, repo_rules = _classify_rules(rules)
        assert len(org_rules) == 2  # id=1 (org), id=4 (default)
        assert len(repo_rules) == 2  # id=2 (repo), id=3 (repository)

    def test_no_entity_inferred_repo_from_detections(self) -> None:
        """Rule with no entity but repo-level detections → repo rule."""
        rule = FakeRule(id=58, logic_config={})
        det = FakeDetection(id=100, rule_id=58, org="my-org", repo="my-repo")
        org_rules, repo_rules = _classify_rules([rule], [det])
        assert len(org_rules) == 0
        assert len(repo_rules) == 1
        assert repo_rules[0].id == 58

    def test_no_entity_stays_org_without_repo_detections(self) -> None:
        """Rule with no entity and org-level detections → org rule."""
        rule = FakeRule(id=54, logic_config={})
        det = FakeDetection(id=100, rule_id=54, org="my-org", repo=None)
        org_rules, repo_rules = _classify_rules([rule], [det])
        assert len(org_rules) == 1
        assert len(repo_rules) == 0

    def test_entity_takes_precedence_over_detections(self) -> None:
        """Explicit entity config is used even with conflicting detections."""
        rule = FakeRule(id=1, logic_config={"entity": "org"})
        det = FakeDetection(id=100, rule_id=1, org="my-org", repo="some-repo")
        org_rules, repo_rules = _classify_rules([rule], [det])
        assert len(org_rules) == 1
        assert len(repo_rules) == 0


# ── _check_pass / _check_from_detection ──────────────────────────────────────


class TestCheckHelpers:
    """Tests for check construction helpers."""

    def test_check_pass_creates_passing_check(self) -> None:
        rule = FakeRule(
            id=5, name="2FA Rule", category="access_control", default_severity="critical"
        )
        check = _check_pass(rule)
        assert check.rule_id == 5
        assert check.rule_name == "2FA Rule"
        assert check.category == "access_control"
        assert check.severity == "critical"
        assert check.status == "pass"
        assert check.detection_id is None
        assert check.triggered_at is None

    def test_check_pass_uses_rule_description(self) -> None:
        rule = FakeRule(description="Check 2FA is enabled")
        check = _check_pass(rule)
        assert check.description == "Check 2FA is enabled"

    def test_check_pass_empty_description(self) -> None:
        rule = FakeRule(description="")
        check = _check_pass(rule)
        assert check.description == ""

    def test_check_from_detection_uses_detection_fields(self) -> None:
        rule = FakeRule(id=5, name="2FA Rule", category="access_control")
        det = FakeDetection(
            id=200,
            severity="critical",
            status="open",
            title="2FA not required",
            description="Organization does not enforce 2FA",
        )
        check = _check_from_detection(rule, det)
        assert check.rule_id == 5
        assert check.severity == "critical"
        assert check.status == "open"
        assert check.title == "2FA not required"
        assert check.detection_id == 200
        assert check.triggered_at is not None

    def test_check_from_detection_null_description(self) -> None:
        rule = FakeRule()
        det = FakeDetection(description="")
        check = _check_from_detection(rule, det)
        assert check.description == ""


# ── _build_repo_posture ──────────────────────────────────────────────────────


class TestBuildRepoPosture:
    """Tests for building repo-level posture."""

    def test_repo_with_no_rules_scores_100(self) -> None:
        repo = FakeRepo(org="my-org", repo_name="my-repo")
        result = _build_repo_posture(repo, [], [], [])
        assert result.repo_name == "my-repo"
        assert result.org == "my-org"
        assert result.score == 100.0
        assert result.checks == []
        assert result.detection_count == 0

    def test_repo_all_rules_passing(self) -> None:
        repo = FakeRepo(org="my-org", repo_name="my-repo")
        rules = [
            FakeRule(id=1, name="BP Required", logic_config={"entity": "repo"}),
            FakeRule(id=2, name="No public", logic_config={"entity": "repo"}),
        ]
        result = _build_repo_posture(repo, rules, [], [])
        assert result.score == 100.0
        assert len(result.checks) == 2
        assert all(c.status == "pass" for c in result.checks)

    def test_repo_with_failing_posture_rule(self) -> None:
        repo = FakeRepo(org="my-org", repo_name="my-repo")
        rules = [FakeRule(id=1, name="BP Required", default_severity="critical")]
        dets = [
            FakeDetection(
                id=100,
                rule_id=1,
                severity="critical",
                status="open",
                org="my-org",
                repo="my-repo",
            )
        ]
        result = _build_repo_posture(repo, rules, [], dets)
        assert result.score == 0.0
        assert len(result.checks) == 1
        assert result.checks[0].status == "open"

    def test_repo_with_event_detections(self) -> None:
        repo = FakeRepo(org="my-org", repo_name="my-repo")
        event_rule = FakeRule(id=10, logic_type="pattern", name="Suspicious push")
        dets = [
            FakeDetection(
                id=200,
                rule_id=10,
                severity="high",
                status="open",
                org="my-org",
                repo="my-repo",
            )
        ]
        result = _build_repo_posture(repo, [], [event_rule], dets)
        assert result.detection_count == 1
        assert len(result.checks) == 1
        assert result.checks[0].rule_name == "Suspicious push"

    def test_repo_metadata_fields(self) -> None:
        repo = FakeRepo(
            org="my-org",
            repo_name="my-repo",
            visibility="public",
            default_branch="develop",
            archived=True,
            fork=True,
            pushed_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        result = _build_repo_posture(repo, [], [], [])
        assert result.visibility == "public"
        assert result.default_branch == "develop"
        assert result.archived is True
        assert result.fork is True
        assert result.pushed_at == datetime(2024, 6, 1, tzinfo=UTC)

    def test_repo_detections_filtered_to_correct_repo(self) -> None:
        repo = FakeRepo(org="my-org", repo_name="target-repo")
        rule = FakeRule(id=1, name="Rule1", default_severity="high")
        dets = [
            FakeDetection(id=100, rule_id=1, org="my-org", repo="other-repo"),
            FakeDetection(id=101, rule_id=1, org="my-org", repo="target-repo"),
        ]
        result = _build_repo_posture(repo, [rule], [], dets)
        assert result.checks[0].status == "open"
        assert result.checks[0].detection_id == 101


# ── _build_org_posture ───────────────────────────────────────────────────────


class TestBuildOrgPosture:
    """Tests for building org-level posture."""

    def test_org_with_no_rules_or_repos(self) -> None:
        org = FakeOrg(org_login="my-org")
        result = _build_org_posture(org, [], [], [], [], [])
        assert result.org_login == "my-org"
        assert result.score == 100.0
        assert result.checks == []
        assert result.repos is None
        assert result.repo_summary is not None
        assert result.repo_summary.total == 0

    def test_org_score_weighted_40_60(self) -> None:
        """Org score = 40% org checks + 60% repo avg."""
        org = FakeOrg(org_login="my-org")
        # Org rule passing → org check score = 100
        org_rule = FakeRule(id=1, name="2FA", default_severity="critical")
        repo = FakeRepo(org="my-org", repo_name="repo1")
        # Repo rule failing → repo score = 0
        repo_rule = FakeRule(
            id=2, name="BP", default_severity="critical", logic_config={"entity": "repo"}
        )
        dets = [FakeDetection(id=100, rule_id=2, org="my-org", repo="repo1")]

        result = _build_org_posture(org, [org_rule], [repo_rule], [], [repo], dets)
        # org check score = 100, repo score = 0 → 100*0.4 + 0*0.6 = 40
        assert result.score == 40.0

    def test_org_includes_repos_when_requested(self) -> None:
        org = FakeOrg(org_login="my-org")
        repo = FakeRepo(org="my-org", repo_name="repo1")
        result = _build_org_posture(org, [], [], [], [repo], [], include_repos=True)
        assert result.repos is not None
        assert len(result.repos) == 1
        assert result.repos[0].repo_name == "repo1"

    def test_org_excludes_repos_by_default(self) -> None:
        org = FakeOrg(org_login="my-org")
        repo = FakeRepo(org="my-org", repo_name="repo1")
        result = _build_org_posture(org, [], [], [], [repo], [])
        assert result.repos is None

    def test_org_metadata_fields(self) -> None:
        org = FakeOrg(
            org_login="my-org",
            two_factor_required=True,
            default_repo_permission="read",
            members_can_fork_private_repos=False,
            members_can_create_public_repos=True,
            ip_allow_list_enabled=True,
        )
        result = _build_org_posture(org, [], [], [], [], [])
        assert result.two_factor_required is True
        assert result.default_repo_permission == "read"
        assert result.members_can_fork_private_repos is False
        assert result.members_can_create_public_repos is True
        assert result.ip_allow_list_enabled is True

    def test_repo_summary_counts(self) -> None:
        org = FakeOrg(org_login="my-org")
        repos = [
            FakeRepo(org="my-org", repo_name="good-repo"),
            FakeRepo(org="my-org", repo_name="warn-repo"),
            FakeRepo(org="my-org", repo_name="bad-repo"),
        ]
        # bad-repo has a critical failing rule → score 0
        repo_rule = FakeRule(id=1, default_severity="critical", logic_config={"entity": "repo"})
        dets = [FakeDetection(id=100, rule_id=1, org="my-org", repo="bad-repo")]

        result = _build_org_posture(org, [], [repo_rule], [], repos, dets)
        assert result.repo_summary is not None
        assert result.repo_summary.total == 3
        # good-repo and warn-repo pass all checks (score 100) → passing
        assert result.repo_summary.passing == 2
        # bad-repo fails (score 0) → failing
        assert result.repo_summary.failing == 1

    def test_org_filters_repos_to_its_own(self) -> None:
        org = FakeOrg(org_login="my-org")
        repos = [
            FakeRepo(org="my-org", repo_name="mine"),
            FakeRepo(org="other-org", repo_name="theirs"),
        ]
        result = _build_org_posture(org, [], [], [], repos, [], include_repos=True)
        assert result.repos is not None
        assert len(result.repos) == 1
        assert result.repos[0].repo_name == "mine"

    def test_org_event_detection_count(self) -> None:
        org = FakeOrg(org_login="my-org")
        event_rule = FakeRule(id=10, logic_type="pattern", name="Suspicious")
        dets = [
            FakeDetection(id=200, rule_id=10, org="my-org", repo=None),
        ]
        result = _build_org_posture(org, [], [], [event_rule], [], dets)
        assert result.detection_count == 1

    def test_org_event_detection_with_repo_not_counted_as_org_level(self) -> None:
        org = FakeOrg(org_login="my-org")
        event_rule = FakeRule(id=10, logic_type="pattern", name="Suspicious")
        dets = [
            FakeDetection(id=200, rule_id=10, org="my-org", repo="some-repo"),
        ]
        result = _build_org_posture(org, [], [], [event_rule], [], dets)
        # Repo-specific event detection should not count as org-level detection
        assert result.detection_count == 0


# ── Schema validation ────────────────────────────────────────────────────────


class TestPostureSchemas:
    """Tests for Pydantic schema construction and defaults."""

    def test_posture_check_result_defaults(self) -> None:
        check = PostureCheckResult(
            rule_id=1,
            rule_name="test",
            category="access_control",
            severity="high",
            status="pass",
            title="Test",
            description="desc",
        )
        assert check.detection_id is None
        assert check.context_data == {}
        assert check.triggered_at is None

    def test_posture_check_result_with_all_fields(self) -> None:
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        check = PostureCheckResult(
            rule_id=1,
            rule_name="test",
            category="posture_degradation",
            severity="critical",
            status="open",
            title="Test",
            description="desc",
            detection_id=100,
            context_data={"key": "val"},
            triggered_at=ts,
        )
        assert check.detection_id == 100
        assert check.context_data == {"key": "val"}
        assert check.triggered_at == ts

    def test_repo_posture_defaults(self) -> None:
        from app.schemas.posture import RepoPosture

        rp = RepoPosture(
            repo_name="r",
            org="o",
            score=100.0,
            checks=[],
        )
        assert rp.visibility is None
        assert rp.archived is False
        assert rp.fork is False
        assert rp.language is None
        assert rp.detection_count == 0

    def test_org_posture_defaults(self) -> None:
        from app.schemas.posture import OrgPosture

        op = OrgPosture(
            org_login="o",
            score=100.0,
            checks=[],
        )
        assert op.repos is None
        assert op.repo_summary is None
        assert op.detection_count == 0
        assert op.two_factor_required is None

    def test_breadcrumb_item_defaults(self) -> None:
        from app.schemas.posture import BreadcrumbItem

        item = BreadcrumbItem(label="Posture")
        assert item.href is None

    def test_posture_response_defaults(self) -> None:
        from app.schemas.posture import BreadcrumbItem, PostureResponse

        resp = PostureResponse(
            level="enterprise",
            score=100.0,
            breadcrumb=[BreadcrumbItem(label="Posture")],
        )
        assert resp.orgs is None
        assert resp.org is None
        assert resp.repo is None
        assert resp.last_sync_at is None
