#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# repair-octowatch.sh — Diagnose and repair OctoWatch AKS outages
# ─────────────────────────────────────────────────────────────────────────────
#
# Usage:  ./scripts/repair-octowatch.sh [--dry-run]
#
# This script automates the troubleshooting steps for common OctoWatch
# outages on AKS. It checks, in order:
#
#   1. Azure CLI / kubectl prerequisites
#   2. AKS cluster power state
#   3. API server connectivity (authorized IP ranges)
#   4. Node readiness
#   5. Pod health (CrashLoopBackOff, ImagePullBackOff, Pending, etc.)
#   6. Image tag alignment (Helm values vs running pods)
#   7. Database migrations (alembic upgrade head)
#   8. Internal health endpoint
#   9. External ingress reachability
#
# Each step prints a status and, when a problem is found, attempts a fix
# (unless --dry-run is passed).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
RG="rg-octowatch-dev"
CLUSTER="aks-octowatch-dev"
NAMESPACE="octowatch"
EXTERNAL_HOST="octowatch.jmassardo.azure.csa-github.com"
HELM_TAG_FILE="helm/values-image-tag.yaml"
GHCR_PREFIX="ghcr.io/jmassardo"
DEPLOYMENTS=(
  octowatch-api
  octowatch-beat
  octowatch-frontend
  octowatch-worker-baseline
  octowatch-worker-detection
  octowatch-worker-ingestion
  octowatch-worker-notification
  octowatch-worker-sync
)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ── Helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }
fix()   { echo -e "${YELLOW}[FIX]${NC}   $*"; }
dry()   { echo -e "${YELLOW}[DRY-RUN]${NC} Would: $*"; }

run_fix() {
  if $DRY_RUN; then
    dry "$1"
  else
    fix "$1"
    eval "$2"
  fi
}

# ── Step 0: Prerequisites ────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  OctoWatch Repair Script"
echo "═══════════════════════════════════════════════════════"
echo ""

info "Step 0: Checking prerequisites..."

for cmd in az kubectl curl; do
  if ! command -v "$cmd" &>/dev/null; then
    fail "$cmd is not installed"
    exit 1
  fi
done

if ! az account show &>/dev/null; then
  fail "Not logged in to Azure CLI. Run: az login"
  exit 1
fi
ok "Prerequisites OK (az, kubectl, curl available; Azure CLI authenticated)"

# ── Step 1: AKS cluster power state ──────────────────────────────────────────
echo ""
info "Step 1: Checking AKS cluster power state..."

POWER_STATE=$(az aks show -g "$RG" -n "$CLUSTER" --query "powerState.code" -o tsv 2>&1)
PROV_STATE=$(az aks show -g "$RG" -n "$CLUSTER" --query "provisioningState" -o tsv 2>&1)

if [[ "$POWER_STATE" == "Stopped" ]]; then
  fail "Cluster is stopped (powerState=$POWER_STATE)"
  run_fix "Starting AKS cluster..." "az aks start -g $RG -n $CLUSTER && echo 'Cluster started.'"
elif [[ "$POWER_STATE" != "Running" ]]; then
  warn "Unexpected power state: $POWER_STATE (provisioning: $PROV_STATE)"
else
  ok "Cluster power state: $POWER_STATE (provisioning: $PROV_STATE)"
fi

# ── Step 2: API server connectivity / authorized IPs ─────────────────────────
echo ""
info "Step 2: Checking API server connectivity..."

# Refresh credentials first
az aks get-credentials -g "$RG" -n "$CLUSTER" --overwrite-existing &>/dev/null
info "Refreshed kubeconfig"

# Quick connectivity test
if kubectl get nodes --request-timeout=10s &>/dev/null; then
  ok "kubectl can reach the API server"
