################################################################################
# OctoWatch — Outputs
################################################################################

output "vm_public_ip" {
  value       = azurerm_public_ip.main.ip_address
  description = "Public IP address of the OctoWatch VM"
}

output "vm_fqdn" {
  value       = var.enable_aks ? azurerm_public_ip.main.fqdn : "disabled"
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

output "key_vault_uri" {
  value       = "https://${local.key_vault_name}.vault.azure.net/"
  description = "URI of the Azure Key Vault (constructed from naming convention)"
}

output "managed_identity_client_id" {
  value       = azurerm_user_assigned_identity.vm.client_id
  description = "Client ID of the VM user-assigned managed identity"
}

# ── AKS Workload Identity Outputs ─────────────────────────────────────────────

output "workload_identity_client_id" {
  value       = azurerm_user_assigned_identity.aks_workload.client_id
  description = "Client ID of the AKS workload identity (for Helm values)"
}

output "workload_identity_tenant_id" {
  value       = data.azurerm_client_config.current.tenant_id
  description = "Azure AD tenant ID for workload identity federation"
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
  value       = var.enable_aks ? azurerm_linux_virtual_machine.main[0].id : "disabled"
  description = "Azure resource ID of the VM"
}

# ── Azure Container Apps Outputs ───────────────────────────────────────────────

output "aca_environment_default_domain" {
  value       = var.enable_aks ? azurerm_container_app_environment.main[0].default_domain : "disabled"
  description = "Default domain for the Container Apps environment (for smoke testing before cutover)"
}

output "aca_frontend_url" {
  value       = var.enable_aks ? "https://${azurerm_container_app.frontend[0].ingress[0].fqdn}" : "disabled"
  description = "Auto-generated HTTPS URL of the frontend Container App (before custom domain)"
}

output "aca_migrate_job_run_command" {
  value       = "az containerapp job start --name ${var.enable_aks ? azurerm_container_app_job.migrate[0].name : "disabled"} --resource-group ${azurerm_resource_group.main.name}"
  description = "Full CLI command to trigger a database migration run"
}

output "aca_premium_storage_account" {
  value       = var.enable_aks ? azurerm_storage_account.premium[0].name : "disabled"
  description = "Premium FileStorage account name backing pg-data and valkey-data Azure Files shares"
}

output "aks_cluster_name" {
  value = var.enable_aks ? azurerm_kubernetes_cluster.main[0].name : "disabled"
}

output "aks_cluster_fqdn" {
  value = var.enable_aks ? azurerm_kubernetes_cluster.main[0].fqdn : "disabled"
}

output "aks_kube_config" {
  value       = var.enable_aks ? azurerm_kubernetes_cluster.main[0].kube_config_raw : "disabled"
  sensitive   = true
  description = "Run: terraform output -raw aks_kube_config > ~/.kube/config-aks"
}

output "argocd_url" {
  value = var.enable_aks ? "https://argocd.${local.tls_domain}" : "disabled"
}

output "aks_ingress_lb_ip_instruction" {
  value = "After apply, get LB IP: kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}', then set aks_ingress_lb_ip in tfvars"
}

output "aks_nat_egress_ip" {
  value       = var.enable_aks ? azurerm_public_ip.aks_egress[0].ip_address : "disabled"
  description = "Static public IP used by all AKS node egress traffic. Add this to api_server_authorized_ip_ranges and any external service allowlists."
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
  description = "Private IPs of the 3 K8s cluster nodes."
}

output "k8s_ssh_jump_example" {
  value       = "ssh -J octowatch@${azurerm_public_ip.k8s_mgmt.ip_address} octowatch@${local.k8s_node_ips[0]}"
  description = "Example: SSH to a K8s node via the management VM jump host."
}
