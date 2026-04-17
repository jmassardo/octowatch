################################################################################
# OctoWatch — User-Assigned Managed Identity
# The VM uses this identity to authenticate to Key Vault (no stored credentials).
################################################################################

resource "azurerm_user_assigned_identity" "vm" {
  name                = "id-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}
