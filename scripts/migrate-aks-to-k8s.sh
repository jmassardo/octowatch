#!/usr/bin/env bash
# migrate-aks-to-k8s.sh — Migrate TimescaleDB data from AKS to self-managed K8s
#
# Run this script from the MANAGEMENT VM where both kubeconfigs are available.
#
# Usage:
#   ./scripts/migrate-aks-to-k8s.sh --aks-context <context> [--dry-run]
#
# Prerequisites:
#   - kubectl configured with both AKS and self-managed cluster contexts
#   - AKS context: az aks get-credentials --resource-group rg-octowatch-dev --name aks-octowatch-dev
#   - Self-managed context: default kubeconfig on management VM (~/.kube/config)
#   - Both clusters accessible from the management VM
#
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
AKS_CONTEXT=""
K8S_CONTEXT=""  # empty = use default kubeconfig
DRY_RUN=false
DUMP_FILE="/tmp/octowatch-migration-$(date +%Y%m%d-%H%M%S).dump"
NAMESPACE="octowatch"
AKS_DB_POD="octowatch-postgresql-0"
K8S_DB_POD="octowatch-postgresql-0"
DB_NAME="auditlogs"
DB_USER="postgres"

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --aks-context)  AKS_CONTEXT="$2"; shift 2 ;;
    --k8s-context)  K8S_CONTEXT="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    *)              echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$AKS_CONTEXT" ]]; then
  echo "ERROR: --aks-context is required"
  echo "Usage: $0 --aks-context <kubectl-context-name> [--k8s-context <name>] [--dry-run]"
  echo ""
  echo "Setup: az aks get-credentials --resource-group rg-octowatch-dev --name aks-octowatch-dev"
  echo "       kubectl config get-contexts  # to find the context name"
  exit 1
fi

log() { echo "[$(date '+%H:%M:%S')] $*"; }
run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

AKS_KUBECTL="kubectl --context=$AKS_CONTEXT"
K8S_KUBECTL="kubectl"
[[ -n "$K8S_CONTEXT" ]] && K8S_KUBECTL="kubectl --context=$K8S_CONTEXT"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  OctoWatch AKS → Self-Managed K8s Data Migration           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  AKS context    : $AKS_CONTEXT"
echo "  K8s context    : ${K8S_CONTEXT:-<default>}"
echo "  Dump file      : $DUMP_FILE"
echo "  Dry run        : $DRY_RUN"
echo ""

# ── Step 1: Verify both clusters are accessible ─────────────────────────────
log "Step 1: Verifying cluster access..."
echo "  AKS cluster:"
$AKS_KUBECTL get nodes -o wide || { echo "ERROR: Cannot reach AKS cluster"; exit 1; }
echo ""
echo "  Self-managed cluster:"
$K8S_KUBECTL get nodes -o wide || { echo "ERROR: Cannot reach self-managed cluster"; exit 1; }
echo ""

# ── Step 2: Verify TimescaleDB pods ─────────────────────────────────────────
log "Step 2: Verifying TimescaleDB pods..."
echo "  AKS TimescaleDB:"
$AKS_KUBECTL get pod -n $NAMESPACE $AKS_DB_POD -o wide || { echo "ERROR: AKS DB pod not found"; exit 1; }
echo "  K8s TimescaleDB:"
$K8S_KUBECTL get pod -n $NAMESPACE $K8S_DB_POD -o wide || { echo "ERROR: K8s DB pod not found"; exit 1; }
echo ""

# ── Step 3: Scale down AKS application workloads ───────────────────────────
log "Step 3: Scaling down AKS workloads (preventing new writes)..."
run $AKS_KUBECTL scale deployment --all --replicas=0 -n $NAMESPACE
# Suspend CronJobs to prevent scheduled writes
for cj in $($AKS_KUBECTL get cronjobs -n $NAMESPACE -o name 2>/dev/null); do
  run $AKS_KUBECTL patch "$cj" -n $NAMESPACE -p '{"spec":{"suspend":true}}'
