# High Availability Configuration Guide

**Audience**: Platform operators, infrastructure engineers  
**Components**: API, Celery workers, Celery Beat, TimescaleDB, Valkey, Ingress

---

## Overview

This guide covers how to run OctoWatch in a highly available configuration
where no single component failure causes data loss or extended downtime.

### Architecture Summary

```
                    ┌──────────────┐
                    │   Ingress    │
                    │  (nginx LB)  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  API (1) │ │  API (2) │ │  API (n) │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │             │             │
    ┌────────┴─────────────┴─────────────┴────────┐
    │              Valkey (Broker)                  │
    └────────┬─────────────┬─────────────┬────────┘
             ▼             ▼             ▼
      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │  Workers   │ │  Workers   │ │  Workers   │
      │(ingestion) │ │(detection) │ │(baseline)  │
      └──────┬─────┘ └──────┬─────┘ └──────┬─────┘
             │               │               │
             └───────────────┼───────────────┘
                             ▼
                    ┌──────────────┐
                    │ TimescaleDB  │
                    │  (Primary)   │
                    └──────────────┘
```

---

## 1. API High Availability

### Horizontal Pod Autoscaler (HPA)

The Helm chart includes an HPA for the API deployment:

```yaml
# helm/templates/hpa-api.yaml (already configured)
apiVersion: autoscaling/v2
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # Prevent flapping
    scaleUp:
      stabilizationWindowSeconds: 60
```

### PodDisruptionBudget (PDB)

The Helm chart includes a PDB to ensure at least one API pod remains available
during voluntary disruptions (node drains, upgrades):

```yaml
# helm/templates/pdb-api.yaml
apiVersion: policy/v1
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: api
```

### Rolling Update Strategy

The API deployment uses a rolling update strategy that ensures zero downtime:

```yaml
# deployment-api.yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1        # Start one new pod before stopping old
    maxUnavailable: 0  # Never remove a pod until replacement is ready
```

### Session handling

API pods are stateless — all session state is stored in Valkey.  Any pod can
handle any request.  The Ingress load balancer distributes traffic
round-robin.

---

## 2. Worker High Availability

### Queue-based scaling with KEDA

OctoWatch uses KEDA (Kubernetes Event-Driven Autoscaling) to scale worker
deployments based on Valkey queue depth:

```yaml
# values-azure.yaml
keda:
  enabled: true

workers:
  ingestion:
    replicas: 4    # Base replicas (KEDA scales above this)
  detection:
    replicas: 4
  notification:
    replicas: 2
  baseline:
    replicas: 2
```

KEDA ScaledObjects are defined in `helm/templates/keda-scaled-objects.yaml`
and scale each worker deployment independently based on queue length.

### Without KEDA

If KEDA is not available, set static replica counts in values:

```yaml
keda:
  enabled: false

workers:
  ingestion:
    replicas: 4    # Fixed replica count
  detection:
    replicas: 4
```

### Worker reliability

Celery is configured for at-least-once delivery:

| Setting | Value | Effect |
|---------|-------|--------|
| `task_acks_late` | `True` | Tasks acknowledged only after completion |
| `worker_prefetch_multiplier` | `1` | Workers fetch one task at a time |
| `task_reject_on_worker_lost` | `True` | Tasks re-queued if worker dies |

If a worker pod is killed (OOM, node failure), its in-progress task is
automatically returned to the queue and picked up by another worker.

---

## 3. Celery Beat — Exactly-One Constraint

Celery Beat (the task scheduler) **must run as exactly one instance**.
Running multiple Beat instances will cause duplicate task submissions.

### Current approach: single-replica Deployment

```yaml
# deployment-beat.yaml
spec:
  replicas: 1
  strategy:
    type: Recreate  # Kill old before starting new — prevents overlap
```

### Failure recovery

If the Beat pod fails:

1. Kubernetes automatically restarts it (via the Deployment controller).
2. Beat re-reads the schedule from `celery_app.py` on startup.
3. Missed schedules fire immediately on the next beat tick.
4. The `Recreate` strategy ensures no two Beat instances run simultaneously.

### Monitoring Beat health

```bash
# Check Beat pod status
kubectl -n octowatch get pods -l app.kubernetes.io/component=beat

# Check Beat logs for schedule registration
kubectl -n octowatch logs deploy/octowatch-beat --tail=20
```

### Advanced: leader election (optional)

For environments requiring faster Beat failover, consider using a leader
election sidecar:

