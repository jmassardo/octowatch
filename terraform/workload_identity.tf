################################################################################
# OctoWatch — Workload Identity for AKS → Key Vault Access
#
# Creates a dedicated managed identity for the OctoWatch application pods
# running in AKS, with a federated credential linking the Kubernetes service
# account to the Azure identity via OIDC (Workload Identity).
#
# This enables pods annotated with azure.workload.identity/use=true to
# authenticate to Azure Key Vault without stored credentials.
################################################################################

# ── Managed Identity for AKS Workloads ────────────────────────────────────────

resource "azurerm_user_assigned_identity" "aks_workload" {
  name                = "id-${local.name_prefix}-aks-workload"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}

# ── Federated Identity Credential ─────────────────────────────────────────────
# Links the Kubernetes service account (octowatch namespace) to the Azure
# managed identity via the AKS cluster's OIDC issuer URL.

resource "azurerm_federated_identity_credential" "aks_workload" {
  name                = "fic-${local.name_prefix}-aks"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.aks_workload.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:octowatch:octowatch"
}

# ── Key Vault Secrets Officer Role Assignment ─────────────────────────────────
# Grants the workload identity full read/write access to secrets in the
# Key Vault. Uses RBAC (not access policies) since the KV was created with
# enable_rbac_authorization = true.

resource "azurerm_role_assignment" "kv_secrets_officer" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${azurerm_resource_group.main.name}/providers/Microsoft.KeyVault/vaults/${local.key_vault_name}"
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azurerm_user_assigned_identity.aks_workload.principal_id
}

# ── Data source for current subscription ──────────────────────────────────────

data "azurerm_client_config" "current" {}
