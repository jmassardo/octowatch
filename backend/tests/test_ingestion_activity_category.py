"""Tests for activity_category integration into the ingestion pipeline."""

from __future__ import annotations

from app.routers.ingest_webhook import _normalize_webhook_event
from app.services.activity_category import derive_activity_category

# ── derive_activity_category unit tests ──────────────────────────────────────


class TestDeriveActivityCategory:
    """Verify derive_activity_category returns correct categories."""

    def test_exact_override_takes_priority(self) -> None:
        assert derive_activity_category("git.clone") == "passive"
        assert derive_activity_category("git.fetch") == "passive"

    def test_namespace_map(self) -> None:
        assert derive_activity_category("org.update_member") == "admin"
        assert derive_activity_category("repo.create") == "repo_mgmt"
        assert derive_activity_category("workflows.completed_workflow_run") == "ci_cd"
        assert derive_activity_category("secret_scanning.alert_created") == "security"
        assert derive_activity_category("copilot.seat_assigned") == "copilot"

    def test_webhook_prefix_map(self) -> None:
        assert derive_activity_category("push.push") == "code"
        assert derive_activity_category("pull_request.opened") == "code"
        assert derive_activity_category("pull_request_review.submitted") == "code_review"
        assert derive_activity_category("issues.opened") == "issue_mgmt"
        assert derive_activity_category("workflow_run.completed") == "ci_cd"
        assert derive_activity_category("release.published") == "release_mgmt"

    def test_unknown_action_returns_other(self) -> None:
        assert derive_activity_category("unknown_namespace.something") == "other"
        assert derive_activity_category("") == "other"

    def test_single_segment_action(self) -> None:
        # An action with no dot still checks the namespace map
        assert derive_activity_category("push") == "code"


# ── _normalize_event (bulk ingestion) tests ──────────────────────────────────


class TestBulkNormalizeEvent:
    """Verify _normalize_event in AbstractIngestWorker includes activity_category."""

    def test_normalize_event_includes_activity_category(self) -> None:
        """The normalized dict should contain activity_category derived from action."""
        from app.workers.ingestion.base import AbstractIngestWorker

        # Create a concrete subclass for testing
        class ConcreteWorker(AbstractIngestWorker):
            ingestion_source = "test"

            async def run(self) -> None:
                pass

        worker = ConcreteWorker.__new__(ConcreteWorker)
        worker.ingestion_source = "test"

        raw = {
            "action": "org.invite_member",
            "actor": "alice",
            "actor_id": 123,
            "@timestamp": "2024-01-15T10:00:00Z",
            "org": "acme",
        }

        result = worker._normalize_event(raw, dedup_hash="abc123", source_file_path="test.json")

        assert result is not None
        assert result["activity_category"] == "admin"
        assert result["action"] == "org.invite_member"

    def test_normalize_event_security_action(self) -> None:
        """Security namespace actions should map to 'security' category."""
        from app.workers.ingestion.base import AbstractIngestWorker

        class ConcreteWorker(AbstractIngestWorker):
            ingestion_source = "test"

            async def run(self) -> None:
                pass

        worker = ConcreteWorker.__new__(ConcreteWorker)
        worker.ingestion_source = "test"

        raw = {
            "action": "secret_scanning.alert_dismissed",
            "actor": "bob",
            "@timestamp": "2024-01-15T10:00:00Z",
        }

        result = worker._normalize_event(raw, dedup_hash="def456", source_file_path="scan.json")

        assert result is not None
        assert result["activity_category"] == "security"


# ── Webhook normalizer tests ─────────────────────────────────────────────────


class TestWebhookNormalizeEvent:
    """Verify _normalize_webhook_event includes activity_category and bot detection."""

    def test_includes_activity_category(self) -> None:
        payload = {
            "action": "opened",
            "sender": {"login": "alice", "id": 42, "type": "User"},
            "organization": {"login": "acme"},
            "repository": {"full_name": "acme/app"},
        }

        result = _normalize_webhook_event(payload, "pull_request", "delivery-123")

        assert result is not None
        assert result["activity_category"] == "code"
        assert result["action"] == "pull_request.opened"

    def test_webhook_push_event_category(self) -> None:
        payload = {
            "sender": {"login": "deployer", "id": 99, "type": "User"},
            "repository": {"full_name": "acme/infra"},
        }

        result = _normalize_webhook_event(payload, "push", "delivery-456")

        assert result is not None
        assert result["activity_category"] == "code"
        assert result["action"] == "push"

    def test_detects_bot_sender(self) -> None:
        payload = {
            "action": "completed",
            "sender": {"login": "dependabot[bot]", "id": 1001, "type": "Bot"},
            "organization": {"login": "acme"},
            "repository": {"full_name": "acme/lib"},
        }

        result = _normalize_webhook_event(payload, "workflow_run", "delivery-789")

        assert result is not None
        assert result["actor_is_bot"] is True

    def test_human_sender_not_bot(self) -> None:
        payload = {
            "action": "opened",
            "sender": {"login": "alice", "id": 42, "type": "User"},
            "organization": {"login": "acme"},
            "repository": {"full_name": "acme/app"},
        }

        result = _normalize_webhook_event(payload, "issues", "delivery-abc")

        assert result is not None
        assert result["actor_is_bot"] is False

    def test_missing_sender_not_bot(self) -> None:
        payload = {
            "action": "created",
            "organization": {"login": "acme"},
        }

        result = _normalize_webhook_event(payload, "repository", "delivery-xyz")

        assert result is not None
        assert result["actor_is_bot"] is False

    def test_ping_event_returns_none(self) -> None:
        result = _normalize_webhook_event({}, "ping", "delivery-ping")
        assert result is None

    def test_workflow_run_category(self) -> None:
        payload = {
            "action": "completed",
            "sender": {"login": "github-actions[bot]", "id": 65, "type": "Bot"},
            "repository": {"full_name": "acme/app"},
        }

        result = _normalize_webhook_event(payload, "workflow_run", "del-001")

        assert result is not None
        assert result["activity_category"] == "ci_cd"
        assert result["actor_is_bot"] is True
