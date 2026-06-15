#!/usr/bin/env bash
# =============================================================================
# deploy-namespace.sh — Deploy OctoWatch to a single customer namespace
#
# Reads all deployment metadata from namespace labels and annotations so that
# NO customer-specific data needs to exist in the repository.
#
# Usage: ./scripts/deploy-namespace.sh <namespace> <image-tag> <helm-chart-path>
# =============================================================================
set -euo pipefail

NS="${1:?Usage: deploy-namespace.sh <namespace> <image-tag> <helm-chart-path>}"
TAG="${2:?Usage: deploy-namespace.sh <namespace> <image-tag> <helm-chart-path>}"
CHART="${3:?Usage: deploy-namespace.sh <namespace> <image-tag> <helm-chart-path>}"
FORCE_REINSTALL="${FORCE_REINSTALL:-false}"

echo "━━━ Deploying to ${NS} (tag=${TAG}) ━━━"

# Read deployment metadata from namespace labels/annotations
SIZE=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.labels.octowatch\.dev/size}')
SIZE="${SIZE:-small}"
CUSTOMER=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.labels.octowatch\.dev/customer}')

# Read infrastructure config from namespace annotations (set by Terraform)
KV_NAME=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.annotations.octowatch\.dev/keyvault-name}')
KV_URI=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.annotations.octowatch\.dev/keyvault-uri}')
WI_CLIENT_ID=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.annotations.octowatch\.dev/workload-identity-id}')
TENANT_ID=$(kubectl get ns "${NS}" -o jsonpath='{.metadata.annotations.octowatch\.dev/tenant-id}')

# Validate required fields
if [ -z "${CUSTOMER}" ]; then
  echo "::error::Namespace ${NS} missing label octowatch.dev/customer"
  exit 1
fi

# Determine image registry from environment or default
REGISTRY="${IMAGE_PREFIX:-ghcr.io/jmassardo}"

# Build Helm set flags
HELM_ARGS=(
  --set-string "global.image.tag=${TAG}"
  --set "global.image.registry=${REGISTRY}"
  --set "ingress.host=${CUSTOMER}.octowatch.dev"
  --set "ingress.tls.secretName=octowatch-wildcard-tls"
  --set "ingress.tls.enabled=true"
  --set "ingress.annotations.cert-manager\\.io/cluster-issuer="
  --set "networkPolicy.enabled=true"
  --set "useExternalSecrets=true"
)

# Add workload identity / Key Vault if annotations are populated
if [ -n "${KV_NAME}" ] && [ -n "${WI_CLIENT_ID}" ]; then
  HELM_ARGS+=(
    --set "workloadIdentity.enabled=true"
    --set "workloadIdentity.clientId=${WI_CLIENT_ID}"
    --set "workloadIdentity.tenantId=${TENANT_ID}"
    --set "keyVault.name=${KV_NAME}"
    --set "keyVault.uri=${KV_URI}"
  )
fi

# Force reinstall if requested (purges broken releases with immutable field conflicts)
if [ "${FORCE_REINSTALL}" = "true" ]; then
  if helm status "${NS}" -n "${NS}" >/dev/null 2>&1; then
    echo "⚠️  Force reinstall: uninstalling existing release ${NS}"
    helm uninstall "${NS}" -n "${NS}" --wait
  fi
  # Clean up orphaned PVCs (they survive helm uninstall due to resource-policy: keep)
  PVCS=$(kubectl get pvc -n "${NS}" -o name 2>/dev/null || true)
  if [ -n "${PVCS}" ]; then
    echo "⚠️  Cleaning up orphaned PVCs:"
    echo "${PVCS}"
    kubectl delete pvc --all -n "${NS}" --wait=false 2>/dev/null || true
  fi
  sleep 5
fi

# Include selfmanaged overlay (imagePullSecrets, registry, static replicas)
VALUES_FILES=(
  -f "${CHART}/values.yaml"
  -f "${CHART}/values-selfmanaged.yaml"
  -f "${CHART}/values-${SIZE}.yaml"
)

# Deploy
if ! helm upgrade --install "${NS}" "${CHART}" \
  -n "${NS}" \
  "${VALUES_FILES[@]}" \
  "${HELM_ARGS[@]}" \
  --timeout 15m \
  --wait; then
  echo "::error::Helm deploy failed for ${NS}. Dumping pod status:"
  kubectl get pods -n "${NS}" -o wide 2>&1 || true
  echo "--- Events (last 5 min) ---"
  kubectl get events -n "${NS}" --sort-by='.lastTimestamp' 2>&1 | tail -30 || true
  echo "--- Logs from non-ready pods ---"
  kubectl get pods -n "${NS}" -o jsonpath='{range .items[?(@.status.containerStatuses[0].ready==false)]}{.metadata.name}{"\n"}{end}' 2>&1 | while read -r pod; do
    [ -z "${pod}" ] && continue
    echo "=== logs: ${pod} (last 50 lines) ==="
    kubectl logs "${pod}" -n "${NS}" --tail=50 2>&1 || true
  done || true
  echo "--- Readiness probe direct test ---"
  API_POD=$(kubectl get pods -n "${NS}" -l app.kubernetes.io/component=api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  if [ -n "${API_POD}" ]; then
    echo "Exec curl /ready on ${API_POD}:"
    kubectl exec "${API_POD}" -n "${NS}" -- curl -s http://localhost:8000/ready 2>&1 || true
    echo ""
    echo "Checking env vars (redacted):"
    kubectl exec "${API_POD}" -n "${NS}" -- env 2>&1 | grep -E "^(DATABASE_URL|VALKEY_URL)" | sed 's/\(.*:\/\/[^:]*:\)[^@]*/\1***/' || true
  fi
  echo "--- Services ---"
  kubectl get svc -n "${NS}" 2>&1 || true
  echo "--- NetworkPolicies ---"
  kubectl get networkpolicies -n "${NS}" 2>&1 || true
  exit 1
fi

echo "✓ ${NS} deployed (customer=${CUSTOMER}, size=${SIZE}, tag=${TAG})"
