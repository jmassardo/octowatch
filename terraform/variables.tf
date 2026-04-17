################################################################################
# OctoWatch — Input Variables
################################################################################

# ── Core Infrastructure ────────────────────────────────────────────────────────

variable "location" {
  type        = string
  default     = "eastus2"
  description = "Azure region where all resources will be deployed."
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev | staging | prod). Used in resource names and tags."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "owner_tag" {
  type        = string
  default     = "platform-team"
  description = "Value for the 'owner' resource tag."
}

variable "extra_tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags to merge onto every resource."
}

# ── Virtual Machine ────────────────────────────────────────────────────────────

variable "vm_size" {
  type        = string
  default     = "Standard_D4s_v5"
  description = "Azure VM SKU. Standard_D4s_v5 provides 4 vCPUs / 16 GiB RAM."
}

variable "data_disk_size_gb" {
  type        = number
  default     = 256
  description = "Size in GiB of the Premium SSD data disk (mounted at /mnt/octowatch-data)."
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key (RSA or ED25519) for the 'octowatch' admin user."
}

variable "ssh_source_cidr" {
  type        = string
  default     = "*"
  description = "CIDR allowed to reach port 22. Restrict to your IP in production (e.g. '203.0.113.10/32')."
}

variable "dns_label" {
  type        = string
  description = "DNS label for the public IP. FQDN will be <dns_label>.<location>.cloudapp.azure.com."
}

# ── Existing Azure DNS Zone ────────────────────────────────────────────────────

variable "dns_zone_name" {
  type        = string
  default     = ""
  description = "Name of an existing Azure DNS zone (e.g. 'example.com'). When set, an A record is created pointing to the VM's public IP and the DNS FQDN becomes the effective TLS domain."
}

variable "dns_zone_resource_group" {
  type        = string
  default     = ""
  description = "Resource group that contains the existing Azure DNS zone. Required when dns_zone_name is set."
}

variable "dns_record_name" {
  type        = string
  default     = "octowatch"
  description = "Name of the A record to create in the DNS zone (e.g. 'octowatch' → octowatch.example.com)."
}

variable "dns_ttl" {
  type        = number
  default     = 300
  description = "TTL (in seconds) for the DNS A record."
}

# ── TLS / Certificates ─────────────────────────────────────────────────────────

variable "tls_mode" {
  type        = string
  default     = "selfsigned"
  description = "TLS provisioning mode: 'selfsigned' (self-signed cert) or 'letsencrypt' (ACME via certbot)."

  validation {
    condition     = contains(["selfsigned", "letsencrypt"], var.tls_mode)
    error_message = "tls_mode must be 'selfsigned' or 'letsencrypt'."
  }
}

variable "tls_domain" {
  type        = string
  default     = ""
  description = "Custom domain for TLS certificate. Leave empty to use the Azure FQDN (dns_label.location.cloudapp.azure.com)."
}

variable "certbot_email" {
  type        = string
  default     = ""
  description = "Email address passed to certbot (required when tls_mode = 'letsencrypt')."
}

# ── GHCR Container Registry ────────────────────────────────────────────────────

variable "ghcr_username" {
  type        = string
  description = "GitHub username for GHCR authentication."
}

variable "ghcr_token" {
  type        = string
  sensitive   = true
  description = "GitHub Personal Access Token (PAT) with 'read:packages' scope for GHCR."
}

variable "ghcr_image_tag" {
  type        = string
  default     = "latest"
  description = "Docker image tag to pull from GHCR (e.g. 'latest', 'v1.2.3', 'sha-abc1234')."
}

variable "ghcr_owner" {
  type        = string
  description = "GitHub organisation or user that owns the GHCR packages (e.g. 'my-org')."
}

# ── Application Secrets (Core) ─────────────────────────────────────────────────
# All secrets are stored in Azure Key Vault. They are written to the VM's .env
# file at boot via managed-identity-authenticated Key Vault calls.

variable "secret_database_url" {
  type        = string
  sensitive   = true
  description = "Full PostgreSQL / TimescaleDB connection URL (postgres://user:pass@host/db)."
}

