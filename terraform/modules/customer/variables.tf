################################################################################
# OctoWatch — Customer Module Variables
#
# Each customer gets an isolated namespace with its own Key Vault, workload
# identity, DNS record, and backup storage container.
################################################################################

variable "customer_slug" {
  type        = string
  description = "Unique customer identifier (lowercase, alphanumeric + hyphens). Used in namespace name and DNS."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.customer_slug))
    error_message = "customer_slug must be lowercase alphanumeric with hyphens, 2-21 chars, starting with a letter."
  }
}

variable "ring" {
  type        = string
  description = "Deployment ring for this customer."

  validation {
    condition     = contains(["test", "preview", "prod"], var.ring)
    error_message = "ring must be one of: test, preview, prod."
  }
}

variable "size" {
  type        = string
  default     = "small"
  description = "T-shirt size controlling resource allocation."

  validation {
    condition     = contains(["small", "medium", "large"], var.size)
    error_message = "size must be one of: small, medium, large."
  }
}

variable "resource_group_name" {
  type        = string
  description = "Azure resource group for customer resources."
}

variable "location" {
  type        = string
  description = "Azure region for resources."
}

variable "aks_oidc_issuer_url" {
  type        = string
  description = "OIDC issuer URL from the AKS cluster (for federated identity)."
}

variable "aks_subnet_id" {
  type        = string
  description = "AKS subnet ID for Key Vault network rules."
}

variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone ID for octowatch.dev."
}

variable "ingress_lb_ip" {
  type        = string
  description = "Public IP of the shared NGINX ingress load balancer."
}

variable "backup_storage_account_id" {
  type        = string
  description = "ID of the shared storage account for backup containers."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags to apply to all resources."
}
