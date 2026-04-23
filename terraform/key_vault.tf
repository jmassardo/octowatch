################################################################################
# OctoWatch — Azure Key Vault
# NOTE: The Key Vault (kv-oct-dev-i6iv6t) was created in a previous apply run
# with rbac_authorization_enabled=true and is no longer managed by Terraform.
# The CSA subscription Contributor role cannot change the permission model.
# Secrets are now baked into cloud-init userdata at provision time instead.
# A user with Owner/User-Access-Administrator can manage the KV manually.
#
# ── Network ACL State (applied live 2026-04-23) ────────────────────────────────
# The following network restrictions were applied directly via az CLI:
#
#   Default action : Deny
#   Bypass         : AzureServices
#   IP rules       : 66.116.122.236/32, 66.116.122.237/32 (platform-team admin)
#   VNet rules     : snet-aks-octowatch-dev (Microsoft.KeyVault service endpoint
#                    enabled on the subnet to support the VNet rule)
#
# Commands used:
#   # Enable service endpoint on AKS subnet (prerequisite for VNet rule)
#   az network vnet subnet update \
#     --resource-group rg-octowatch-dev \
#     --vnet-name vnet-octowatch-dev \
#     --name snet-aks-octowatch-dev \
#     --service-endpoints Microsoft.KeyVault
#
#   # Add admin IP before locking down
#   az keyvault network-rule add \
#     --name kv-oct-dev-i6iv6t \
#     --resource-group rg-octowatch-dev \
#     --ip-address <ADMIN_IP>/32
#
#   # Add AKS subnet rule
#   az keyvault network-rule add \
#     --name kv-oct-dev-i6iv6t \
#     --resource-group rg-octowatch-dev \
#     --subnet <AKS_SUBNET_ID>
#
#   # Set default action to Deny with AzureServices bypass
#   az keyvault update \
#     --name kv-oct-dev-i6iv6t \
#     --resource-group rg-octowatch-dev \
#     --default-action Deny \
#     --bypass AzureServices
#
# To re-enable full Terraform management of this Key Vault:
#   1. An Owner must assign "Key Vault Administrator" to the deploying principal
#   2. Restore the azurerm_key_vault resource block (see git history)
#   3. Import the existing KV: terraform import azurerm_key_vault.main <KV_ID>
#   4. Add azurerm_key_vault_network_acls or inline network_acls block to codify
#      the network rules above
################################################################################

# Random suffix kept to avoid destroying the existing random resource in state.
resource "random_string" "kv_suffix" {
  length  = 6
  special = false
  upper   = false
}

# Key Vault resource intentionally removed from management.
# The vault kv-oct-dev-i6iv6t exists in Azure but Terraform no longer manages it.
# To re-enable: an Owner must assign Key Vault Secrets Officer to the deploying
# principal, then the azurerm_key_vault resource and key_vault_secrets.tf can
# be restored.

# ── Storage RBAC removed ───────────────────────────────────────────────────────
# Contributor role lacks Microsoft.Authorization/roleAssignments/write.
# VM backup uploads use the storage account key instead.