variable "secret_secret_key" {
  type        = string
  sensitive   = true
  description = "Django/FastAPI SECRET_KEY — long random string for JWT/session signing."
}

variable "secret_encryption_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Optional additional encryption key (Fernet-compatible base64 string)."
}

variable "secret_valkey_url" {
  type        = string
  sensitive   = true
  description = "Valkey (Redis-compatible) connection URL (redis://:password@host:6379/0)."
}

variable "secret_valkey_password" {
  type        = string
  sensitive   = true
  description = "Valkey requirepass password (must match VALKEY_URL)."
}

variable "secret_postgres_user" {
  type        = string
  sensitive   = true
  description = "PostgreSQL superuser username for the Docker Compose db service."
}

variable "secret_postgres_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL superuser password for the Docker Compose db service."
}

variable "secret_postgres_db" {
  type        = string
  sensitive   = true
  description = "PostgreSQL database name created on first start."
}

variable "secret_github_client_id" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client ID for user authentication."
}

variable "secret_github_client_secret" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client Secret."
}

variable "secret_github_rules_repo" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub repo containing detection rules (org/repo format). Leave empty to disable."
}

variable "secret_github_rules_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub PAT for reading the rules repository."
}

variable "secret_initial_admin_logins" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Comma-separated GitHub logins that receive initial admin role on first boot."
}

variable "secret_app_base_url" {
  type        = string
  sensitive   = true
  description = "Public base URL of the application (e.g. https://octowatch.example.com)."
}

# ── Application Secrets (Optional Integrations) ────────────────────────────────

variable "secret_github_app_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub App ID for Enterprise Sync. Leave empty to disable."
}

variable "secret_github_app_private_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub App private key (PEM contents). Stored as a file on the VM."
}

variable "secret_github_enterprise_slug" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub Enterprise slug for organisation sync."
}

variable "secret_maxmind_license_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "MaxMind GeoLite2 license key for IP geolocation enrichment."
}

variable "secret_okta_org_url" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Okta organisation URL (https://<tenant>.okta.com) for IdP enrichment."
}

variable "secret_okta_api_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Okta API token for IdP enrichment queries."
}

variable "secret_azure_ad_tenant_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Azure AD (Entra) tenant ID for IdP enrichment."
}

variable "secret_azure_ad_client_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Azure AD application (client) ID for IdP enrichment."
}

variable "secret_azure_ad_client_secret" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Azure AD client secret for IdP enrichment."
}

variable "secret_slack_bot_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Slack Bot OAuth token (xoxb-...) for alert notifications."
}

variable "secret_smtp_host" {
  type        = string
  sensitive   = true
  default     = ""
  description = "SMTP server hostname for email notifications."
}

variable "secret_smtp_username" {
  type        = string
  sensitive   = true
  default     = ""
  description = "SMTP authentication username."
}

variable "secret_smtp_password" {
  type        = string
  sensitive   = true
  default     = ""
  description = "SMTP authentication password."
}

variable "secret_jira_url" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Jira instance URL for ticket creation (https://yourorg.atlassian.net)."
}

variable "secret_jira_username" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Jira username (email) for API authentication."
}

variable "secret_jira_api_token" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Jira API token for ticket creation."
}

# ── Optional Features ──────────────────────────────────────────────────────────

variable "enable_disk_encryption_set" {
  type        = bool
  default     = false
  description = "Enable customer-managed key disk encryption (requires additional Key Vault setup)."
}

variable "enable_defender" {
  type        = bool
  default     = false
  description = "Enable Microsoft Defender for Cloud on the VM."
}

variable "enable_auto_shutdown" {
  type        = bool
  default     = false
  description = "Enable daily auto-shutdown schedule (useful for dev/staging to reduce costs)."
}

variable "auto_shutdown_time" {
  type        = string
  default     = "2300"
  description = "Daily auto-shutdown time in HHMM UTC format (e.g. '2300' = 11 PM UTC)."
}
