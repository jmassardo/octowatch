output "resource_group_name" {
  description = "Name of the Azure resource group"
  value       = azurerm_resource_group.main.name
}

output "vm_public_ip" {
  description = "Public IP address of the VM"
  value       = azurerm_public_ip.main.ip_address
}

output "vm_fqdn" {
  description = "Fully qualified domain name (Azure-assigned)"
  value       = azurerm_public_ip.main.fqdn
}

output "acr_login_server" {
  description = "ACR login server URL"
  value       = azurerm_container_registry.main.login_server
}

output "acr_name" {
  description = "ACR name"
  value       = azurerm_container_registry.main.name
}

output "app_url" {
  description = "Application URL"
  value       = "https://${azurerm_public_ip.main.fqdn}"
}

output "ssh_private_key" {
  description = "SSH private key for VM access"
  value       = tls_private_key.vm.private_key_pem
  sensitive   = true
}

output "ssh_command" {
  description = "SSH command to connect to the VM"
  value       = "ssh -i octowatch.pem ${var.admin_username}@${azurerm_public_ip.main.fqdn}"
}