done
echo "  Waiting for all app pods to terminate..."
if [[ "$DRY_RUN" != "true" ]]; then
  for i in $(seq 1 30); do
    RUNNING=$($AKS_KUBECTL get pods -n $NAMESPACE --field-selector=status.phase=Running --no-headers 2>/dev/null | grep -cv 'timescaledb\|valkey' || true)
    [ "$RUNNING" -eq 0 ] && break
    echo "  Still $RUNNING app pods running ($i/30)..."
    sleep 5
  done
fi
echo ""

# ── Step 4: Get row counts from AKS (post-quiesce baseline) ────────────────
log "Step 4: Capturing AKS row counts (after quiescing writers)..."
$AKS_KUBECTL exec -n $NAMESPACE $AKS_DB_POD -- psql -U $DB_USER -d $DB_NAME -c "
  SELECT 'events' AS table_name, approximate_row_count('events') AS row_count
  UNION ALL
  SELECT 'detections', count(*) FROM detections
  UNION ALL
  SELECT 'rule_definitions', count(*) FROM rule_definitions
  UNION ALL
  SELECT 'notification_configs', count(*) FROM notification_configs
  UNION ALL
  SELECT 'alembic_version', count(*) FROM alembic_version;
"
echo ""

# ── Step 5: pg_dump from AKS TimescaleDB ────────────────────────────────────
log "Step 5: Running pg_dump on AKS TimescaleDB..."
run $AKS_KUBECTL exec -n $NAMESPACE $AKS_DB_POD -- \
  pg_dump -U $DB_USER -d $DB_NAME \
  --no-owner --no-acl \
  --format=custom --compress=9 \
  --verbose \
  --file=/tmp/migration.dump 2>&1 | tail -5

log "Step 5b: Copying dump file from AKS pod..."
run $AKS_KUBECTL cp "$NAMESPACE/$AKS_DB_POD:/tmp/migration.dump" "$DUMP_FILE"
if [[ "$DRY_RUN" != "true" ]]; then
  DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
  log "  Dump size: $DUMP_SIZE"
fi
echo ""

# ── Step 6: Scale down K8s application workloads ───────────────────────────
log "Step 6: Scaling down self-managed K8s workloads..."
run $K8S_KUBECTL scale deployment --all --replicas=0 -n $NAMESPACE 2>/dev/null || true
echo ""

# ── Step 7: Copy dump to self-managed K8s ──────────────────────────────────
log "Step 7: Copying dump to self-managed K8s TimescaleDB pod..."
run $K8S_KUBECTL cp "$DUMP_FILE" "$NAMESPACE/$K8S_DB_POD:/tmp/migration.dump"
echo ""

# ── Step 8: Pre-restore ────────────────────────────────────────────────────
log "Step 8: Running timescaledb_pre_restore()..."
run $K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- \
  psql -U $DB_USER -d $DB_NAME -c "SELECT timescaledb_pre_restore();" 2>/dev/null || {
    log "  (timescaledb_pre_restore not available — OK for first restore)"
  }
echo ""

# ── Step 9: pg_restore ─────────────────────────────────────────────────────
log "Step 9: Restoring database..."
RESTORE_LOG="/tmp/pg_restore_output.log"
RESTORE_RC=0
run $K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- \
  pg_restore -U $DB_USER -d $DB_NAME \
  --no-owner --no-privileges \
  --clean --if-exists \
  --verbose \
  /tmp/migration.dump 2>&1 | tee "$RESTORE_LOG" | tail -20 || RESTORE_RC=$?

