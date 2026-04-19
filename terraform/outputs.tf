################################################################################
# OctoWatch — Outputs
################################################################################

output "vm_public_ip" {
  value       = azurerm_public_ip.main.ip_address
  description = "Public IP address of the OctoWatch VM"
}

output "vm_fqdn" {
  value       = azurerm_public_ip.main.fqdn
  description = "Azure FQDN of the OctoWatch VM"
}

output "dns_fqdn" {
  value       = var.dns_zone_name != "" ? "${var.dns_record_name}.${var.dns_zone_name}" : null
  description = "Custom DNS FQDN from the existing Azure DNS zone, if configured"
}

output "tls_domain" {
  value       = local.tls_domain
  description = "Effective TLS domain"
}

output "ssh_command" {
  value       = "ssh octowatch@${azurerm_public_ip.main.ip_address}"
  description = "SSH command to connect to the VM"
}

output "resource_group_name" {
  value       = azurerm_resource_group.main.name
  description = "Resource group name"
}

# Key Vault outputs removed — KV is no longer managed by Terraform.
# The vault kv-oct-dev-i6iv6t exists in Azure but Terraform no longer manages it.

output "managed_identity_client_id" {
  value       = azurerm_user_assigned_identity.vm.client_id
  description = "Client ID of the user-assigned managed identity"
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

output "vm_id" {
  value       = azurerm_linux_virtual_machine.main.id
  description = "Azure resource ID of the VM"
}
