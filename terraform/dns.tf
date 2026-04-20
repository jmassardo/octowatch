################################################################################
# OctoWatch — Azure DNS Integration
#
# Creates an A record in an existing Azure DNS zone pointing to the VM's
# public IP. Set dns_zone_name and dns_zone_resource_group to enable.
# Leave both empty to skip DNS record creation (Azure FQDN or custom
# tls_domain will be used instead).
################################################################################

data "azurerm_dns_zone" "existing" {
  count               = var.dns_zone_name != "" ? 1 : 0
  name                = var.dns_zone_name
  resource_group_name = var.dns_zone_resource_group
}

resource "azurerm_dns_a_record" "octowatch" {
  # Destroyed at cutover (aca_cutover_complete = true) — the CNAME in
  # container_apps.tf takes over traffic routing to the ACA frontend.
  count               = var.dns_zone_name != "" && !var.aca_cutover_complete ? 1 : 0
  name                = var.dns_record_name
  zone_name           = data.azurerm_dns_zone.existing[0].name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = var.dns_ttl
  records             = [azurerm_public_ip.main.ip_address]
  tags                = local.common_tags
}
