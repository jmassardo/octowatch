################################################################################
# OctoWatch — Azure Key Vault
# NOTE: The Key Vault (kv-oct-dev-i6iv6t) was created in a previous apply run
# with rbac_authorization_enabled=true and is no longer managed by Terraform.
# The CSA subscription Contributor role cannot change the permission model.
# Secrets are now baked into cloud-init userdata at provision time instead.
# A user with Owner/User-Access-Administrator can manage the KV manually.
################################################################################

# Random suffix kept to avoid destroying the existing random resource in state.
resource "random_string" "kv_suffix" {
  length  = 6
  special = false
  upper   = false
}

# Key Vault resource intentionally removed from management.
# The vault kv-oct-dev-i6iv6t exists in Azure but Terraform no longer manages it.
# To re-enable: an Owner must assign Key Vault Secrets Officer to the deploying
# principal, then the azurerm_key_vault resource and key_vault_secrets.tf can
# be restored.

# ── Storage RBAC removed ───────────────────────────────────────────────────────
# Contributor role lacks Microsoft.Authorization/roleAssignments/write.
# VM backup uploads use the storage account key instead.
