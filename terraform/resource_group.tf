################################################################################
# OctoWatch — Resource Group
################################################################################

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}-${var.location}"
  location = var.location
  tags     = local.common_tags
}
