################################################################################
# OctoWatch — Customer Module
#
# Provisions all per-customer resources for an isolated OctoWatch instance:
#   - Kubernetes namespace (with ring/size labels for pipeline discovery)
#   - Azure Key Vault (RBAC-enabled, network-restricted)
#   - Workload Identity (managed identity + federated credential)
#   - Cloudflare DNS CNAME record ({customer}.octowatch.dev)
#   - Backup storage container
################################################################################

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.31"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

locals {
  namespace   = "octowatch-${var.customer_slug}"
  name_prefix = "oct-${var.customer_slug}"

  common_tags = merge(
    {
      application = "octowatch"
      customer    = var.customer_slug
      ring        = var.ring
      managed_by  = "terraform"
    },
    var.tags,
  )
}

# ── Kubernetes Namespace ──────────────────────────────────────────────────────
# Labels drive the CI pipeline's ring-based deployment discovery.

resource "kubernetes_namespace" "customer" {
  metadata {
    name = local.namespace

    labels = {
      "octowatch.dev/customer"    = var.customer_slug
      "octowatch.dev/ring"        = var.ring
      "octowatch.dev/size"        = var.size
      "app.kubernetes.io/part-of" = "octowatch"
    }

    annotations = {
      "octowatch.dev/provisioned-by"       = "terraform"
      "octowatch.dev/keyvault-name"        = azurerm_key_vault.customer.name
      "octowatch.dev/keyvault-uri"         = azurerm_key_vault.customer.vault_uri
      "octowatch.dev/workload-identity-id" = azurerm_user_assigned_identity.workload.client_id
      "octowatch.dev/tenant-id"            = data.azurerm_client_config.current.tenant_id
    }
  }
}

# ── Key Vault ─────────────────────────────────────────────────────────────────
# Each customer gets an isolated vault. RBAC mode, network-restricted to AKS.

resource "random_string" "kv_suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_key_vault" "customer" {
  name                          = "kv-${local.name_prefix}-${random_string.kv_suffix.result}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  enable_rbac_authorization     = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 30
  public_network_access_enabled = true

  network_acls {
    bypass                     = "AzureServices"
    default_action             = "Deny"
    virtual_network_subnet_ids = [var.aks_subnet_id]
  }

  tags = local.common_tags
}

# ── Workload Identity ─────────────────────────────────────────────────────────
# Managed identity scoped to this customer's namespace + Key Vault.

resource "azurerm_user_assigned_identity" "workload" {
  name                = "id-${local.name_prefix}-workload"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = local.common_tags
}

resource "azurerm_federated_identity_credential" "workload" {
  name                = "fic-${local.name_prefix}"
  resource_group_name = var.resource_group_name
  parent_id           = azurerm_user_assigned_identity.workload.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = var.aks_oidc_issuer_url
  # Service account name matches Helm's serviceAccount.name default
  subject = "system:serviceaccount:${local.namespace}:${local.namespace}"
}

resource "azurerm_role_assignment" "kv_secrets_officer" {
  scope                = azurerm_key_vault.customer.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

# ── Cloudflare DNS ────────────────────────────────────────────────────────────
# CNAME: {customer}.octowatch.dev → ingress LB

resource "cloudflare_record" "customer" {
  zone_id = var.cloudflare_zone_id
  name    = var.customer_slug
  content = var.ingress_lb_ip
  type    = "A"
  ttl     = 300
  proxied = false
}

# ── Backup Storage Container ─────────────────────────────────────────────────
# Isolated blob container within the shared storage account.

resource "azurerm_storage_container" "backup" {
  name                  = "backup-${var.customer_slug}"
  storage_account_id    = var.backup_storage_account_id
  container_access_type = "private"
}

# ── Data Sources ──────────────────────────────────────────────────────────────

data "azurerm_client_config" "current" {}
