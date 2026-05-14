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
  # Destroyed at cutover (aca_cutover_complete, aks_cutover_complete, or
  # k8s_cutover_complete = true) — the target platform's record takes over.
  count               = var.dns_zone_name != "" && !(var.aca_cutover_complete || var.aks_cutover_complete || var.k8s_cutover_complete) ? 1 : 0
  name                = var.dns_record_name
  zone_name           = data.azurerm_dns_zone.existing[0].name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = var.dns_ttl
  records             = [azurerm_public_ip.main.ip_address]
  tags                = local.common_tags
}

resource "azurerm_dns_a_record" "octowatch_aks" {
  count               = var.aks_cutover_complete && var.aks_ingress_lb_ip != "" ? 1 : 0
  name                = var.dns_record_name
  zone_name           = data.azurerm_dns_zone.existing[0].name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = var.dns_ttl
  records             = [var.aks_ingress_lb_ip]
  tags                = local.common_tags
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
