# Customer Onboarding Guide

This document describes how to provision a new OctoWatch customer instance on the shared multi-tenant cluster.

## Prerequisites

- Terraform >= 1.7 with access to Azure, Kubernetes, and Cloudflare providers
- `kubectl` configured for the OctoWatch AKS cluster
- Cloudflare API token with DNS edit permissions for `octowatch.dev`
- The customer's GitHub Enterprise slug and a registered GitHub App

## Architecture Overview

Each customer gets:
- A dedicated Kubernetes namespace (`octowatch-{slug}`)
- An isolated Azure Key Vault
- A dedicated workload identity (federated via OIDC)
- A DNS record (`{slug}.octowatch.dev`)
- A backup storage container
- Full NetworkPolicy isolation from other customers

## Step 1: Provision Infrastructure (Terraform)

Add a module call in your Terraform configuration (outside this repo — customer data stays out of source control):

```hcl
module "customer_acme" {
  source = "git::https://github.com/jmassardo/octowatch.git//terraform/modules/customer"

  customer_slug               = "acme"
  ring                        = "prod"      # test | preview | prod
  size                        = "small"     # small | medium | large
  resource_group_name         = azurerm_resource_group.main.name
  location                    = "eastus2"
  aks_oidc_issuer_url         = azurerm_kubernetes_cluster.main.oidc_issuer_url
  aks_subnet_id               = azurerm_subnet.aks.id
  cloudflare_zone_id          = var.cloudflare_zone_id
  ingress_lb_ip               = data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress[0].ip
  backup_storage_account_id   = azurerm_storage_account.backups.id
  backup_storage_account_name = azurerm_storage_account.backups.name
}
```

Then apply:

```bash
terraform plan -target=module.customer_acme
terraform apply -target=module.customer_acme
```

## Step 2: Populate Key Vault Secrets

After Terraform creates the Key Vault, populate the required secrets:

```bash
VAULT_NAME=$(terraform output -raw -module=customer_acme key_vault_name)

# Infrastructure secrets
az keyvault secret set --vault-name "$VAULT_NAME" --name "database-url" \
  --value "postgresql+asyncpg://app_rw:PASSWORD@octowatch-acme-postgresql.octowatch-acme.svc.cluster.local:5432/auditlogs"

az keyvault secret set --vault-name "$VAULT_NAME" --name "valkey-url" \
  --value "redis://:PASSWORD@octowatch-acme-valkey-master.octowatch-acme.svc.cluster.local:6379/0"

az keyvault secret set --vault-name "$VAULT_NAME" --name "secret-key" \
  --value "$(openssl rand -hex 32)"

# GitHub App secrets (provided by customer or created during app registration)
az keyvault secret set --vault-name "$VAULT_NAME" --name "github-app-id" \
  --value "123456"

az keyvault secret set --vault-name "$VAULT_NAME" --name "github-app-private-key" \
  --value @path/to/private-key.pem

az keyvault secret set --vault-name "$VAULT_NAME" --name "github-webhook-secret" \
  --value "$(openssl rand -hex 20)"

az keyvault secret set --vault-name "$VAULT_NAME" --name "hec-token" \
  --value "$(openssl rand -hex 32)"
```

## Step 3: Verify DNS

The Terraform module creates a DNS A record. Verify propagation:

```bash
dig +short acme.octowatch.dev
# Should return the ingress LB IP
```

## Step 4: Deploy

The next CI pipeline run will automatically discover the new namespace via its `octowatch.dev/ring` label and deploy. To trigger immediately:

1. Go to **Actions → Deploy (Multi-Tenant) → Run workflow**
2. Select the appropriate ring or leave blank for full rollout

Or deploy manually:

```bash
helm upgrade --install octowatch-acme ./helm \
  -n octowatch-acme \
  -f helm/values.yaml \
  -f helm/values-small.yaml \
  --set global.image.tag="latest" \
  --set global.image.registry="ghcr.io/jmassardo" \
  --set ingress.host="acme.octowatch.dev" \
  --set ingress.tls.secretName="octowatch-wildcard-tls" \
  --set networkPolicy.enabled=true \
  --set workloadIdentity.enabled=true \
  --set workloadIdentity.clientId="$(terraform output -raw -module=customer_acme workload_identity_client_id)" \
  --set workloadIdentity.tenantId="$(terraform output -raw -module=customer_acme workload_identity_tenant_id)" \
  --set keyVault.name="$(terraform output -raw -module=customer_acme key_vault_name)" \
  --set keyVault.uri="$(terraform output -raw -module=customer_acme key_vault_uri)" \
  --timeout 5m --wait
```

## Step 5: Post-Deploy Verification

```bash
# Check pods are running
kubectl get pods -n octowatch-acme

# Verify health endpoint
kubectl run curl-test --image=curlimages/curl:8.7.1 --rm -i --restart=Never \
  -n octowatch-acme -- curl -sf http://octowatch-acme-api:8000/health

# Verify external access
curl -sf https://acme.octowatch.dev/health
```

## Day-2 Operations

### Scaling a Customer

Change the size label — the next deploy picks up the new values file:

```bash
kubectl label ns octowatch-acme octowatch.dev/size=medium --overwrite
# Trigger deploy or wait for next pipeline run
```

### Promoting Between Rings

```bash
kubectl label ns octowatch-acme octowatch.dev/ring=prod --overwrite
```

### Removing a Customer

1. Uninstall the Helm release: `helm uninstall octowatch-acme -n octowatch-acme`
2. Delete the namespace: `kubectl delete ns octowatch-acme`
3. Run `terraform destroy -target=module.customer_acme`

## Security Notes

- NetworkPolicies enforce full namespace isolation (default-deny + explicit allow)
- Each customer's Key Vault is network-restricted to the AKS subnet
- Workload identities are scoped — a customer's pods can only access their own vault
- The wildcard TLS cert is shared but served by the ingress controller (not in customer namespaces)
- Cross-namespace traffic (RFC1918) is blocked by egress NetworkPolicies
