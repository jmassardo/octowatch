# OctoWatch — Terraform Variables
# DO NOT commit this file — it contains secrets.

# ── Core Infrastructure ────────────────────────────────────────────────────────

location    = "eastus2"
environment = "dev"
owner_tag   = "jmassardo"

extra_tags = {
  project = "octowatch"
}

# ── Virtual Machine ────────────────────────────────────────────────────────────

vm_size           = "Standard_D4ds_v5"
data_disk_size_gb = 256

ssh_public_key  = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL9IWLCawifl85hM1soanbvESFFPsB8SSenXFkshGFyx jmassardo"
ssh_source_cidr = "*"
dns_label       = "octowatch-dev"

# ── Azure DNS Zone ─────────────────────────────────────────────────────────────

dns_zone_name           = "jmassardo.azure.csa-github.com"
dns_zone_resource_group = "csa-shared-resources"
dns_record_name         = "octowatch"
dns_ttl                 = 300

# ── TLS / Certificates ─────────────────────────────────────────────────────────

tls_mode      = "letsencrypt"
tls_domain    = "octowatch.jmassardo.azure.csa-github.com"
certbot_email = "jmassardo@github.com"

# ── GHCR Container Registry ────────────────────────────────────────────────────

ghcr_username  = "jmassardo"
ghcr_token     = "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"
ghcr_image_tag = "latest"
ghcr_owner     = "jmassardo"

# ── Application Secrets (Core) ─────────────────────────────────────────────────

secret_database_url      = "postgresql+asyncpg://octowatch:M8gkK0JZtjVLYVglbgMNQbvxc6K6m0UtGhCscIUDZQo@db:5432/octowatch"
secret_secret_key        = "646e5de983afd27f3248f71c7baa647fd984c866d633dc583a247fa19dd2eccd7982b6fc58d60ad579654ad6f9267c7701f4fb92547166206ae7f81809fc69a9"
secret_encryption_key    = "Y8V0pBycKW6x82ugZcb4EQWBXJ3_Vhb2qY7wLS-tkRU="
secret_valkey_url        = "redis://:BRA_vo_hfgL952Z8doSzevrmzLszumbnx3T9t-pG93k@valkey:6379/0"
secret_valkey_password   = "BRA_vo_hfgL952Z8doSzevrmzLszumbnx3T9t-pG93k"
secret_postgres_user     = "octowatch"
secret_postgres_password = "M8gkK0JZtjVLYVglbgMNQbvxc6K6m0UtGhCscIUDZQo"
secret_postgres_db       = "octowatch"

secret_github_client_id     = "Ov23ctoyvthSLYdOGkmw"
secret_github_client_secret = "21aa357dc65f5e7158bc9639b39525371fcb2a2d"

secret_github_rules_repo  = ""
secret_github_rules_token = ""

secret_initial_admin_logins = "jmassardo"
secret_app_base_url         = "https://octowatch.jmassardo.azure.csa-github.com"

# ── Optional Integrations ──────────────────────────────────────────────────────

secret_github_app_id          = ""
secret_github_app_private_key = ""
secret_github_enterprise_slug = ""
secret_maxmind_license_key    = ""
secret_okta_org_url           = ""
secret_okta_api_token         = ""
secret_azure_ad_tenant_id     = ""
secret_azure_ad_client_id     = ""
secret_azure_ad_client_secret = ""
secret_slack_bot_token        = ""
secret_smtp_host              = ""
secret_smtp_username          = ""
secret_smtp_password          = ""
secret_jira_url               = ""
secret_jira_username          = ""
secret_jira_api_token         = ""

# ── AKS / ArgoCD ──────────────────────────────────────────────────────────────

aks_node_size         = "Standard_D4s_v4"
aks_cutover_complete  = true
aks_ingress_lb_ip     = "132.196.147.130"
argocd_admin_password = "OctoWatch-AKS-2026!"
argocd_github_pat     = ""
letsencrypt_email     = "jmassardo@github.com"

# ── Optional Features ──────────────────────────────────────────────────────────

enable_disk_encryption_set = false
enable_defender            = false
enable_auto_shutdown       = false
auto_shutdown_time         = "0200"
secret_azure_storage_connection_string = ""