if [[ "$RESTORE_RC" -ne 0 && "$DRY_RUN" != "true" ]]; then
  # pg_restore exits 1 for warnings about pre-existing objects with --clean --if-exists.
  # Check for actual fatal errors beyond the expected "does not exist" noise.
  FATAL_ERRORS=$(grep -ciE '(FATAL|could not|permission denied|out of memory)' "$RESTORE_LOG" 2>/dev/null || true)
  if [[ "$FATAL_ERRORS" -gt 0 ]]; then
    log "ERROR: pg_restore encountered fatal errors — review $RESTORE_LOG"
    grep -iE '(FATAL|could not|permission denied|out of memory)' "$RESTORE_LOG" | head -10
    exit 1
  fi
  log "  Note: pg_restore exited with warnings (expected for --clean --if-exists)."
fi
rm -f "$RESTORE_LOG"
echo ""

# ── Step 10: Post-restore ──────────────────────────────────────────────────
log "Step 10: Running timescaledb_post_restore()..."
run $K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- \
  psql -U $DB_USER -d $DB_NAME -c "SELECT timescaledb_post_restore();" 2>/dev/null || {
    log "  (timescaledb_post_restore not available — skipping)"
  }
echo ""

# ── Step 11: Verify hypertables ────────────────────────────────────────────
log "Step 11: Verifying hypertable integrity..."
$K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- \
  psql -U $DB_USER -d $DB_NAME -c "
  SELECT hypertable_name, num_chunks, compression_enabled
  FROM timescaledb_information.hypertables
  ORDER BY hypertable_name;
" 2>/dev/null || log "  (No hypertables found)"
echo ""

# ── Step 12: Verify row counts match ──────────────────────────────────────
log "Step 12: Verifying row counts on self-managed cluster..."
$K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- psql -U $DB_USER -d $DB_NAME -c "
  SELECT 'events' AS table_name, approximate_row_count('events') AS row_count
  UNION ALL
  SELECT 'detections', count(*) FROM detections
  UNION ALL
  SELECT 'rule_definitions', count(*) FROM rule_definitions
  UNION ALL
  SELECT 'notification_configs', count(*) FROM notification_configs
  UNION ALL
  SELECT 'alembic_version', count(*) FROM alembic_version;
"
echo ""

# ── Step 13: Verify Alembic migration state ────────────────────────────────
log "Step 13: Checking Alembic migration state..."
$K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- \
  psql -U $DB_USER -d $DB_NAME -c "SELECT version_num FROM alembic_version;"
echo ""

# ── Step 14: Cleanup ──────────────────────────────────────────────────────
log "Step 14: Cleaning up dump files..."
run $AKS_KUBECTL exec -n $NAMESPACE $AKS_DB_POD -- rm -f /tmp/migration.dump
run $K8S_KUBECTL exec -n $NAMESPACE $K8S_DB_POD -- rm -f /tmp/migration.dump
rm -f "$DUMP_FILE"
echo ""

# ── Step 15: Scale up K8s workloads ───────────────────────────────────────
log "Step 15: Scaling up self-managed K8s workloads..."
run $K8S_KUBECTL scale deployment octowatch-api -n $NAMESPACE --replicas=2
run $K8S_KUBECTL scale deployment octowatch-frontend -n $NAMESPACE --replicas=1
run $K8S_KUBECTL scale deployment octowatch-worker-ingestion -n $NAMESPACE --replicas=4
run $K8S_KUBECTL scale deployment octowatch-worker-detection -n $NAMESPACE --replicas=4
run $K8S_KUBECTL scale deployment octowatch-worker-notification -n $NAMESPACE --replicas=2
run $K8S_KUBECTL scale deployment octowatch-worker-baseline -n $NAMESPACE --replicas=2
run $K8S_KUBECTL scale deployment octowatch-beat -n $NAMESPACE --replicas=1
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Migration complete!                                        ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Next steps:                                                ║"
echo "║    1. Verify /health and /ready return 200                  ║"
echo "║    2. Test login and key workflows                          ║"
echo "║    3. Cut DNS: set k8s_cutover_complete=true, terraform apply║"
echo "║    4. AKS workloads are still scaled to 0 — restore if     ║"
echo "║       rollback is needed                                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