else
  warn "kubectl cannot reach the API server — checking authorized IP ranges"

  MY_IP=$(curl -s https://ifconfig.me)
  info "My public IP: $MY_IP"

  AUTH_IPS=$(az aks show -g "$RG" -n "$CLUSTER" \
    --query "apiServerAccessProfile.authorizedIpRanges" -o tsv 2>&1 | tr '\n' ',')

  if [[ -n "$AUTH_IPS" ]] && ! echo "$AUTH_IPS" | grep -q "$MY_IP"; then
    fail "IP $MY_IP is NOT in the authorized IP ranges"
    run_fix "Adding $MY_IP/32 to authorized IP ranges" \
      "az aks update -g $RG -n $CLUSTER --api-server-authorized-ip-ranges '${AUTH_IPS}${MY_IP}/32' --no-wait"

    if ! $DRY_RUN; then
      info "Waiting for AKS update to propagate..."
      for i in $(seq 1 20); do
        sleep 15
        STATE=$(az aks show -g "$RG" -n "$CLUSTER" --query "provisioningState" -o tsv 2>&1)
        if [[ "$STATE" == "Succeeded" ]]; then
          ok "AKS update complete"
          break
        fi
        info "  Still updating... ($STATE) [${i}/20]"
      done

      # Re-fetch credentials and retry
      az aks get-credentials -g "$RG" -n "$CLUSTER" --overwrite-existing &>/dev/null
      if kubectl get nodes --request-timeout=15s &>/dev/null; then
        ok "kubectl now reaches the API server"
      else
        fail "Still cannot reach API server after adding IP. Manual investigation needed."
        exit 1
      fi
    fi
  else
    fail "IP is in allowlist but still can't connect. Possible DNS or network issue."
    info "Try: nslookup $(az aks show -g $RG -n $CLUSTER --query fqdn -o tsv)"
    exit 1
  fi
fi

# ── Step 3: Node readiness ───────────────────────────────────────────────────
echo ""
info "Step 3: Checking node readiness..."

NOT_READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -v " Ready " || true)
if [[ -n "$NOT_READY" ]]; then
  fail "Some nodes are not Ready:"
  echo "$NOT_READY"
  warn "Node issues may require Azure portal intervention or nodepool scaling"
else
  NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
  ok "All $NODE_COUNT nodes are Ready"
fi

# ── Step 4: Pod health ───────────────────────────────────────────────────────
echo ""
info "Step 4: Checking pod health in namespace '$NAMESPACE'..."

PROBLEM_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null \
  | grep -Ev "Running|Completed" || true)

if [[ -n "$PROBLEM_PODS" ]]; then
  fail "Problem pods detected:"
  echo "$PROBLEM_PODS"
  echo ""

  # Check for ImagePullBackOff — usually a tag mismatch
  IPB_PODS=$(echo "$PROBLEM_PODS" | grep "ImagePullBackOff\|ErrImagePull" || true)
  if [[ -n "$IPB_PODS" ]]; then
    warn "ImagePullBackOff detected — likely an image tag mismatch (see Step 5)"
  fi

  # Check for CrashLoopBackOff
  CLB_PODS=$(echo "$PROBLEM_PODS" | grep "CrashLoopBackOff" || true)
  if [[ -n "$CLB_PODS" ]]; then
    warn "CrashLoopBackOff pods — checking logs:"
    while read -r pod _; do
      echo "  --- $pod ---"
      kubectl logs -n "$NAMESPACE" "$pod" --tail=20 2>&1 | sed 's/^/    /'
    done <<< "$CLB_PODS"
  fi

  # Check for Pending pods
  PENDING=$(echo "$PROBLEM_PODS" | grep "Pending" || true)
  if [[ -n "$PENDING" ]]; then
    warn "Pending pods — usually a resource constraint. Checking events:"
    while read -r pod _; do
      kubectl describe pod -n "$NAMESPACE" "$pod" 2>/dev/null | grep -A5 "Events:" | sed 's/^/    /'
    done <<< "$PENDING"
  fi
else
  POD_COUNT=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
  ok "All $POD_COUNT pods are Running"
fi

# ── Step 5: Image tag alignment ─────────────────────────────────────────────
echo ""
info "Step 5: Checking image tag alignment..."

