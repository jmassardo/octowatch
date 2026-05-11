# Zero-Downtime Upgrade

**Audience**: Platform operators, release engineers  
**Components**: Helm chart, Alembic migrations, Celery workers

---

## Overview

OctoWatch supports zero-downtime upgrades through:

1. **Pre-upgrade migration job** — Alembic runs before new pods start.
2. **Rolling deployments** — API pods roll one at a time (`maxSurge: 1`, `maxUnavailable: 0`).
3. **Graceful worker shutdown** — Celery workers finish in-progress tasks before exiting.

---

## 1. Upgrade Procedure

### Standard Helm upgrade

```bash
# 1. Review what will change
helm diff upgrade octowatch ./helm \
  -f helm/values.yaml \
  -f helm/values-azure.yaml \
  --namespace octowatch

# 2. Run the upgrade
helm upgrade octowatch ./helm \
  -f helm/values.yaml \
  -f helm/values-azure.yaml \
  --namespace octowatch \
  --wait \
  --timeout 10m
```

### What happens during `helm upgrade`

```
helm upgrade
  │
  ├─ 1. Migration Job (post-sync hook, weight 5)
  │     └─ Runs: alembic upgrade head
  │     └─ Blocks until complete (backoffLimit: 3, deadline: 300s)
  │     └─ Deleted after success (hook-delete-policy: before-hook-creation,hook-succeeded)
  │
  ├─ 2. API Deployment (rolling update)
  │     └─ maxSurge: 1 — one new pod starts first
  │     └─ maxUnavailable: 0 — no old pods terminate until new is Ready
  │     └─ Readiness probe must pass before traffic shifts
  │
  ├─ 3. Worker Deployments (rolling update)
  │     └─ Each worker deployment rolls independently
  │     └─ Celery workers handle SIGTERM gracefully (see §3)
  │
  └─ 4. Beat Deployment (rolling update)
        └─ Single replica — brief gap is acceptable for scheduler
```

---

## 2. Migration Compatibility Guidelines

To maintain zero-downtime, database migrations **must be backwards-compatible**
with the currently running code version.  Follow these rules:

### Safe operations (online, no locks)

| Operation | Approach |
|-----------|----------|
| Add a nullable column | `ALTER TABLE ... ADD COLUMN ... NULL` — no table lock |
| Add an index | `CREATE INDEX CONCURRENTLY` — does not block reads/writes |
| Add a new table | Safe — existing code does not reference it |
| Backfill data | Use batched updates with `LIMIT` to avoid long transactions |

### Unsafe operations (require two-phase deploy)

| Operation | Approach |
|-----------|----------|
| Remove a column | Phase 1: Stop reading the column in code. Phase 2: Drop column in next release |
| Rename a column | Phase 1: Add new column + write to both. Phase 2: Drop old column |
| Add NOT NULL constraint | Phase 1: Backfill nulls. Phase 2: Add constraint with `NOT VALID`, then `VALIDATE` |
| Change column type | Phase 1: Add new column. Phase 2: Migrate data. Phase 3: Drop old column |

### TimescaleDB-specific considerations

- **Hypertable schema changes**: `ALTER TABLE` on hypertables may affect chunks.
  Always test on a staging instance first.
- **Compression policy changes**: Modify compression settings in a separate
  migration from schema changes.
- **Continuous aggregates**: Refresh policies must be updated if underlying
  hypertable schema changes.

---

## 3. Celery Worker Graceful Shutdown

OctoWatch's Celery configuration ensures no work is lost during upgrades:

```python
# celery_app.py
"task_acks_late": True,           # Ack only after task completes
"worker_prefetch_multiplier": 1,  # Fetch one task at a time
"task_reject_on_worker_lost": True,  # Re-queue if worker dies
```

### How it works

1. Kubernetes sends `SIGTERM` to the old worker pod.
2. Celery receives `SIGTERM` and stops accepting new tasks.
3. In-progress tasks continue until completion (up to `task_soft_time_limit` of 30 min).
4. Once all tasks finish, the worker exits cleanly.
5. Kubernetes waits up to `terminationGracePeriodSeconds` (default 30s) before `SIGKILL`.

### Recommendation

Set `terminationGracePeriodSeconds` on worker deployments to match the longest
expected task duration:

```yaml
# In deployment-worker.yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 1800  # 30 minutes — matches task_soft_time_limit
```

If a worker is killed before its task completes, `task_reject_on_worker_lost`
ensures the task is returned to the queue and picked up by another worker.

---

## 4. Rollback Procedure

### Helm rollback

```bash
# List release history
helm history octowatch --namespace octowatch

# Rollback to previous revision
helm rollback octowatch <revision> --namespace octowatch --wait
```

### Database rollback

If the new migration is incompatible with the old code:

```bash
# 1. Identify the target revision
kubectl exec -n octowatch deploy/octowatch-api -- alembic history | head -10

# 2. Downgrade to the previous revision
kubectl exec -n octowatch deploy/octowatch-api -- alembic downgrade -1

# 3. Then rollback the Helm release
helm rollback octowatch <revision> --namespace octowatch --wait
```

> **Important**: Only downgrade if the migration added columns/tables. If the
> migration was destructive (dropped columns), restore from backup instead.

---

## 5. Pre-Upgrade Checklist

Before running `helm upgrade`:

- [ ] **Backup**: Verify the latest automated backup completed successfully
- [ ] **Migration review**: Check new Alembic migrations for backwards compatibility
- [ ] **Staging tested**: New version deployed and validated on staging
- [ ] **Worker queues drained**: Check queue depth — large backlogs may cause long shutdown:
  ```bash
  kubectl exec -n octowatch deploy/octowatch-api -- \
    python -c "from app.celery_app import celery_app; print(celery_app.control.inspect().active())"
  ```
- [ ] **Maintenance window** (optional): Enable maintenance mode for major upgrades

---

## 6. Post-Upgrade Verification

After the upgrade completes:

- [ ] **Health check**: `curl -s https://<host>/health | jq .`
- [ ] **Readiness**: `curl -s https://<host>/ready | jq .`
- [ ] **Migration version**: `kubectl exec -n octowatch deploy/octowatch-api -- alembic current`
- [ ] **API version**: Check the `/api/v1/version` endpoint (if available)
- [ ] **Worker status**: Verify all worker pods are Running:
  ```bash
  kubectl -n octowatch get pods -l app.kubernetes.io/component=worker
  ```
- [ ] **Beat schedule**: Check beat pod logs for scheduled task registration
- [ ] **Ingestion flowing**: Monitor ingestion worker logs for new events
- [ ] **No errors**: Check for elevated error rates in logs or monitoring
