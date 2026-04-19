################################################################################
# OctoWatch — Storage Account
# Used for: PostgreSQL backups (pg-backups container) and VM boot diagnostics.
################################################################################

# Random suffix ensures the storage account name is globally unique.
resource "random_string" "storage_suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_storage_account" "main" {
  # Storage account names: 3-24 chars, lowercase alphanumeric only, globally unique.
  name                = "stoctowatch${var.environment}${random_string.storage_suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Enforce TLS 1.2+ on all data-plane connections.
  min_tls_version = "TLS1_2"

  # Reject plain HTTP — all connections must use HTTPS.
  https_traffic_only_enabled = true

  # Required by CSA subscription policy GH.15.06 — no public blob access.
  allow_nested_items_to_be_public = false

  tags = local.common_tags
}

# ── PostgreSQL Backup Container ────────────────────────────────────────────────
# The backup-azure.sh script (run from cron) uploads pg_dump output here.
# Access is via managed identity (az storage blob upload --auth-mode login).

resource "azurerm_storage_container" "pg_backups" {
  name                  = "pg-backups"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# ── RBAC: VM Identity → Storage Blob Data Contributor ─────────────────────────
# Required for the VM to upload backups using managed identity auth.

# ── Storage RBAC removed ───────────────────────────────────────────────────────
# Contributor role does not include Microsoft.Authorization/roleAssignments/write.
# VM backup uploads use the storage account connection string from Key Vault.
