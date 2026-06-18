# Database Backup & Restore

**Audience**: Platform operators, on-call engineers  
**Components**: TimescaleDB (PostgreSQL 16), Helm CronJob, management VM,
`scripts/backup.sh`, `scripts/restore.sh`

---

## Overview

OctoWatch stores all audit log events, detections, and configuration in a
TimescaleDB database. This runbook covers automated and manual backup
procedures, restore steps (including TimescaleDB-specific hooks), and
post-restore verification.

For the **self-managed kubeadm deployment**, the management VM is the normal
operator entry point for backup verification, `kubectl port-forward`, and
restore operations.

---

## 1. Automated Backups

### Option A: Helm CronJob

The Helm chart includes an optional `CronJob` that runs `pg_dump` on a
configurable schedule and uploads the backup to S3-compatible storage.

> In the self-managed cluster overlay, this CronJob is typically disabled by
> default and scheduled backups are often run from the management VM instead.
> Enable it only if you want in-cluster scheduled backups.

#### Enable in values

```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"
  bucket: "octowatch-backups"
  retentionDays: 30
  image: timescale/timescaledb:2.25.1-pg16
```

#### Verify the CronJob

```bash
kubectl -n octowatch get cronjob
kubectl -n octowatch get jobs --sort-by=.metadata.creationTimestamp | tail -5
kubectl -n octowatch logs job/octowatch-db-backup-<timestamp>
```

### Option B: Management VM scheduled backups

Many self-managed installations schedule `pg_dump` from the management VM,
writing the dump to operator-managed storage (for example Azure Blob Storage or
an S3-compatible bucket). This keeps backup orchestration outside the workload
cluster while still using the cluster database endpoint.

---

## 2. Manual Backup

Use `scripts/backup.sh` for ad-hoc backups from any machine with `pg_dump` and
network access to the database.

### Usage

```bash
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs"   ./scripts/backup.sh

DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs"   ./scripts/backup.sh s3://my-bucket/backups
```

### What the script does

1. Validates `DATABASE_URL` and `pg_dump` are available.
2. Runs `pg_dump` with `--no-owner --no-acl --format=custom --compress=9`.
3. Saves to `./backups/octowatch-backup-<timestamp>.dump`.
4. Optionally uploads to the provided S3 path.

### TimescaleDB compatibility

The custom-format dump is compatible with
`timescaledb_pre_restore()` / `timescaledb_post_restore()` hooks.

---

## 3. Restore Procedure

Use `scripts/restore.sh` to restore from a backup file or S3 path.

### Prerequisites

- Stop OctoWatch API, workers, and beat before restoring.
- Ensure `pg_restore` and `psql` are available.
- The target database must already exist.

### Usage

```bash
DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs"   ./scripts/restore.sh backups/octowatch-backup-20260501-020000.dump

DATABASE_URL="postgresql://app_rw:pass@db-host:5432/auditlogs"   ./scripts/restore.sh s3://octowatch-backups/octowatch/backups/20260501-020000.sql.gz
```

### Restore steps performed by the script

| Step | Action | Notes |
|------|--------|-------|
| 1 | Download from S3 (if needed) | Uses `aws s3 cp` |
| 2 | Ensure TimescaleDB extension exists | `CREATE EXTENSION IF NOT EXISTS timescaledb` |
| 3 | Run `timescaledb_pre_restore()` | Prepares internal catalog |
| 4 | `pg_restore --clean --if-exists` | Drops and recreates objects |
| 5 | Run `timescaledb_post_restore()` | Rebuilds Timescale metadata |
| 6 | Verify hypertable integrity | Checks `timescaledb_information.hypertables` |
| 7 | Check chunk health | Lists chunks and compression status |
| 8 | Verify Alembic migrations | `alembic check` / `alembic upgrade head` |

### Kubernetes restore (self-managed cluster)

Run these commands from the **management VM** or from another host with the same
kubeconfig and namespace access:

```bash
kubectl -n octowatch scale deploy --all --replicas=0
kubectl -n octowatch port-forward svc/octowatch-timescaledb 5432:5432
```

In another terminal on the same admin host:

```bash
DATABASE_URL="postgresql://app_rw:pass@localhost:5432/auditlogs"   ./scripts/restore.sh backups/octowatch-backup-20260501-020000.dump
```

Then restore normal workload replicas:

```bash
kubectl -n octowatch scale deploy/octowatch-api --replicas=2
kubectl -n octowatch scale deploy/octowatch-frontend --replicas=1
kubectl -n octowatch scale deploy/octowatch-worker-ingestion --replicas=4
kubectl -n octowatch scale deploy/octowatch-worker-detection --replicas=4
kubectl -n octowatch scale deploy/octowatch-worker-notification --replicas=2
kubectl -n octowatch scale deploy/octowatch-worker-baseline --replicas=2
kubectl -n octowatch scale deploy/octowatch-beat --replicas=1
```

Adjust replica counts if your overlay differs.

---

## 4. Post-Restore Verification Checklist

- [ ] `alembic current` matches the expected head revision
- [ ] `timescaledb_information.hypertables` returns expected tables
- [ ] Recent event counts look reasonable
- [ ] Detections exist as expected
- [ ] `ingestion_cursors` state is valid
- [ ] `/health` and `/ready` return `200` after restart
- [ ] Worker logs show successful ingest after restart

---

## 5. Backup Retention & Rotation

### S3 lifecycle policy

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

```bash
find ./backups/ -name "octowatch-backup-*.dump" -mtime +30 -delete
```

---

## 6. Disaster Recovery Scenarios

### Complete database loss

1. Provision a new TimescaleDB instance.
2. Create the database and enable `timescaledb`.
3. Run `scripts/restore.sh` with the latest backup.
4. Verify with the checklist above.
5. Restart services.

### Corrupted table

1. Identify the affected table.
2. Take a fresh backup of the current state.
3. Restore from the last known good backup.
4. Compare counts to determine the loss window.
5. Re-ingest missing data if the source still has it.

### Failed migration

1. Check `alembic current`.
2. If safe, run `alembic downgrade -1`.
3. Fix the migration and re-run `alembic upgrade head`.
4. If downgrade is unsafe, restore from the pre-upgrade backup.
