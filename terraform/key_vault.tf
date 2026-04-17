################################################################################
# OctoWatch — Azure Key Vault
# RBAC-enabled vault stores all application secrets.
# VM identity gets Secrets User; deploying principal gets Secrets Officer.
################################################################################

# Random suffix ensures the Key Vault name is globally unique.
resource "random_string" "kv_suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_key_vault" "main" {
  name                = local.key_vault_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Use Azure RBAC for all data-plane operations (no legacy access policies).
  # Note: renamed from enable_rbac_authorization in azurerm v4.x
  rbac_authorization_enabled = true

  # Soft-delete protects against accidental secret loss.
  soft_delete_retention_days = 7

  # Purge protection prevents permanent deletion during the retention window.
  # Required for production; set to false only if you need to tear down and
  # recreate quickly in dev (update provider feature flag accordingly).
  purge_protection_enabled = true

  tags = local.common_tags
}

# ── RBAC: VM Identity → Secrets User ──────────────────────────────────────────
# Allows the VM to read (get/list) secrets at boot time.

resource "azurerm_role_assignment" "kv_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.vm.principal_id
}

# ── RBAC: Deploying Principal → Secrets Officer ────────────────────────────────
# Allows the Terraform runner (CI/CD service principal or developer) to create,
# update and delete secrets. Required for key_vault_secrets.tf to succeed.

resource "azurerm_role_assignment" "kv_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}
