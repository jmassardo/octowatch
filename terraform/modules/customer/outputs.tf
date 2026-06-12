################################################################################
# OctoWatch — Customer Module Outputs
#
# Values needed to populate the Helm release (via CI or manual helm install).
################################################################################

output "namespace" {
  value       = kubernetes_namespace.customer.metadata[0].name
  description = "Kubernetes namespace for this customer's OctoWatch instance."
}

output "key_vault_name" {
  value       = azurerm_key_vault.customer.name
  description = "Azure Key Vault name for this customer."
}

output "key_vault_uri" {
  value       = azurerm_key_vault.customer.vault_uri
  description = "Azure Key Vault URI for this customer."
}

output "workload_identity_client_id" {
  value       = azurerm_user_assigned_identity.workload.client_id
  description = "Client ID of the workload identity (for Helm values)."
}

output "workload_identity_tenant_id" {
  value       = data.azurerm_client_config.current.tenant_id
  description = "Azure AD tenant ID (for Helm values)."
}

output "dns_fqdn" {
  value       = "${var.customer_slug}.octowatch.dev"
  description = "Customer's fully qualified domain name."
}

output "backup_container_name" {
  value       = azurerm_storage_container.backup.name
  description = "Blob storage container name for this customer's backups."
}

output "ring" {
  value       = var.ring
  description = "Deployment ring this customer is assigned to."
}

output "size" {
  value       = var.size
  description = "T-shirt size assigned to this customer."
}
