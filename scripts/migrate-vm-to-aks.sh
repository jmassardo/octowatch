#!/usr/bin/env bash
# migrate-vm-to-aks.sh — Migrate TimescaleDB data from Docker Compose VM to AKS
# Usage: ./scripts/migrate-vm-to-aks.sh [--vm-ip <IP>] [--ssh-key <path>] [--dry-run]
# 
# Prerequisites:
#   - kubectl configured for the AKS cluster (terraform output -raw aks_kube_config > ~/.kube/config)
#   - SSH access to the VM (ssh-key path, default: ~/.ssh/id_rsa)
#   - pg_dump installed on the VM (part of timescaledb docker image)
#
# The migration:
#   1. Waits for TimescaleDB pod to be ready in AKS
#   2. Creates a pg_dump from the VM via Docker exec
#   3. Copies the dump file locally
#   4. Restores into the AKS TimescaleDB pod with timescaledb_pre/post_restore()
#
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
VM_IP=""
SSH_KEY="${HOME}/.ssh/id_rsa"
SSH_USER="octowatch"
DRY_RUN=false
DUMP_FILE="${HOME}/octowatch-migration-$(date +%Y%m%d-%H%M%S).dump"
NAMESPACE="octowatch"
POSTGRES_CONTAINER="octowatch-postgresql-0"  # Bitnami statefulset pod name
DB_NAME="auditlogs"
DB_USER="postgres"  # Use superuser for restore (has TimescaleDB extension rights)

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vm-ip)     VM_IP="$2"; shift 2 ;;
    --ssh-key)   SSH_KEY="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=true; shift ;;
    *)           echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$VM_IP" ]]; then
  echo "ERROR: --vm-ip is required"
  echo "Usage: $0 --vm-ip <VM_PUBLIC_IP> [--ssh-key <path>] [--dry-run]"
  echo ""
  echo "Get VM IP: terraform output -raw vm_public_ip"
  exit 1
fi

log() { echo "[$(date '+%H:%M:%S')] $*"; }
run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    eval "$@"
  fi
}

# ── Step 1: Verify AKS kubectl access ─────────────────────────────────────────
log "Verifying kubectl access to AKS..."
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || {
  echo "ERROR: Cannot access namespace $NAMESPACE in AKS."
  echo "Run: terraform output -raw aks_kube_config > ~/.kube/config"
  exit 1
}

# ── Step 2: Wait for TimescaleDB pod ─────────────────────────────────────────
log "Waiting for TimescaleDB pod to be ready..."
kubectl wait pod "$POSTGRES_CONTAINER" \
  --namespace="$NAMESPACE" \
  --for=condition=Ready \
  --timeout=300s

# ── Step 3: Dump from VM ──────────────────────────────────────────────────────
log "Creating pg_dump on VM ($VM_IP)..."
REMOTE_DUMP="/home/${SSH_USER}/octowatch-dump-$(date +%Y%m%d-%H%M%S).dump"

# Run pg_dump inside the running timescaledb container on the VM
run ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=30 "${SSH_USER}@${VM_IP}" \
  "docker exec \$(docker ps --filter name=db --format '{{.Names}}' | head -1) \
   pg_dump -U postgres auditlogs \
   --no-owner --no-privileges --no-tablespaces \
   --format=custom --compress=9 --file='$REMOTE_DUMP'"

# ── Step 4: Copy dump file locally ─────────────────────────────────────────────
log "Copying dump file from VM to local..."
run scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${VM_IP}:${REMOTE_DUMP}" "$DUMP_FILE"
log "Dump file: $DUMP_FILE ($(du -sh "$DUMP_FILE" 2>/dev/null | cut -f1 || echo 'dry-run'))"

# ── Step 5: Copy dump into AKS pod ────────────────────────────────────────────
log "Copying dump into AKS TimescaleDB pod..."
run kubectl cp "$DUMP_FILE" "${NAMESPACE}/${POSTGRES_CONTAINER}:/tmp/migration.dump"

# ── Step 6: Restore with TimescaleDB pre/post restore ────────────────────────
log "Restoring database (this may take several minutes)..."

RESTORE_CMD=$(cat <<'PSQL'
set -euo pipefail

# Drop and recreate target database
psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'auditlogs' AND pid <> pg_backend_pid();"
psql -U postgres -c "DROP DATABASE IF EXISTS auditlogs;"
psql -U postgres -c "CREATE DATABASE auditlogs OWNER app_rw;"

# Enable TimescaleDB in the new database
psql -U postgres auditlogs -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

# Call pre-restore hook (disables TimescaleDB background workers during restore)
psql -U postgres auditlogs -c "SELECT timescaledb_pre_restore();"

# Restore the dump
pg_restore -U postgres -d auditlogs --no-owner --no-privileges \
  --format=custom --exit-on-error /tmp/migration.dump

# Call post-restore hook (re-enables background workers, revalidates chunks)
psql -U postgres auditlogs -c "SELECT timescaledb_post_restore();"

# Grant permissions to app user
psql -U postgres auditlogs -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO app_rw;"
psql -U postgres auditlogs -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO app_rw;"
psql -U postgres auditlogs -c "GRANT USAGE ON SCHEMA public TO app_rw;"

echo "Restore completed successfully."
PSQL
)

run kubectl exec -n "$NAMESPACE" "$POSTGRES_CONTAINER" -- bash -c "$RESTORE_CMD"

# ── Step 7: Cleanup ─────────────────────────────────────────────────────────
log "Cleaning up dump files..."
run kubectl exec -n "$NAMESPACE" "$POSTGRES_CONTAINER" -- rm -f /tmp/migration.dump
run ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${SSH_USER}@${VM_IP}" "rm -f $REMOTE_DUMP"
[[ "$DRY_RUN" == "false" ]] && rm -f "$DUMP_FILE"

log "Migration completed successfully!"
log ""
log "Next steps:"
log "  1. Validate the AKS deployment: kubectl get pods -n $NAMESPACE"
log "  2. Check API health: kubectl port-forward -n $NAMESPACE svc/octowatch-api 8000:8000"
log "  3. When ready for DNS cutover, set in terraform.tfvars:"
log "       aks_cutover_complete = true"
log "       aks_ingress_lb_ip    = \$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
log "       aca_cutover_complete = true"
log "     Then run: terraform apply"
