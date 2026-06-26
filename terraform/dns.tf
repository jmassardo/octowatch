################################################################################
# OctoWatch — Azure DNS Integration
#
# Creates DNS records in an existing Azure DNS zone.
# Set dns_zone_name and dns_zone_resource_group to enable.
# Leave both empty to skip DNS record creation.
################################################################################

data "azurerm_dns_zone" "existing" {
  count               = var.dns_zone_name != "" ? 1 : 0
  name                = var.dns_zone_name
  resource_group_name = var.dns_zone_resource_group
}

# ── Self-Managed K8s Cluster DNS Record ───────────────────────────────────────

resource "azurerm_dns_a_record" "octowatch_k8s" {
  count               = var.dns_zone_name != "" && var.k8s_cutover_complete ? 1 : 0
  name                = var.dns_record_name
  zone_name           = data.azurerm_dns_zone.existing[0].name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = var.dns_ttl
  records             = [azurerm_public_ip.k8s_lb.ip_address]
  tags                = local.common_tags
}
