# Customer Onboarding Guide

This document describes how to provision a new OctoWatch customer instance on
the shared **self-managed Kubernetes cluster**.

---

## Prerequisites

- Terraform >= 1.7 with access to Azure, Kubernetes, and Cloudflare providers
- `kubectl` access to the OctoWatch cluster **from the management VM**
- Cloudflare API token with DNS edit permissions for `octowatch.dev`
- The customer's GitHub Enterprise slug and a registered GitHub App

> The management VM is the canonical admin entry point for the shared cluster.
> Run `kubectl` and Helm commands there unless you have a separately managed
> kubeconfig with the same permissions.

---

## Architecture Overview

Each customer gets:

- A dedicated Kubernetes namespace (`octowatch-{slug}`)
- An isolated Azure Key Vault
- A dedicated workload identity / federated credential mapping
- A DNS record (`{slug}.octowatch.dev`)
- A backup storage container
- Full NetworkPolicy isolation from other customers

---

## Step 1: Provision Infrastructure (Terraform)

Add a module call in your Terraform configuration (outside this repo — customer
data stays out of source control):

```hcl
module "customer_acme" {
  source = "git::https://github.com/jmassardo/octowatch.git//terraform/modules/customer"

  customer_slug               = "acme"
  ring                        = "prod"      # test | preview | prod
  size                        = "small"     # small | medium | large
  resource_group_name         = azurerm_resource_group.main.name
  location                    = "eastus2"

  # These input names are legacy compatibility shims from the AKS era.
  # For the self-managed cluster, point them at the kubeadm cluster's
  # service-account issuer URL and cluster subnet.
  aks_oidc_issuer_url         = "<self-managed cluster service-account issuer URL>"
  aks_subnet_id               = azurerm_subnet.k8s_cluster.id

  cloudflare_zone_id          = var.cloudflare_zone_id
  ingress_lb_ip               = azurerm_public_ip.k8s_lb.ip_address
  backup_storage_account_id   = azurerm_storage_account.backups.id
  backup_storage_account_name = azurerm_storage_account.backups.name
}
```

Then apply:

```bash
terraform plan -target=module.customer_acme
terraform apply -target=module.customer_acme
```

---

## Step 2: Populate Key Vault Secrets

After Terraform creates the Key Vault, populate the required secrets:

```bash
VAULT_NAME=$(terraform output -raw -module=customer_acme key_vault_name)

az keyvault secret set --vault-name "$VAULT_NAME" --name "database-url"   --value "postgresql+asyncpg://app_rw:PASSWORD@octowatch-acme-postgresql.octowatch-acme.svc.cluster.local:5432/auditlogs"

az keyvault secret set --vault-name "$VAULT_NAME" --name "valkey-url"   --value "redis://:PASSWORD@octowatch-acme-valkey-master.octowatch-acme.svc.cluster.local:6379/0"

az keyvault secret set --vault-name "$VAULT_NAME" --name "secret-key"   --value "$(openssl rand -hex 32)"

az keyvault secret set --vault-name "$VAULT_NAME" --name "github-app-id"   --value "123456"

az keyvault secret set --vault-name "$VAULT_NAME" --name "github-app-private-key"   --value @path/to/private-key.pem

az keyvault secret set --vault-name "$VAULT_NAME" --name "github-webhook-secret"   --value "$(openssl rand -hex 20)"

az keyvault secret set --vault-name "$VAULT_NAME" --name "hec-token"   --value "$(openssl rand -hex 32)"
```

---

## Step 3: Verify DNS

The Terraform module creates a DNS A record. Verify propagation:

```bash
dig +short acme.octowatch.dev
```

It should resolve to the shared ingress load balancer IP.

---

## Step 4: Deploy

The next CI pipeline run can deploy the namespace automatically. To deploy
manually, run from the **management VM**:

```bash
kubectl config current-context
kubectl get ns octowatch-acme

helm upgrade --install octowatch-acme ./helm   -n octowatch-acme   -f helm/values.yaml   -f helm/values-selfmanaged.yaml   -f helm/values-small.yaml   --set global.image.tag="latest"   --set global.image.registry="ghcr.io/jmassardo"   --set ingress.host="acme.octowatch.dev"   --set ingress.tls.secretName="octowatch-wildcard-tls"   --set networkPolicy.enabled=true   --set workloadIdentity.enabled=true   --set workloadIdentity.clientId="$(terraform output -raw -module=customer_acme workload_identity_client_id)"   --set workloadIdentity.tenantId="$(terraform output -raw -module=customer_acme workload_identity_tenant_id)"   --set keyVault.name="$(terraform output -raw -module=customer_acme key_vault_name)"   --set keyVault.uri="$(terraform output -raw -module=customer_acme key_vault_uri)"   --timeout 5m --wait
```

---

## Step 5: Post-Deploy Verification

Run from the management VM:

```bash
kubectl get pods -n octowatch-acme

kubectl run curl-test --image=curlimages/curl:8.7.1 --rm -i --restart=Never   -n octowatch-acme -- curl -sf http://octowatch-acme-api:8000/health

curl -sf https://acme.octowatch.dev/health
```

---

## Day-2 Operations

### Scaling a Customer

```bash
kubectl label ns octowatch-acme octowatch.dev/size=medium --overwrite
```

### Promoting Between Rings

```bash
kubectl label ns octowatch-acme octowatch.dev/ring=prod --overwrite
```

### Removing a Customer

1. `helm uninstall octowatch-acme -n octowatch-acme`
2. `kubectl delete ns octowatch-acme`
3. `terraform destroy -target=module.customer_acme`

---

## Security Notes

- NetworkPolicies enforce full namespace isolation
- Each customer's Key Vault is network-restricted to the self-managed cluster subnet
- Workload identities are scoped to the customer's namespace and vault
- The wildcard TLS certificate is shared only at the ingress layer
- Cross-namespace traffic is constrained by egress and ingress policies
