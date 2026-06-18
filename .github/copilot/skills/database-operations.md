---
name: database-operations
description: Run database operations against the OctoWatch TimescaleDB instance. Use for migrations, queries, backups, and troubleshooting.
---

# Database Operations Skill

Run database operations against the OctoWatch TimescaleDB (PostgreSQL) instance.

## Access

Database runs as a container in the Kubernetes cluster. Access via:

### From management VM
```bash
# Get connection string
kubectl exec -it -n octowatch deployment/backend -- \
  python -c "from app.config import settings; print(settings.database_url)"

# Direct psql (if psql installed on mgmt VM)
psql "postgresql://user:pass@host:5432/octowatch"

# Via kubectl exec into backend pod
kubectl exec -it -n octowatch deployment/backend -- \
  python -c "
from app.database import get_sync_engine
from sqlalchemy import text
with get_sync_engine().connect() as conn:
    result = conn.execute(text('SELECT count(*) FROM audit_events'))
    print(result.scalar())
"
```

## Migrations

### Run pending migrations
```bash
kubectl exec -it -n octowatch deployment/backend -- \
  alembic upgrade head
```

### Check migration status
```bash
kubectl exec -it -n octowatch deployment/backend -- \
  alembic current
```

### Create new migration
```bash
cd backend
alembic revision --autogenerate -m "description_of_change"
```

## Common Queries

### Event counts by type
```sql
SELECT action, count(*) FROM audit_events
WHERE created_at > now() - interval '24 hours'
GROUP BY action ORDER BY count DESC LIMIT 20;
```

### Check hypertable health
```sql
SELECT hypertable_name, num_chunks, total_bytes
FROM timescaledb_information.hypertable_sizes;
```

### Check ingestion lag
```sql
SELECT max(created_at), now() - max(created_at) as lag
FROM audit_events;
```

## Backups

### Manual backup
```bash
# From management VM
kubectl exec -n octowatch deployment/timescaledb -- \
  pg_dump -U octowatch -Fc octowatch > backup_$(date +%Y%m%d).dump
```

### Restore
```bash
kubectl exec -i -n octowatch deployment/timescaledb -- \
  pg_restore -U octowatch -d octowatch < backup.dump
```

## Safety
- Always use transactions for data modifications
- Test migrations on a backup/staging DB before production
- Never drop hypertables without explicit user confirmation
- Backup before any destructive operation
