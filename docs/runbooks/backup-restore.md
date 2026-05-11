# Database Backup & Restore

**Audience**: Platform operators, on-call engineers  
**Components**: TimescaleDB (PostgreSQL 16), Helm CronJob, `scripts/backup.sh`, `scripts/restore.sh`

---

## Overview

OctoWatch stores all audit log events, detections, and configuration in a
TimescaleDB database.  This runbook covers automated and manual backup
procedures, restore steps (including TimescaleDB-specific hooks), and
post-restore verification.

---

## 1. Automated Backups (Helm CronJob)

The Helm chart includes a `CronJob` that runs `pg_dump` on a configurable
schedule and uploads the backup to S3-compatible storage.

### Enable in values

```yaml
# values-azure.yaml (or your environment overlay)
backup:
  enabled: true
  schedule: "0 2 * * *"           # Daily at 02:00 UTC
  bucket: "octowatch-backups"     # S3 bucket name
  retentionDays: 30               # Days to retain old backups
  image: timescale/timescaledb:2.25.1-pg16
```

### How it works

1. The CronJob runs at the configured schedule.
2. `pg_dump` creates a compressed custom-format dump (`--format=custom --compress=9`).
3. If the `aws` CLI is available in the image, the backup is uploaded to
   `s3://<bucket>/octowatch/backups/<timestamp>.sql.gz`.
4. Old backups beyond `retentionDays` are pruned from S3.
5. The local temp file is deleted after upload.

### Verify CronJob is running

```bash
kubectl -n octowatch get cronjob
kubectl -n octowatch get jobs --sort-by=.metadata.creationTimestamp | tail -5
```

### Check backup job logs

```bash
kubectl -n octowatch logs job/octowatch-db-backup-<timestamp>
```

---

## 2. Manual Backup

Use `scripts/backup.sh` for ad-hoc backups from any machine with `pg_dump`
and network access to the database.

### Usage

```bash
# Local backup only
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs" \
  ./scripts/backup.sh

# Backup + upload to S3
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs" \
  ./scripts/backup.sh s3://my-bucket/backups
```

### What the script does

1. Validates `DATABASE_URL` and `pg_dump` are available.
2. Runs `pg_dump` with flags: `--no-owner --no-acl --format=custom --compress=9`.
3. Saves to `./backups/octowatch-backup-<timestamp>.dump`.
4. Optionally uploads to the provided S3 path.

### TimescaleDB compatibility

The `--format=custom` flag produces a dump that is compatible with
TimescaleDB's `timescaledb_pre_restore()` / `timescaledb_post_restore()`
hooks.  No additional flags are needed — the dump includes hypertable
definitions and chunk metadata.

---

## 3. Restore Procedure

Use `scripts/restore.sh` to restore from a backup file or S3 path.

### Prerequisites

- **Stop all OctoWatch services** (API, workers, beat) before restoring.
- Ensure `pg_restore` and `psql` are available.
- The target database must exist (can be empty).

### Usage

```bash
# From local file
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs" \
  ./scripts/restore.sh backups/octowatch-backup-20260501-020000.dump

# From S3
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs" \
  ./scripts/restore.sh s3://octowatch-backups/octowatch/backups/20260501-020000.sql.gz
```

### Restore steps (performed by the script)

| Step | Action | Notes |
|------|--------|-------|
| 1 | Download from S3 (if S3 path) | Uses `aws s3 cp` |
| 2 | Ensure TimescaleDB extension exists | `CREATE EXTENSION IF NOT EXISTS timescaledb` |
| 3 | Run `timescaledb_pre_restore()` | Prepares internal catalog for restore |
| 4 | `pg_restore --clean --if-exists` | Drops and recreates all objects |
| 5 | Run `timescaledb_post_restore()` | Rebuilds chunk indexes and catalog |
| 6 | Verify hypertable integrity | Queries `timescaledb_information.hypertables` |
| 7 | Check chunk health | Lists chunks with compression status |
| 8 | Verify Alembic migrations | Runs `alembic check` and `alembic upgrade head` if needed |

### Kubernetes restore

If restoring to the AKS cluster database:

```bash
# 1. Scale down all deployments
kubectl -n octowatch scale deploy --all --replicas=0

# 2. Port-forward to the database
kubectl -n octowatch port-forward svc/octowatch-timescaledb 5432:5432

# 3. Run restore (in another terminal)
DATABASE_URL="postgresql://app_rw:pass@localhost:5432/auditlogs" \
  ./scripts/restore.sh backups/octowatch-backup-20260501-020000.dump

# 4. Scale back up
kubectl -n octowatch scale deploy --all --replicas=1
# (HPA will scale API back to min replicas automatically)
```

---

## 4. Post-Restore Verification Checklist

After restoring, verify the following before re-enabling services:

- [ ] **Alembic version matches code**: `alembic current` shows the expected head revision
- [ ] **Hypertables intact**: `SELECT * FROM timescaledb_information.hypertables` returns expected tables
- [ ] **Event count reasonable**: `SELECT COUNT(*) FROM events WHERE created_at > NOW() - INTERVAL '7 days'`
- [ ] **Detections present**: `SELECT COUNT(*) FROM detections`
- [ ] **Ingestion cursors valid**: `SELECT * FROM ingestion_cursors WHERE status = 'active'`
- [ ] **Health endpoints**: After starting services, verify `/health` and `/ready` return 200
- [ ] **Ingestion flowing**: Check worker logs for successful ingestion after restart

---

## 5. Backup Retention & Rotation

### S3 lifecycle policy (recommended)

Configure an S3 lifecycle rule as a safety net in case the CronJob pruning
fails:

```json
{
  "Rules": [{
    "ID": "octowatch-backup-retention",
    "Prefix": "octowatch/backups/",
    "Status": "Enabled",
    "Expiration": { "Days": 90 }
  }]
}
```

### Local backup cleanup

Local backups in `./backups/` are not auto-pruned.  Add a cron job or
periodically delete old files:

```bash
find ./backups/ -name "octowatch-backup-*.dump" -mtime +30 -delete
```

---

## 6. Disaster Recovery Scenarios

### Scenario: Complete database loss

1. Provision a new TimescaleDB instance.
2. Create the database and `timescaledb` extension.
3. Run `scripts/restore.sh` with the latest backup.
4. Verify with the checklist above.
5. Restart all services.

### Scenario: Corrupted table

1. Identify the affected table.
2. Take a fresh backup of the current state (even if corrupted).
3. Restore from the last known good backup.
4. Compare event counts to assess data loss window.
5. Re-ingest missing data if the ingestion sources still have the original files.

### Scenario: Failed migration

1. Check `alembic current` to identify the stuck migration.
2. If the migration is partially applied, run `alembic downgrade -1` to revert.
3. Fix the migration script and re-run `alembic upgrade head`.
4. If downgrade fails, restore from the pre-upgrade backup.
