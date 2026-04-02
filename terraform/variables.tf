/* ------------------------------------------------------------------ */
/*  General                                                            */
/* ------------------------------------------------------------------ */

variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
  default     = "octowatch"
}

variable "environment" {
  description = "Deployment environment (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

/* ------------------------------------------------------------------ */
/*  Compute                                                            */
/* ------------------------------------------------------------------ */

variable "vm_size" {
  description = "Azure VM size (4 vCPU / 16 GB recommended for TimescaleDB + workers)"
  type        = string
  default     = "Standard_D4s_v5"
}

variable "admin_username" {
  description = "VM admin SSH username"
  type        = string
  default     = "octoadmin"
}

variable "data_disk_size_gb" {
  description = "Size of the data disk for PostgreSQL, Valkey, and MinIO"
  type        = number
  default     = 128
}

/* ------------------------------------------------------------------ */
/*  Networking                                                         */
/* ------------------------------------------------------------------ */

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the VM (empty = no SSH from internet)"
  type        = list(string)
  default     = []
}

/* ------------------------------------------------------------------ */
/*  Container Registry                                                 */
/* ------------------------------------------------------------------ */

variable "acr_name" {
  description = "Azure Container Registry name (must be globally unique, alphanumeric only)"
  type        = string
}

/* ------------------------------------------------------------------ */
/*  Application – GitHub                                               */
/* ------------------------------------------------------------------ */

variable "github_app_id" {
  description = "GitHub App numeric ID"
  type        = string
  default     = ""
}

variable "github_enterprise_slug" {
  description = "GitHub Enterprise account slug"
  type        = string
  default     = ""
}

variable "github_client_id" {
  description = "GitHub OAuth App client ID"
  type        = string
  sensitive   = true
}

variable "github_client_secret" {
  description = "GitHub OAuth App client secret"
  type        = string
  sensitive   = true
}

variable "initial_admin_logins" {
  description = "Comma-separated GitHub logins granted initial admin access"
  type        = string
  default     = ""
}
