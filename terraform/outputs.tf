################################################################################
# OctoWatch — Outputs
################################################################################

output "dns_fqdn" {
  value       = var.dns_zone_name != "" ? "${var.dns_record_name}.${var.dns_zone_name}" : null
  description = "Custom DNS FQDN from the existing Azure DNS zone, if configured"
}

output "tls_domain" {
  value       = local.tls_domain
  description = "Effective TLS domain"
}

output "resource_group_name" {
  value       = azurerm_resource_group.main.name
  description = "Resource group name"
}

# Key Vault outputs removed — KV is no longer managed by Terraform.
# The vault kv-oct-dev-i6iv6t exists in Azure but Terraform no longer manages it.

output "key_vault_uri" {
  value       = "https://${local.key_vault_name}.vault.azure.net/"
  description = "URI of the Azure Key Vault (constructed from naming convention)"
}

output "managed_identity_client_id" {
  value       = azurerm_user_assigned_identity.vm.client_id
  description = "Client ID of the VM user-assigned managed identity"
}

output "managed_identity_principal_id" {
  value       = azurerm_user_assigned_identity.vm.principal_id
  description = "Principal ID of the user-assigned managed identity"
}

output "storage_account_name" {
  value       = azurerm_storage_account.main.name
  description = "Storage account name for backups and diagnostics"
}

output "storage_account_connection_string" {
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
  description = "Storage account connection string"
}

# ── Self-Managed K8s Cluster Outputs ──────────────────────────────────────────

output "k8s_mgmt_public_ip" {
  value       = azurerm_public_ip.k8s_mgmt.ip_address
  description = "Public IP of the K8s management/bastion VM."
}

output "k8s_mgmt_ssh_command" {
  value       = "ssh octowatch@${azurerm_public_ip.k8s_mgmt.ip_address}"
  description = "SSH command to connect to the management VM."
}

output "k8s_lb_public_ip" {
  value       = azurerm_public_ip.k8s_lb.ip_address
  description = "Public IP of the K8s cluster Load Balancer (HTTP/S traffic)."
}

output "k8s_node_private_ips" {
  value       = local.k8s_node_ips
  description = "Private IPs of the K8s cluster nodes."
}

output "k8s_ssh_jump_example" {
  value       = "ssh -J octowatch@${azurerm_public_ip.k8s_mgmt.ip_address} octowatch@${local.k8s_node_ips[0]}"
  description = "Example: SSH to a K8s node via the management VM jump host."
}
