"""Tests for Epic 8 — Data Management: retention policies, S3 archival, GDPR erasure."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Shared helpers ──────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the admin router mounted."""
    from app.routers.admin import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _mock_db() -> AsyncMock:
    """Return an AsyncMock that behaves like an AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _admin_user() -> MagicMock:
    """Return a mock AuthenticatedUser with sys_admin role."""
    user = MagicMock()
    user.github_login = "admin-user"
    user.github_id = 99999
    user.has_role = MagicMock(return_value=True)
    return user


def _override_deps(app: FastAPI, db: AsyncMock, user: MagicMock) -> None:
    """Override auth, DB, Valkey, and CSRF deps for testing."""
    from app.deps import get_db, get_valkey, require_role, verify_csrf

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_valkey] = lambda: AsyncMock()
    app.dependency_overrides[verify_csrf] = lambda: None
    # Override every require_role call to return our admin user
    app.dependency_overrides[require_role(["sys_admin"])] = lambda: user
    # Also need a broader override: patch at the dependency level
    for dep_fn in [require_role(["sys_admin"]), require_role(["report_admin", "sys_admin"])]:
        app.dependency_overrides[dep_fn] = lambda: user


# ═══════════════════════════════════════════════════════════════════════════════
#  Issue #61 — Comprehensive Retention Policies
# ═══════════════════════════════════════════════════════════════════════════════


class TestRetentionService:
    """Unit tests for app.services.retention_service."""

    @pytest.mark.asyncio
    async def test_get_all_policies_returns_defaults(self) -> None:
        """All 8 tables should appear with their default retention days."""
        from app.services.retention_service import RETENTION_TABLES, get_all_policies

        db = _mock_db()
        # get_setting returns None → defaults used
        with patch(
            "app.services.retention_service.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            policies = await get_all_policies(db)

        assert len(policies) == len(RETENTION_TABLES)
        for table_name, meta in RETENTION_TABLES.items():
            assert table_name in policies
            assert policies[table_name]["retention_days"] == meta["default_days"]
            assert policies[table_name]["time_column"] == meta["time_col"]

    @pytest.mark.asyncio
    async def test_get_all_policies_uses_stored_values(self) -> None:
        """Stored setting should override the default."""
        from app.services.retention_service import get_all_policies

        db = _mock_db()

        async def _mock_get_setting(_db: Any, key: str) -> str | None:
            if key == "retention.events.days":
                return "180"
            return None

        with patch("app.services.retention_service.get_setting", side_effect=_mock_get_setting):
            policies = await get_all_policies(db)

        assert policies["events"]["retention_days"] == 180

    @pytest.mark.asyncio
    async def test_get_policy_unknown_table_raises(self) -> None:
        """Requesting a policy for an unknown table should raise ValueError."""
        from app.services.retention_service import get_policy

        db = _mock_db()
        with pytest.raises(ValueError, match="Unknown retention table"):
            await get_policy(db, "nonexistent_table")

    @pytest.mark.asyncio
    async def test_update_policy_stores_and_logs(self) -> None:
        """update_policy should call set_setting and log_action."""
        from app.services.retention_service import update_policy

        db = _mock_db()

        with (
            patch(
                "app.services.retention_service.get_setting",
                new_callable=AsyncMock,
                return_value="365",
            ),
            patch(
                "app.services.retention_service.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
            patch(
                "app.services.retention_service.log_action",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            await update_policy(db, "events", 180, user_login="admin", ip_address="127.0.0.1")

        mock_set.assert_called_once()
        assert mock_set.call_args.args[1] == "retention.events.days"
        assert mock_set.call_args.args[2] == "180"

        mock_log.assert_called_once()
        log_kwargs = mock_log.call_args.kwargs
        assert log_kwargs["action_type"] == "retention_policy_update"
        assert log_kwargs["resource_id"] == "events"
        assert log_kwargs["parameters"]["old_days"] == 365
        assert log_kwargs["parameters"]["new_days"] == 180

    @pytest.mark.asyncio
    async def test_update_policy_rejects_unknown_table(self) -> None:
        """Updating a policy for an unknown table should raise ValueError."""
        from app.services.retention_service import update_policy

        db = _mock_db()
        with pytest.raises(ValueError, match="Unknown retention table"):
            await update_policy(db, "fake_table", 30, user_login="admin")

    @pytest.mark.asyncio
    async def test_update_policy_rejects_invalid_days(self) -> None:
        """retention_days < 1 should raise ValueError."""
        from app.services.retention_service import update_policy

        db = _mock_db()
        with pytest.raises(ValueError, match="retention_days must be >= 1"):
            await update_policy(db, "events", 0, user_login="admin")

    @pytest.mark.asyncio
    async def test_enforce_retention_deletes_old_rows(self) -> None:
        """enforce_retention should run DELETE … WHERE time_col < cutoff."""
        from app.services.retention_service import enforce_retention

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 42
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.retention_service.get_setting",
            new_callable=AsyncMock,
            return_value="30",
        ):
            deleted = await enforce_retention(db, "events")

        assert deleted == 42
        # Verify the SQL includes the correct table and column
        call_args = db.execute.call_args
        raw = call_args.args[0]
        sql_text = str(raw.text if hasattr(raw, "text") else raw)
        assert "events" in sql_text
        assert "created_at" in sql_text

    @pytest.mark.asyncio
    async def test_enforce_retention_calls_archive_callback(self) -> None:
        """If archive_callback is provided, it should be called before deletion."""
        from app.services.retention_service import enforce_retention

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 10
        db.execute = AsyncMock(return_value=mock_result)

        archive_cb = AsyncMock()

        with patch(
            "app.services.retention_service.get_setting",
            new_callable=AsyncMock,
            return_value="30",
        ):
            await enforce_retention(db, "detections", archive_callback=archive_cb)

        archive_cb.assert_called_once()
        args = archive_cb.call_args.args
        assert args[1] == "detections"
        # Third arg is cutoff datetime
        assert isinstance(args[2], datetime)

    @pytest.mark.asyncio
    async def test_enforce_all_iterates_tables(self) -> None:
        """enforce_all should process all tables and return per-table counts."""
        from app.services.retention_service import RETENTION_TABLES, enforce_all

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.retention_service.get_setting",
            new_callable=AsyncMock,
            return_value="30",
        ):
            results = await enforce_all(db)

        assert len(results) == len(RETENTION_TABLES)
        for table in RETENTION_TABLES:
            assert table in results

    @pytest.mark.asyncio
    async def test_raw_payloads_retention_independent(self) -> None:
        """event_raw_payloads has its own retention separate from events."""
        from app.services.retention_service import get_all_policies

        db = _mock_db()
        with patch(
            "app.services.retention_service.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            policies = await get_all_policies(db)

        # Defaults differ: events=365, raw_payloads=90
        assert policies["events"]["retention_days"] == 365
        assert policies["event_raw_payloads"]["retention_days"] == 90

    def test_retention_tables_have_required_fields(self) -> None:
        """Each table config must specify time_col and default_days."""
        from app.services.retention_service import RETENTION_TABLES

        for table_name, meta in RETENTION_TABLES.items():
            assert "time_col" in meta, f"{table_name} missing time_col"
            assert "default_days" in meta, f"{table_name} missing default_days"
            assert isinstance(meta["default_days"], int)


# ═══════════════════════════════════════════════════════════════════════════════
#  Issue #63 — Data Archival to Object Storage
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchiveService:
    """Unit tests for app.services.archive_service."""

    @pytest.mark.asyncio
    async def test_archive_rows_creates_ndjson_gz(self) -> None:
        """archive_rows should upload a gzipped NDJSON file to S3."""
        from app.services.archive_service import archive_rows

        db = _mock_db()
        cutoff = datetime(2024, 6, 1, tzinfo=UTC)

        # Simulate 2 rows returned from the DB
        mock_rows = [
            ({"id": 1, "actor": "alice", "created_at": "2024-01-01T00:00:00"},),
            ({"id": 2, "actor": "bob", "created_at": "2024-02-01T00:00:00"},),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        db.execute = AsyncMock(return_value=mock_result)

        s3 = MagicMock()
        key = await archive_rows(db, "events", cutoff, s3_client=s3, bucket="test-bucket")

        assert key == "archive/events/2024/06/data.ndjson.gz"
        s3.put_object.assert_called_once()
        call_kwargs = s3.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == key

        # Verify the uploaded body is valid gzipped NDJSON
        body = call_kwargs["Body"]
        decompressed = gzip.decompress(body).decode("utf-8")
        lines = decompressed.strip().split("\n")
        assert len(lines) == 2
        record1 = json.loads(lines[0])
        assert record1["actor"] == "alice"

    @pytest.mark.asyncio
    async def test_archive_rows_empty_returns_empty_key(self) -> None:
        """If no rows match the cutoff, archive_rows returns an empty string."""
        from app.services.archive_service import archive_rows

        db = _mock_db()
        cutoff = datetime(2024, 6, 1, tzinfo=UTC)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        s3 = MagicMock()
        key = await archive_rows(db, "events", cutoff, s3_client=s3, bucket="b")
        assert key == ""
        s3.put_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_archive_rows_unknown_table_raises(self) -> None:
        """Archiving an unknown table should raise ValueError."""
        from app.services.archive_service import archive_rows

        db = _mock_db()
        s3 = MagicMock()
        with pytest.raises(ValueError, match="Unknown archive table"):
            await archive_rows(db, "nonexistent", datetime.now(UTC), s3_client=s3, bucket="b")

    @pytest.mark.asyncio
    async def test_restore_archive_imports_rows(self) -> None:
        """restore_archive should decompress and INSERT rows from NDJSON."""
        from app.services.archive_service import restore_archive

        db = _mock_db()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        # Build a fake archive
        records = [
            {
                "id": 1,
                "document_id": "d1",
                "created_at": "2024-01-01T00:00:00",
                "action": "repos.create",
                "actor": "alice",
                "data": {},
                "ingested_at": "2024-01-01",
                "ingestion_source": "s3",
                "source_file_path": "f.json",
            },
            {
                "id": 2,
                "document_id": "d2",
                "created_at": "2024-02-01T00:00:00",
                "action": "repos.delete",
                "actor": "bob",
                "data": {},
                "ingested_at": "2024-02-01",
                "ingestion_source": "s3",
                "source_file_path": "g.json",
            },
        ]
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for rec in records:
                gz.write((json.dumps(rec) + "\n").encode())
        buf.seek(0)

        s3 = MagicMock()
        body_mock = MagicMock(read=MagicMock(return_value=buf.getvalue()))
        s3.get_object.return_value = {"Body": body_mock}

        restored = await restore_archive(
            db, "archive/events/2024/01/data.ndjson.gz", s3_client=s3, bucket="b"
        )
        assert restored == 2
        # 2 INSERT calls
        assert db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_restore_archive_invalid_path_raises(self) -> None:
        """An archive path not starting with 'archive/' should raise."""
        from app.services.archive_service import restore_archive

        db = _mock_db()
        s3 = MagicMock()
        with pytest.raises(ValueError, match="Invalid archive path"):
            await restore_archive(db, "bad/path.ndjson.gz", s3_client=s3, bucket="b")

    @pytest.mark.asyncio
    async def test_restore_archive_unknown_table_raises(self) -> None:
        """An archive path with unknown table should raise."""
        from app.services.archive_service import restore_archive

        db = _mock_db()
        s3 = MagicMock()
        with pytest.raises(ValueError, match="Unknown table"):
            await restore_archive(
                db, "archive/nonexistent/2024/01/data.ndjson.gz", s3_client=s3, bucket="b"
            )

    def test_list_archives_paginates(self) -> None:
        """list_archives should paginate through S3 and return file metadata."""
        from app.services.archive_service import list_archives

        s3 = MagicMock()
        paginator = MagicMock()
        s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {
                        "Key": "archive/events/2024/01/data.ndjson.gz",
                        "Size": 1024,
                        "LastModified": datetime(2024, 1, 31, tzinfo=UTC),
                    },
                ]
            }
        ]

        result = list_archives(s3_client=s3, bucket="b", table_name="events")
        assert len(result) == 1
        assert result[0]["key"] == "archive/events/2024/01/data.ndjson.gz"
        assert result[0]["size_bytes"] == 1024

    def test_archive_key_format(self) -> None:
        """Archive keys should follow archive/{table}/{year}/{month}/data.ndjson.gz."""
        from app.services.archive_service import _archive_key

        key = _archive_key("detections", datetime(2025, 3, 15, tzinfo=UTC))
        assert key == "archive/detections/2025/03/data.ndjson.gz"

    def test_ndjson_format_valid(self) -> None:
        """Each line in the archive should be valid JSON (NDJSON format)."""
        records = [{"id": i, "value": f"test_{i}"} for i in range(5)]
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for rec in records:
                gz.write((json.dumps(rec) + "\n").encode())
        buf.seek(0)

        decompressed = gzip.decompress(buf.getvalue()).decode("utf-8")
        lines = decompressed.strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            parsed = json.loads(line)
            assert "id" in parsed


# ═══════════════════════════════════════════════════════════════════════════════
#  Issue #66 — GDPR Right-to-Erasure
# ═══════════════════════════════════════════════════════════════════════════════


class TestGdprService:
    """Unit tests for app.services.gdpr_service."""

    @pytest.mark.asyncio
    async def test_erase_user_anonymizes_events(self) -> None:
        """Events should be anonymized (actor replaced with pseudonym)."""
        from app.services.gdpr_service import _redacted_token, erase_user

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.gdpr_service.log_action", new_callable=AsyncMock):
            result = await erase_user(db, "octocat", authorized_by="admin")

        assert result["github_login"] == "octocat"
        assert result["pseudonym"] == _redacted_token("octocat")
        assert "events" in result["affected_tables"]

    @pytest.mark.asyncio
    async def test_erase_user_deletes_idp_enrichments(self) -> None:
        """IdP enrichments should be deleted entirely, not anonymized."""
        from app.services.gdpr_service import erase_user

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.gdpr_service.log_action", new_callable=AsyncMock):
            await erase_user(db, "octocat", authorized_by="admin")

        # Verify DELETE was called for idp_actor_enrichments
        delete_calls = [
            call
            for call in db.execute.call_args_list
            if "DELETE" in str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0])
            and "idp_actor_enrichments"
            in str(call.args[0].text if hasattr(call.args[0], "text") else call.args[0])
        ]
        assert len(delete_calls) >= 1

    @pytest.mark.asyncio
    async def test_erase_user_creates_audit_entry(self) -> None:
        """A GDPR erasure audit trail entry should be created."""
        from app.services.gdpr_service import erase_user

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.gdpr_service.log_action", new_callable=AsyncMock) as mock_log:
            await erase_user(db, "octocat", authorized_by="admin", ip_address="10.0.0.1")

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action_type"] == "gdpr_erasure"
        assert kwargs["resource_type"] == "user"
        assert kwargs["resource_id"] == "octocat"
        assert kwargs["user_login"] == "admin"
        assert kwargs["ip_address"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_erase_user_empty_login_raises(self) -> None:
        """An empty github_login should raise ValueError."""
        from app.services.gdpr_service import erase_user

        db = _mock_db()
        with pytest.raises(ValueError, match="github_login must not be empty"):
            await erase_user(db, "", authorized_by="admin")

    def test_redacted_token_consistency(self) -> None:
        """The same login should always produce the same pseudonym."""
        from app.services.gdpr_service import _redacted_token

        token1 = _redacted_token("octocat")
        token2 = _redacted_token("octocat")
        assert token1 == token2

        # Different logins produce different tokens
        token3 = _redacted_token("different-user")
        assert token1 != token3

    def test_redacted_token_format(self) -> None:
        """Pseudonym should be REDACTED-{8_hex_chars}."""
        from app.services.gdpr_service import _redacted_token

        token = _redacted_token("testuser")
        assert token.startswith("REDACTED-")
        hex_part = token.split("-", 1)[1]
        assert len(hex_part) == 8
        # Should be valid hex
        int(hex_part, 16)

    def test_redacted_token_matches_sha256(self) -> None:
        """Pseudonym should match SHA-256 of the login."""
        from app.services.gdpr_service import _redacted_token

        login = "octocat"
        expected_hex = hashlib.sha256(login.encode("utf-8")).hexdigest()[:8]
        assert _redacted_token(login) == f"REDACTED-{expected_hex}"

    @pytest.mark.asyncio
    async def test_erase_user_covers_all_tables(self) -> None:
        """The erasure should touch all configured target tables."""
        from app.services.gdpr_service import _ERASURE_TARGETS, erase_user

        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.gdpr_service.log_action", new_callable=AsyncMock):
            result = await erase_user(db, "octocat", authorized_by="admin")

        for target in _ERASURE_TARGETS:
            assert target["table"] in result["affected_tables"]

    @pytest.mark.asyncio
    async def test_erase_user_handles_table_error_gracefully(self) -> None:
        """If one table fails, others should still be processed."""
        from app.services.gdpr_service import erase_user

        db = _mock_db()
        call_count = 0

        async def _side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error")
            result = MagicMock()
            result.rowcount = 2
            return result

        db.execute = AsyncMock(side_effect=_side_effect)

        with patch("app.services.gdpr_service.log_action", new_callable=AsyncMock):
            result = await erase_user(db, "octocat", authorized_by="admin")

        # First table had an error → -1, others should have counts
        tables = result["affected_tables"]
        assert -1 in tables.values()
        assert any(v >= 0 for v in tables.values())


# ═══════════════════════════════════════════════════════════════════════════════
#  Schema tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemas:
    """Tests for the updated integration schemas."""

    def test_retention_config_defaults(self) -> None:
        """RetentionConfig should have sane defaults for all tables."""
        from app.schemas.integration import RetentionConfig

        config = RetentionConfig()
        assert config.events_retention_days == 365
        assert config.raw_payloads_retention_days == 90
        assert config.detections_retention_days == 730
        assert config.audit_trail_retention_days == 730
        assert config.event_dedup_retention_days == 7
        assert config.enterprise_sync_log_retention_days == 90
        assert config.behavioral_baselines_retention_days == 180
        assert config.system_health_events_retention_days == 90

    def test_retention_config_validation(self) -> None:
        """RetentionConfig should reject out-of-range values."""
        from pydantic import ValidationError

        from app.schemas.integration import RetentionConfig

        with pytest.raises(ValidationError):
            RetentionConfig(events_retention_days=0)
        with pytest.raises(ValidationError):
            RetentionConfig(events_retention_days=5000)

    def test_retention_update_request(self) -> None:
        """RetentionUpdateRequest should accept a policies dict."""
        from app.schemas.integration import RetentionUpdateRequest

        req = RetentionUpdateRequest(policies={"events": 180, "detections": 365})
        assert req.policies["events"] == 180

    def test_gdpr_erase_request_validation(self) -> None:
        """GdprEraseRequest should require a non-empty github_login."""
        from pydantic import ValidationError

        from app.schemas.integration import GdprEraseRequest

        with pytest.raises(ValidationError):
            GdprEraseRequest(github_login="")

    def test_gdpr_erase_response(self) -> None:
        """GdprEraseResponse should serialize correctly."""
        from app.schemas.integration import GdprEraseResponse

        resp = GdprEraseResponse(
            github_login="octocat",
            pseudonym="REDACTED-abc12345",
            affected_tables={"events": 5, "detections": 2},
        )
        assert resp.pseudonym == "REDACTED-abc12345"

    def test_archive_restore_request(self) -> None:
        """ArchiveRestoreRequest should require a non-empty path."""
        from pydantic import ValidationError

        from app.schemas.integration import ArchiveRestoreRequest

        with pytest.raises(ValidationError):
            ArchiveRestoreRequest(archive_path="")

        req = ArchiveRestoreRequest(archive_path="archive/events/2024/01/data.ndjson.gz")
        assert req.archive_path.startswith("archive/")

    def test_retention_policy_item(self) -> None:
        """RetentionPolicyItem should hold all expected fields."""
        from app.schemas.integration import RetentionPolicyItem

        item = RetentionPolicyItem(
            table_name="events",
            time_column="created_at",
            retention_days=365,
            default_days=365,
            row_count=1000,
            size_bytes=2048000,
        )
        assert item.table_name == "events"
        assert item.row_count == 1000


# ═══════════════════════════════════════════════════════════════════════════════
#  Celery beat schedule tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCeleryConfig:
    """Verify the retention worker is registered in the Celery beat schedule."""

    def test_retention_task_in_beat_schedule(self) -> None:
        """enforce-retention-policies should be in the beat schedule."""
        from app.celery_app import celery_app

        assert "enforce-retention-policies" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["enforce-retention-policies"]
        assert entry["task"] == "app.workers.retention_worker.enforce_all_retention_policies"

    def test_retention_worker_in_includes(self) -> None:
        """retention_worker should be in conf.include for task discovery."""
        from app.celery_app import celery_app

        includes = celery_app.conf.include or []
        assert "app.workers.retention_worker" in includes

    def test_dedup_prune_still_scheduled(self) -> None:
        """The existing prune-event-dedup task should still be present."""
        from app.celery_app import celery_app

        assert "prune-event-dedup" in celery_app.conf.beat_schedule


# ═══════════════════════════════════════════════════════════════════════════════
#  Model export tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelExports:
    """Verify new model exports are registered."""

    def test_system_health_event_exported(self) -> None:
        """SystemHealthEvent should be importable from app.models."""
        from app.models import SystemHealthEvent

        assert SystemHealthEvent.__tablename__ == "system_health_events"

    def test_sync_log_entry_exported(self) -> None:
        """SyncLogEntry should be importable from app.models."""
        from app.models import SyncLogEntry

        assert SyncLogEntry.__tablename__ == "enterprise_sync_log_entries"
