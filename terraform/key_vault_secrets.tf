################################################################################
# OctoWatch — Key Vault Secrets
#
# All secrets depend on the Secrets Officer RBAC assignment to ensure the
# deploying principal has write access before attempting to create secrets.
#
# Naming convention: octowatch-<component>-<variable>
# On the VM, secrets are fetched by name and written to /opt/octowatch/compose/.env
################################################################################

# ── Core Application ───────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "database_url" {
  name         = "octowatch-database-url"
  value        = var.secret_database_url
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "secret_key" {
  name         = "octowatch-secret-key"
  value        = var.secret_secret_key
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "encryption_key" {
  name         = "octowatch-encryption-key"
  value        = var.secret_encryption_key
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "valkey_url" {
  name         = "octowatch-valkey-url"
  value        = var.secret_valkey_url
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "valkey_password" {
  name         = "octowatch-valkey-password"
  value        = var.secret_valkey_password
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── PostgreSQL ─────────────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "postgres_user" {
  name         = "octowatch-postgres-user"
  value        = var.secret_postgres_user
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "octowatch-postgres-password"
  value        = var.secret_postgres_password
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "postgres_db" {
  name         = "octowatch-postgres-db"
  value        = var.secret_postgres_db
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── GitHub OAuth & Rules ───────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "github_client_id" {
  name         = "octowatch-github-client-id"
  value        = var.secret_github_client_id
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "github_client_secret" {
  name         = "octowatch-github-client-secret"
  value        = var.secret_github_client_secret
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "github_rules_repo" {
  name         = "octowatch-github-rules-repo"
  value        = var.secret_github_rules_repo
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "github_rules_token" {
  name         = "octowatch-github-rules-token"
  value        = var.secret_github_rules_token
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── Application Settings ───────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "initial_admin_logins" {
  name         = "octowatch-initial-admin-logins"
  value        = var.secret_initial_admin_logins
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "app_base_url" {
  name         = "octowatch-app-base-url"
  value        = var.secret_app_base_url
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── GHCR Token ─────────────────────────────────────────────────────────────────
# Stored in KV so the VM can retrieve it at boot for docker login.

resource "azurerm_key_vault_secret" "ghcr_token" {
  name         = "octowatch-ghcr-token"
  value        = var.ghcr_token
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── GitHub App (Enterprise Sync) ───────────────────────────────────────────────

resource "azurerm_key_vault_secret" "github_app_id" {
  name         = "octowatch-github-app-id"
  value        = var.secret_github_app_id
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "github_app_private_key" {
  name         = "octowatch-github-app-private-key"
  value        = var.secret_github_app_private_key
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "github_enterprise_slug" {
  name         = "octowatch-github-enterprise-slug"
  value        = var.secret_github_enterprise_slug
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── MaxMind GeoIP ──────────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "maxmind_license_key" {
  name         = "octowatch-maxmind-license-key"
  value        = var.secret_maxmind_license_key
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── Okta IdP Enrichment ────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "okta_org_url" {
  name         = "octowatch-okta-org-url"
  value        = var.secret_okta_org_url
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "okta_api_token" {
  name         = "octowatch-okta-api-token"
  value        = var.secret_okta_api_token
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── Azure AD / Entra IdP Enrichment ───────────────────────────────────────────

resource "azurerm_key_vault_secret" "azure_ad_tenant_id" {
  name         = "octowatch-azure-ad-tenant-id"
  value        = var.secret_azure_ad_tenant_id
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_ad_client_id" {
  name         = "octowatch-azure-ad-client-id"
  value        = var.secret_azure_ad_client_id
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "azure_ad_client_secret" {
  name         = "octowatch-azure-ad-client-secret"
  value        = var.secret_azure_ad_client_secret
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── Slack Notifications ────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "slack_bot_token" {
  name         = "octowatch-slack-bot-token"
  value        = var.secret_slack_bot_token
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── SMTP Email Notifications ───────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "smtp_host" {
  name         = "octowatch-smtp-host"
  value        = var.secret_smtp_host
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "smtp_username" {
  name         = "octowatch-smtp-username"
  value        = var.secret_smtp_username
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "smtp_password" {
  name         = "octowatch-smtp-password"
  value        = var.secret_smtp_password
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

# ── Jira Ticketing ─────────────────────────────────────────────────────────────

resource "azurerm_key_vault_secret" "jira_url" {
  name         = "octowatch-jira-url"
  value        = var.secret_jira_url
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "jira_username" {
  name         = "octowatch-jira-username"
  value        = var.secret_jira_username
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "jira_api_token" {
  name         = "octowatch-jira-api-token"
  value        = var.secret_jira_api_token
  key_vault_id = azurerm_key_vault.main.id
  tags         = local.common_tags
  depends_on   = [azurerm_role_assignment.kv_secrets_officer]
}
