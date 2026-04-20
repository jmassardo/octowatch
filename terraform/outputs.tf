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

# ── Azure Container Apps Outputs ───────────────────────────────────────────────

output "aca_environment_default_domain" {
  value       = azurerm_container_app_environment.main.default_domain
  description = "Default domain for the Container Apps environment (for smoke testing before cutover)"
}

output "aca_frontend_url" {
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
  description = "Auto-generated HTTPS URL of the frontend Container App (before custom domain)"
}

output "aca_migrate_job_run_command" {
  value       = "az containerapp job start --name ${azurerm_container_app_job.migrate.name} --resource-group ${azurerm_resource_group.main.name}"
  description = "Full CLI command to trigger a database migration run"
}

output "aca_premium_storage_account" {
  value       = azurerm_storage_account.premium.name
  description = "Premium FileStorage account name backing pg-data and valkey-data Azure Files shares"
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "aks_cluster_fqdn" {
  value = azurerm_kubernetes_cluster.main.fqdn
}

output "aks_kube_config" {
  value       = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive   = true
  description = "Run: terraform output -raw aks_kube_config > ~/.kube/config-aks"
}

output "argocd_url" {
  value = "https://argocd.${local.tls_domain}"
}

output "aks_ingress_lb_ip_instruction" {
  value = "After apply, get LB IP: kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}', then set aks_ingress_lb_ip in tfvars"
}
