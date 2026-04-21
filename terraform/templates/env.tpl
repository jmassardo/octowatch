# OctoWatch environment -- rendered at provision time by Terraform.
# To update secrets: update terraform.tfvars and re-provision the VM.

# -- Core ----------------------------------------------------------------------
DATABASE_URL=${secret_database_url}
SECRET_KEY=${secret_secret_key}
ENCRYPTION_KEY=${secret_encryption_key}
VALKEY_URL=${secret_valkey_url}
VALKEY_PASSWORD=${secret_valkey_password}

# -- PostgreSQL ----------------------------------------------------------------
POSTGRES_USER=${secret_postgres_user}
POSTGRES_PASSWORD=${secret_postgres_password}
POSTGRES_DB=${secret_postgres_db}

# -- GitHub OAuth & Rules ------------------------------------------------------
GITHUB_CLIENT_ID=${secret_github_client_id}
GITHUB_CLIENT_SECRET=${secret_github_client_secret}
GITHUB_RULES_REPO=${secret_github_rules_repo}
GITHUB_RULES_TOKEN=${secret_github_rules_token}

# -- Application ---------------------------------------------------------------
APP_BASE_URL=${secret_app_base_url}
INITIAL_ADMIN_LOGINS=${secret_initial_admin_logins}
INGESTION_MODE=hec
LOG_LEVEL=INFO

# -- GitHub App (Enterprise Sync) ----------------------------------------------
GITHUB_APP_ID=${secret_github_app_id}
GITHUB_APP_PRIVATE_KEY_PATH=%{ if secret_github_app_private_key != "" }/opt/octowatch/compose/github-app-key.pem%{ endif }
GITHUB_ENTERPRISE_SLUG=${secret_github_enterprise_slug}
GITHUB_SYNC_ENABLED=false

# -- MaxMind GeoIP -------------------------------------------------------------
MAXMIND_LICENSE_KEY=${secret_maxmind_license_key}

# -- Okta IdP ------------------------------------------------------------------
OKTA_ORG_URL=${secret_okta_org_url}
OKTA_API_TOKEN=${secret_okta_api_token}

# -- Azure AD / Entra IdP ------------------------------------------------------
AZURE_AD_TENANT_ID=${secret_azure_ad_tenant_id}
AZURE_AD_CLIENT_ID=${secret_azure_ad_client_id}
AZURE_AD_CLIENT_SECRET=${secret_azure_ad_client_secret}

# -- Slack Notifications -------------------------------------------------------
SLACK_BOT_TOKEN=${secret_slack_bot_token}

# -- SMTP Notifications --------------------------------------------------------
SMTP_HOST=${secret_smtp_host}
SMTP_PORT=587
SMTP_USERNAME=${secret_smtp_username}
SMTP_PASSWORD=${secret_smtp_password}
SMTP_FROM_ADDRESS=

# -- Jira Ticketing ------------------------------------------------------------
JIRA_URL=${secret_jira_url}
JIRA_USERNAME=${secret_jira_username}
JIRA_API_TOKEN=${secret_jira_api_token}