```yaml
# Example: celery-beat with leader election via Kubernetes Lease
containers:
  - name: beat
    command: ["celery", "-A", "app.celery_app", "beat", "--loglevel=info"]
    # Only runs when this pod holds the Lease
```

This is not currently implemented in the Helm chart but can be added if
sub-second Beat failover is required.

---

## 4. TimescaleDB High Availability

### Current setup: standalone StatefulSet

OctoWatch deploys TimescaleDB as a single-instance StatefulSet
(`helm/templates/timescaledb.yaml`).  This provides data durability via PVC
but not automatic failover.

### Failover procedure (manual)

If the TimescaleDB pod fails:

1. **Kubernetes restarts it automatically** — the StatefulSet controller
   ensures exactly one pod.  The PVC preserves data across restarts.
2. **If the node fails** — Kubernetes reschedules the pod to another node.
   The PVC must use a zone-redundant storage class (`managed-csi-zrs`) to
   ensure the volume is accessible from any availability zone.
3. **If the PVC is lost** — restore from backup (see
   [backup-restore.md](backup-restore.md)).

### Timeline

| Failure type | Recovery time | Data loss |
|-------------|---------------|-----------|
| Pod crash | ~30 seconds | None (PVC intact) |
| Node failure (ZRS PVC) | ~2-5 minutes | None |
| Node failure (LRS PVC) | Manual restore | Since last backup |
| PVC corruption | Manual restore | Since last backup |

### Recommended: managed database

For production environments requiring < 1 minute failover, use a managed
database service:

- **Azure**: Azure Database for PostgreSQL Flexible Server with Citus/TimescaleDB extension
- **AWS**: Amazon RDS for PostgreSQL with TimescaleDB AMI

Set `postgresql.enabled: false` in Helm values and provide the
`DATABASE_URL` pointing to the managed instance.

---

## 5. Valkey (Redis) High Availability

### Current setup: single instance

OctoWatch uses Valkey as Celery's broker and result backend.

### Failure impact

If Valkey becomes unavailable:

- **Workers** stop receiving tasks — work queues until Valkey recovers.
- **API** continues serving read requests from the database.
- **No data loss** — events are in the database; only task dispatch is delayed.

### Recommended: Valkey Sentinel or Cluster

For production HA:

```yaml
# values-azure.yaml
valkey:
  architecture: replication
  sentinel:
    enabled: true
    replicas: 3
```

Update `VALKEY_URL` to use the Sentinel endpoint:

```
redis+sentinel://:password@sentinel-0:26379,sentinel-1:26379,sentinel-2:26379/mymaster/0
```

---

## 6. Ingress & Load Balancing

The nginx Ingress controller distributes traffic across all healthy API pods:

- **Health checks**: The Ingress uses the API's `/ready` endpoint for
  backend health checks.
- **Rate limiting**: Separate Ingress resources apply per-path rate limits
  (see `helm/templates/ingress.yaml`).
- **TLS termination**: TLS is terminated at the Ingress level.

### Multi-zone deployment

Ensure API pods are spread across availability zones:

```yaml
# Add to API deployment (recommended)
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: topology.kubernetes.io/zone
          labelSelector:
            matchLabels:
              app.kubernetes.io/component: api
```

---

## 7. Monitoring & Alerting for HA

### Key metrics to monitor

| Component | Metric | Alert threshold |
|-----------|--------|-----------------|
| API | Pod count < `minReplicas` | Immediate |
| API | HTTP 5xx rate | > 1% for 5 minutes |
| Workers | Queue depth growing | > 1000 for 15 minutes |
| Beat | Pod not Running | > 2 minutes |
| TimescaleDB | Pod not Ready | > 1 minute |
| Valkey | Connection failures | Any |
| Ingestion | No events ingested | > 30 minutes |

### Health endpoints

```bash
# API health (includes DB and Valkey connectivity)
curl https://<host>/health

# API readiness (ready to serve traffic)
curl https://<host>/ready
```

---

## 8. HA Configuration Checklist

- [ ] API `minReplicas` ≥ 2 in HPA
- [ ] PodDisruptionBudget configured for API
- [ ] Worker replicas ≥ 2 per queue (or KEDA enabled)
- [ ] Beat deployment uses `Recreate` strategy
- [ ] TimescaleDB PVC uses zone-redundant storage (`managed-csi-zrs`)
- [ ] Automated backups enabled and tested
- [ ] Pod anti-affinity configured for zone spread
- [ ] Monitoring and alerting configured for all components
- [ ] `terminationGracePeriodSeconds` set on worker pods (≥ 1800)