if [[ -f "$REPO_ROOT/$HELM_TAG_FILE" ]]; then
  EXPECTED_TAG=$(grep 'tag:' "$REPO_ROOT/$HELM_TAG_FILE" | awk '{print $2}' | tr -d '"')
  info "Expected tag (from $HELM_TAG_FILE): $EXPECTED_TAG"

  MISMATCHED=""
  for deploy in "${DEPLOYMENTS[@]}"; do
    ACTUAL=$(kubectl get deploy "$deploy" -n "$NAMESPACE" \
      -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "NOT_FOUND")
    ACTUAL_TAG="${ACTUAL##*:}"
    if [[ "$ACTUAL" == "NOT_FOUND" ]]; then
      continue  # deployment doesn't exist (e.g., some workers may not be deployed)
    fi
    if [[ "$ACTUAL_TAG" != "$EXPECTED_TAG" ]]; then
      MISMATCHED+="  $deploy: running=$ACTUAL_TAG expected=$EXPECTED_TAG\n"
    fi
  done

  if [[ -n "$MISMATCHED" ]]; then
    warn "Image tag mismatches found:"
    echo -e "$MISMATCHED"

    run_fix "Updating deployment images to tag $EXPECTED_TAG" "
      for deploy in ${DEPLOYMENTS[*]}; do
        # Determine the image name from the deployment name
        if [[ \"\$deploy\" == octowatch-worker-* ]]; then
          IMAGE_NAME=\"octowatch-worker\"
          CONTAINER_NAME=\"\${deploy#octowatch-}\"
        else
          IMAGE_NAME=\"\$deploy\"
          CONTAINER_NAME=\"\${deploy#octowatch-}\"
        fi
        kubectl set image deployment/\$deploy -n $NAMESPACE \
          \$CONTAINER_NAME=$GHCR_PREFIX/\$IMAGE_NAME:$EXPECTED_TAG 2>/dev/null || true
      done
    "

    if ! $DRY_RUN; then
      info "Waiting for rollouts..."
      for deploy in "${DEPLOYMENTS[@]}"; do
        kubectl rollout status deployment/"$deploy" -n "$NAMESPACE" --timeout=120s 2>/dev/null || true
      done
      ok "Rollouts complete"
    fi
  else
    ok "All deployments running expected tag: $EXPECTED_TAG"
  fi
else
  warn "$HELM_TAG_FILE not found — skipping tag check (run from repo root)"
fi

# ── Step 6: Database migrations ─────────────────────────────────────────────
echo ""
info "Step 6: Checking database migrations..."

CURRENT_REV=$(kubectl exec -n "$NAMESPACE" deploy/octowatch-api -- \
  python -c "
from alembic.config import Config
from alembic import command
import io, sys
buf = io.StringIO()
sys.stdout = buf
cfg = Config('alembic.ini')
command.current(cfg)
sys.stdout = sys.__stdout__
out = buf.getvalue()
for line in out.splitlines():
  if line.strip() and not line.startswith('INFO'):
    print(line.strip())
" 2>/dev/null || echo "UNKNOWN")

HEAD_REV=$(kubectl exec -n "$NAMESPACE" deploy/octowatch-api -- \
  python -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
print(script.get_current_head())
" 2>/dev/null || echo "UNKNOWN")

if [[ "$CURRENT_REV" == *"(head)"* ]] || [[ "$CURRENT_REV" == "$HEAD_REV" ]]; then
  ok "Database is at latest migration: $CURRENT_REV"
else
  fail "Database migration mismatch — current: $CURRENT_REV, head: $HEAD_REV"
  run_fix "Running pending migrations (alembic upgrade head)" \
    "kubectl exec -n $NAMESPACE deploy/octowatch-api -- python -c \"
from alembic.config import Config
from alembic import command
cfg = Config('alembic.ini')
command.upgrade(cfg, 'head')
\""

  if ! $DRY_RUN; then
    info "Restarting API and worker pods to pick up schema changes..."
    kubectl rollout restart deployment/octowatch-api -n "$NAMESPACE" 2>/dev/null
    kubectl rollout restart deployment/octowatch-worker-detection -n "$NAMESPACE" 2>/dev/null
    kubectl rollout restart deployment/octowatch-worker-ingestion -n "$NAMESPACE" 2>/dev/null
    kubectl rollout status deployment/octowatch-api -n "$NAMESPACE" --timeout=120s 2>/dev/null
    ok "Migrations applied and pods restarted"
  fi
fi

# ── Step 7: Internal health check ───────────────────────────────────────────
echo ""
info "Step 7: Internal API health check..."

HEALTH=$(kubectl exec -n "$NAMESPACE" deploy/octowatch-api -- \
  curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")

if echo "$HEALTH" | grep -q '"ok"'; then
  ok "Internal health: $HEALTH"
else
  fail "Internal health check failed: $HEALTH"
  warn "Checking API pod logs:"
  kubectl logs -n "$NAMESPACE" deploy/octowatch-api --tail=30 2>&1 | sed 's/^/    /'
fi

# ── Step 8: External ingress check ──────────────────────────────────────────
echo ""
info "Step 8: External ingress check..."

INGRESS_COUNT=$(kubectl get ingress -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
info "Found $INGRESS_COUNT ingress resource(s)"

EXT_RESPONSE=$(curl -sk -o /dev/null -w "%{http_code}" "https://$EXTERNAL_HOST/" 2>/dev/null || echo "000")
if [[ "$EXT_RESPONSE" == "200" ]]; then
  ok "External endpoint $EXTERNAL_HOST returns HTTP $EXT_RESPONSE"
elif [[ "$EXT_RESPONSE" == "000" ]]; then
  fail "Cannot reach $EXTERNAL_HOST (DNS or network issue)"
else
  warn "External endpoint returns HTTP $EXT_RESPONSE (may be expected for some paths)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Repair script complete"
echo "═══════════════════════════════════════════════════════"
echo ""
if $DRY_RUN; then
  info "This was a dry run — no changes were made"
fi
