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
  --set "global.image.tag=${TAG}"
  --set "global.image.registry=${REGISTRY}"
  --set "ingress.host=${CUSTOMER}.octowatch.dev"
  --set "ingress.tls.secretName=octowatch-wildcard-tls"
  --set "ingress.tls.enabled=true"
  --set "ingress.annotations.cert-manager\\.io/cluster-issuer="
  --set "networkPolicy.enabled=true"
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

# Include selfmanaged overlay (imagePullSecrets, registry, static replicas)
VALUES_FILES=(
  -f "${CHART}/values.yaml"
  -f "${CHART}/values-selfmanaged.yaml"
  -f "${CHART}/values-${SIZE}.yaml"
)

# Deploy
helm upgrade --install "${NS}" "${CHART}" \
  -n "${NS}" \
  "${VALUES_FILES[@]}" \
  "${HELM_ARGS[@]}" \
  --timeout 8m \
  --wait

echo "✓ ${NS} deployed (customer=${CUSTOMER}, size=${SIZE}, tag=${TAG})"
