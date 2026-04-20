################################################################################
# OctoWatch — Azure Container Apps Infrastructure
#
# Provisions the complete ACA environment to replace the Docker Compose VM.
# All resources are additive — the existing VM infrastructure in vm.tf and
# networking.tf is intentionally left untouched during the migration window.
#
# Deployment order:
#   1. ACA subnet (delegated to Microsoft.App/environments)
#   2. Premium FileStorage account + SMB shares (pg-data, valkey-data)
#   3. Container Apps Environment (custom VNet, Consumption workload profile)
#   4. Environment storage mounts (links shares to environment)
#   5. Container Apps: db → valkey → api → frontend → beat → workers
#   6. Migration job: migrate (manual trigger, run Alembic)
#   7. DNS: TXT verification record + count-gated CNAME (after cutover)
################################################################################

locals {
  aca_database_url   = "postgresql://${var.secret_postgres_user}:${var.secret_postgres_password}@db:5432/${var.secret_postgres_db}"
  aca_valkey_url     = "redis://:${var.secret_valkey_password}@valkey:6379/0"
  image_api          = "ghcr.io/${var.ghcr_owner}/octowatch/api:${var.ghcr_image_tag}"
  image_worker       = "ghcr.io/${var.ghcr_owner}/octowatch/worker:${var.ghcr_image_tag}"
  image_frontend     = "ghcr.io/${var.ghcr_owner}/octowatch/frontend:${var.ghcr_image_tag}"
  custom_domain_fqdn = "${var.dns_record_name}.${var.dns_zone_name}"
}

################################################################################
# A. Networking — ACA-dedicated subnet
################################################################################

resource "azurerm_subnet" "aca" {
  name                 = "snet-aca-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.aca_subnet_cidr]

  delegation {
    name = "aca-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }

  service_endpoints = ["Microsoft.Storage"]
}

################################################################################
# B. Premium Storage Account + SMB Shares
#    Azure Files Premium is required for Container Apps volume mounts.
#    Standard storage does not support SMB mounts in ACA.
################################################################################

resource "random_string" "premium_storage_suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_storage_account" "premium" {
  # Name: "stoctowprem" (11) + environment (3-7) + suffix (6) ≤ 24 chars
  name                = "stoctowprem${var.environment}${random_string.premium_storage_suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  account_kind             = "FileStorage"
  account_tier             = "Premium"
  account_replication_type = "LRS"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false

  network_rules {
    default_action             = "Deny"
    virtual_network_subnet_ids = [azurerm_subnet.aca.id]
    bypass                     = ["AzureServices"]
  }

  tags = local.common_tags

  depends_on = [azurerm_subnet.aca]
}

resource "azurerm_storage_share" "pg_data" {
  name               = "pg-data"
  storage_account_id = azurerm_storage_account.premium.id
  quota              = var.pg_data_share_quota_gb
  enabled_protocol   = "SMB"
}

resource "azurerm_storage_share" "valkey_data" {
  name               = "valkey-data"
  storage_account_id = azurerm_storage_account.premium.id
  quota              = var.valkey_data_share_quota_gb
  enabled_protocol   = "SMB"
}

################################################################################
# C. Container Apps Environment
#    Custom VNet (ACA subnet), Consumption workload profile, public LB.
################################################################################

resource "azurerm_container_app_environment" "main" {
  name                           = "cae-${local.name_prefix}"
  resource_group_name            = azurerm_resource_group.main.name
  location                       = azurerm_resource_group.main.location
  infrastructure_subnet_id       = azurerm_subnet.aca.id
  internal_load_balancer_enabled = false

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }

  tags = local.common_tags
}

################################################################################
# D. Environment Storage Mounts
#    Links the Premium Azure Files shares into the ACA environment so
#    individual container apps can reference them by name in volume blocks.
################################################################################

resource "azurerm_container_app_environment_storage" "pg_data" {
  name                         = "pg-data"
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.premium.name
  share_name                   = azurerm_storage_share.pg_data.name
  access_key                   = azurerm_storage_account.premium.primary_access_key
  access_mode                  = "ReadWrite"
}

resource "azurerm_container_app_environment_storage" "valkey_data" {
  name                         = "valkey-data"
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.premium.name
  share_name                   = azurerm_storage_share.valkey_data.name
  access_key                   = azurerm_storage_account.premium.primary_access_key
  access_mode                  = "ReadWrite"
}

################################################################################
# E. Container App: db (TimescaleDB)
#    Single replica — stateful database, no scaling.
#    PGDATA must point to a subdirectory to avoid mode-0777 startup failure
#    (Docker mounts the parent as 0777; Postgres refuses to start on 0777 dirs).
################################################################################

resource "azurerm_container_app" "db" {
  name                         = "db"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "db"
      image  = "timescale/timescaledb:2.25.1-pg16"
      cpu    = 1.0
      memory = "2Gi"

      # CRITICAL: Set PGDATA to a subdirectory so Postgres does not start
      # in the Azure Files mount root (which is mode 0777 and rejected).
      env {
        name  = "PGDATA"
        value = "/var/lib/postgresql/data/pgdata"
      }
      env {
        name        = "POSTGRES_USER"
        secret_name = "pg-user"
      }
      env {
        name        = "POSTGRES_PASSWORD"
        secret_name = "pg-password"
      }
      env {
        name        = "POSTGRES_DB"
        secret_name = "pg-db"
      }

      volume_mounts {
        name = "pg-data"
        path = "/var/lib/postgresql/data"
      }

      liveness_probe {
        transport        = "TCP"
        port             = 5432
        initial_delay    = 30
        interval_seconds = 30
      }

      readiness_probe {
        transport        = "TCP"
        port             = 5432
        initial_delay    = 10
        interval_seconds = 10
      }
    }

    volume {
      name         = "pg-data"
      storage_name = "pg-data"
      storage_type = "AzureFile"
    }
  }

  # Internal TCP ingress — other container apps reach db on port 5432
  ingress {
    external_enabled = false
    transport        = "tcp"
    target_port      = 5432
    exposed_port     = 5432

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name  = "pg-user"
    value = var.secret_postgres_user
  }
  secret {
    name  = "pg-password"
    value = var.secret_postgres_password
  }
  secret {
    name  = "pg-db"
    value = var.secret_postgres_db
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app_environment_storage.pg_data,
  ]
}

################################################################################
# F. Container App: valkey
#    Single replica — Redis-compatible broker/cache, no scaling.
#    Uses sh -c to expand $VALKEY_PASSWORD at runtime (shell expansion
#    does not work in the JSON exec form that ACA uses natively).
################################################################################

resource "azurerm_container_app" "valkey" {
  name                         = "valkey"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "valkey"
      image  = "valkey/valkey:9.0.3-alpine"
      cpu    = 0.25
      memory = "0.5Gi"

      # sh -c is required so the shell expands $VALKEY_PASSWORD before
      # passing it as the --requirepass argument value.
      command = ["sh", "-c", "valkey-server --requirepass $VALKEY_PASSWORD --appendonly yes"]

      env {
        name        = "VALKEY_PASSWORD"
        secret_name = "valkey-password"
      }

      volume_mounts {
        name = "valkey-data"
        path = "/data"
      }

      liveness_probe {
        transport        = "TCP"
        port             = 6379
        initial_delay    = 10
        interval_seconds = 30
      }
    }

    volume {
      name         = "valkey-data"
      storage_name = "valkey-data"
      storage_type = "AzureFile"
    }
  }

  # Internal TCP ingress — other container apps reach valkey on port 6379
  ingress {
    external_enabled = false
    transport        = "tcp"
    target_port      = 6379
    exposed_port     = 6379

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name  = "valkey-password"
    value = var.secret_valkey_password
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app_environment_storage.valkey_data,
  ]
}

################################################################################
# G. Container App: api (FastAPI / Uvicorn)
#    Scales 1–3 replicas based on concurrent HTTP requests.
################################################################################

resource "azurerm_container_app" "api" {
  name                         = "api"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name    = "api"
      image   = local.image_api
      cpu     = 0.5
      memory  = "1Gi"
      command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

      # ── Connection strings (secrets) ───────────────────────────────────────
      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }

      # ── Application secrets ────────────────────────────────────────────────
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }

      # ── GitHub OAuth ───────────────────────────────────────────────────────
      env {
        name = "GITHUB_CLIENT_ID"
        secret_name = "github-client-id"
      }
      env {
        name = "GITHUB_CLIENT_SECRET"
        secret_name = "github-client-secret"
      }

      # ── GitHub Detection Rules ─────────────────────────────────────────────
      env {
        name = "GITHUB_RULES_TOKEN"
        secret_name = "github-rules-token"
      }
      env {
        name = "GITHUB_RULES_REPO"
        value = var.secret_github_rules_repo
      }
      env {
        name = "GITHUB_RULES_BRANCH"
        value = "main"
      }

      # ── GitHub Enterprise Sync ─────────────────────────────────────────────
      env {
        name = "GITHUB_APP_ID"
        value = var.secret_github_app_id
      }
      env {
        name = "GITHUB_APP_PRIVATE_KEY_PEM"
        secret_name = "github-app-private-key-pem"
      }
      env {
        name = "GITHUB_ENTERPRISE_SLUG"
        value = var.secret_github_enterprise_slug
      }
      env {
        name = "GITHUB_SYNC_ENABLED"
        value = "false"
      }
      env {
        name = "GITHUB_SYNC_INTERVAL_DAYS"
        value = "60"
      }
      env {
        name = "GITHUB_SYNC_ORGS"
        value = ""
      }

      # ── Application settings ───────────────────────────────────────────────
      env {
        name  = "APP_BASE_URL"
        value = "https://${local.custom_domain_fqdn}"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name = "INGESTION_MODE"
        value = "hec"
      }
      env {
        name = "GEOIP_DB_PATH"
        value = "/app/data/GeoLite2-City.mmdb"
      }
      env {
        name = "DETECTION_CONFIDENCE_THRESHOLD"
        value = "0.7"
      }
      env {
        name = "QUERY_MAX_ROWS"
        value = "100000"
      }
      env {
        name = "QUERY_TIMEOUT_SECONDS"
        value = "30"
      }

      # ── Optional integrations ──────────────────────────────────────────────
      env {
        name = "MAXMIND_LICENSE_KEY"
        secret_name = "maxmind-license-key"
      }
      env {
        name = "INITIAL_ADMIN_LOGINS"
        secret_name = "initial-admin-logins"
      }

      # ── Azure Storage (audit/backup) ───────────────────────────────────────
      env {
        name = "AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "storage-connection-string"
      }
      env {
        name = "AZURE_AUDIT_CONTAINER"
        value = "pg-backups"
      }

      # ── SAML (disabled by default — set values to enable) ──────────────────
      env {
        name = "SAML_SP_CERT"
        value = ""
      }
      env {
        name = "SAML_SP_KEY"
        value = ""
      }
      env {
        name = "SAML_IDP_METADATA_URL"
        value = ""
      }

      liveness_probe {
        transport        = "HTTP"
        port             = 8000
        path             = "/health"
        initial_delay    = 15
        interval_seconds = 30
      }

      readiness_probe {
        transport        = "HTTP"
        port             = 8000
        path             = "/health"
        initial_delay    = 10
        interval_seconds = 10
      }
    }

    http_scale_rule {
      name                = "http-scale"
      concurrent_requests = "50"
    }
  }

  # Internal HTTP ingress — frontend and workers reach api on port 8000
  ingress {
    external_enabled = false
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  # ── Secrets ────────────────────────────────────────────────────────────────
  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "github-client-id"
    value = var.secret_github_client_id
  }
  secret {
    name = "github-client-secret"
    value = var.secret_github_client_secret
  }
  secret {
    name = "github-rules-token"
    value = var.secret_github_rules_token
  }
  secret {
    name = "github-app-private-key-pem"
    value = var.secret_github_app_private_key
  }
  secret {
    name = "maxmind-license-key"
    value = var.secret_maxmind_license_key
  }
  secret {
    name = "initial-admin-logins"
    value = var.secret_initial_admin_logins
  }
  secret {
    name  = "storage-connection-string"
    value = azurerm_storage_account.main.primary_connection_string
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

################################################################################
# H. Container App: frontend (React / nginx)
#    Scales 1–3 replicas based on concurrent HTTP requests.
#    External ingress — publicly accessible via ACA auto-generated FQDN
#    (and later via custom domain after cutover).
################################################################################

resource "azurerm_container_app" "frontend" {
  name                         = "frontend"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "frontend"
      image  = local.image_frontend
      cpu    = 0.25
      memory = "0.5Gi"

      liveness_probe {
        transport        = "HTTP"
        port             = 3001
        path             = "/"
        initial_delay    = 10
        interval_seconds = 30
      }

      readiness_probe {
        transport        = "HTTP"
        port             = 3001
        path             = "/"
        initial_delay    = 5
        interval_seconds = 10
      }
    }

    http_scale_rule {
      name                = "http-scale"
      concurrent_requests = "100"
    }
  }

  # External HTTP ingress — publicly reachable; custom domain applied at cutover
  ingress {
    external_enabled = true
    target_port      = 3001

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [azurerm_container_app.api]
}

################################################################################
# I. Container App: beat (Celery Beat scheduler — SINGLETON)
#    HARD LIMIT: max_replicas = 1. Running multiple beat instances causes
#    duplicate task scheduling. revision_mode = "Single" enforces this.
################################################################################

resource "azurerm_container_app" "beat" {
  name                         = "beat"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 1 # HARD LIMIT — never increase; duplicate beat = duplicate tasks

    container {
      name    = "beat"
      image   = local.image_worker
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["celery", "-A", "app.celery_app", "beat", "--scheduler", "celery.beat:PersistentScheduler", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "GITHUB_CLIENT_ID"
        secret_name = "github-client-id"
      }
      env {
        name = "GITHUB_CLIENT_SECRET"
        secret_name = "github-client-secret"
      }
      env {
        name = "GITHUB_RULES_REPO"
        value = var.secret_github_rules_repo
      }
      env {
        name = "GITHUB_RULES_TOKEN"
        secret_name = "github-rules-token"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }
    }
  }

  # No ingress — beat is internal-only
  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "github-client-id"
    value = var.secret_github_client_id
  }
  secret {
    name = "github-client-secret"
    value = var.secret_github_client_secret
  }
  secret {
    name = "github-rules-token"
    value = var.secret_github_rules_token
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [azurerm_container_app.valkey]
}

################################################################################
# J. Workers (5 Container Apps — scale to zero with KEDA Redis/Valkey scaler)
#
# Common pattern:
#   - min_replicas = 0 (scale-to-zero when queue is empty)
#   - KEDA custom scale rule triggers on Redis list depth
#   - authentication uses the valkey-password secret
################################################################################

# ── worker-ingestion ──────────────────────────────────────────────────────────

resource "azurerm_container_app" "worker_ingestion" {
  name                         = "worker-ingestion"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = var.worker_max_replicas.ingestion

    container {
      name    = "worker-ingestion"
      image   = local.image_worker
      cpu     = 0.5
      memory  = "1Gi"
      command = ["celery", "-A", "app.celery_app", "worker", "-Q", "ingestion", "-c", "4", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "INGESTION_MODE"
        value = "hec"
      }
      env {
        name = "MAXMIND_LICENSE_KEY"
        secret_name = "maxmind-license-key"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }
    }

    custom_scale_rule {
      name             = "redis-queue-ingestion"
      custom_rule_type = "redis"
      metadata = {
        address       = "valkey:6379"
        listName      = "ingestion"
        listLength    = tostring(var.celery_queue_scale_threshold)
        databaseIndex = "0"
        enableTLS     = "false"
      }
      authentication {
        secret_name       = "valkey-password"
        trigger_parameter = "password"
      }
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "valkey-password"
    value = var.secret_valkey_password
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "maxmind-license-key"
    value = var.secret_maxmind_license_key
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

# ── worker-detection ──────────────────────────────────────────────────────────

resource "azurerm_container_app" "worker_detection" {
  name                         = "worker-detection"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = var.worker_max_replicas.detection

    container {
      name    = "worker-detection"
      image   = local.image_worker
      cpu     = 0.5
      memory  = "1Gi"
      command = ["celery", "-A", "app.celery_app", "worker", "-Q", "detection", "-c", "8", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "DETECTION_CONFIDENCE_THRESHOLD"
        value = "0.7"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }

      # IdP enrichment — Okta
      env {
        name = "OKTA_ORG_URL"
        value = var.secret_okta_org_url
      }
      env {
        name = "OKTA_API_TOKEN"
        secret_name = "okta-api-token"
      }

      # IdP enrichment — Azure AD / Entra
      env {
        name = "AZURE_AD_TENANT_ID"
        value = var.secret_azure_ad_tenant_id
      }
      env {
        name = "AZURE_AD_CLIENT_ID"
        value = var.secret_azure_ad_client_id
      }
      env {
        name = "AZURE_AD_CLIENT_SECRET"
        secret_name = "azure-ad-client-secret"
      }

      # Notifications — Slack
      env {
        name = "SLACK_BOT_TOKEN"
        secret_name = "slack-bot-token"
      }

      # Notifications — SMTP
      env {
        name = "SMTP_HOST"
        value = var.secret_smtp_host
      }
      env {
        name = "SMTP_USERNAME"
        value = var.secret_smtp_username
      }
      env {
        name = "SMTP_PASSWORD"
        secret_name = "smtp-password"
      }

      # Ticketing — Jira
      env {
        name = "JIRA_URL"
        value = var.secret_jira_url
      }
      env {
        name = "JIRA_USERNAME"
        value = var.secret_jira_username
      }
      env {
        name = "JIRA_API_TOKEN"
        secret_name = "jira-api-token"
      }
    }

    custom_scale_rule {
      name             = "redis-queue-detection"
      custom_rule_type = "redis"
      metadata = {
        address       = "valkey:6379"
        listName      = "detection"
        listLength    = tostring(var.celery_queue_scale_threshold)
        databaseIndex = "0"
        enableTLS     = "false"
      }
      authentication {
        secret_name       = "valkey-password"
        trigger_parameter = "password"
      }
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "valkey-password"
    value = var.secret_valkey_password
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "okta-api-token"
    value = var.secret_okta_api_token
  }
  secret {
    name = "azure-ad-client-secret"
    value = var.secret_azure_ad_client_secret
  }
  secret {
    name = "slack-bot-token"
    value = var.secret_slack_bot_token
  }
  secret {
    name = "smtp-password"
    value = var.secret_smtp_password
  }
  secret {
    name = "jira-api-token"
    value = var.secret_jira_api_token
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

# ── worker-notification ───────────────────────────────────────────────────────

resource "azurerm_container_app" "worker_notification" {
  name                         = "worker-notification"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = var.worker_max_replicas.notification

    container {
      name    = "worker-notification"
      image   = local.image_worker
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["celery", "-A", "app.celery_app", "worker", "-Q", "notification", "-c", "2", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }

      # Notifications — Slack
      env {
        name = "SLACK_BOT_TOKEN"
        secret_name = "slack-bot-token"
      }

      # Notifications — SMTP
      env {
        name = "SMTP_HOST"
        value = var.secret_smtp_host
      }
      env {
        name = "SMTP_USERNAME"
        value = var.secret_smtp_username
      }
      env {
        name = "SMTP_PASSWORD"
        secret_name = "smtp-password"
      }
    }

    custom_scale_rule {
      name             = "redis-queue-notification"
      custom_rule_type = "redis"
      metadata = {
        address       = "valkey:6379"
        listName      = "notification"
        listLength    = tostring(var.celery_queue_scale_threshold)
        databaseIndex = "0"
        enableTLS     = "false"
      }
      authentication {
        secret_name       = "valkey-password"
        trigger_parameter = "password"
      }
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "valkey-password"
    value = var.secret_valkey_password
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "slack-bot-token"
    value = var.secret_slack_bot_token
  }
  secret {
    name = "smtp-password"
    value = var.secret_smtp_password
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

# ── worker-baseline ───────────────────────────────────────────────────────────

resource "azurerm_container_app" "worker_baseline" {
  name                         = "worker-baseline"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = var.worker_max_replicas.baseline

    container {
      name    = "worker-baseline"
      image   = local.image_worker
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["celery", "-A", "app.celery_app", "worker", "-Q", "baseline", "-c", "2", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }
    }

    custom_scale_rule {
      name             = "redis-queue-baseline"
      custom_rule_type = "redis"
      metadata = {
        address       = "valkey:6379"
        listName      = "baseline"
        listLength    = tostring(var.celery_queue_scale_threshold)
        databaseIndex = "0"
        enableTLS     = "false"
      }
      authentication {
        secret_name       = "valkey-password"
        trigger_parameter = "password"
      }
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "valkey-password"
    value = var.secret_valkey_password
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

# ── worker-sync ───────────────────────────────────────────────────────────────

resource "azurerm_container_app" "worker_sync" {
  name                         = "worker-sync"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = var.worker_max_replicas.sync

    container {
      name    = "worker-sync"
      image   = local.image_worker
      cpu     = 0.5
      memory  = "1Gi"
      # --pool=solo is required: GitHub App API calls are not safe with
      # pre-fork concurrency; solo pool runs tasks sequentially in one process.
      command = ["celery", "-A", "app.celery_app", "worker", "-Q", "github_sync", "--pool=solo", "--loglevel", "INFO"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
      env {
        name = "VALKEY_URL"
        secret_name = "valkey-url"
      }
      env {
        name = "SECRET_KEY"
        secret_name = "secret-key"
      }
      env {
        name = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }
      env {
        name = "LOG_LEVEL"
        value = "INFO"
      }

      # GitHub Enterprise Sync
      env {
        name = "GITHUB_APP_PRIVATE_KEY_PEM"
        secret_name = "github-app-private-key-pem"
      }
      env {
        name = "GITHUB_APP_ID"
        value = var.secret_github_app_id
      }
      env {
        name = "GITHUB_ENTERPRISE_SLUG"
        value = var.secret_github_enterprise_slug
      }
      env {
        name = "GITHUB_SYNC_ENABLED"
        value = "false"
      }
      env {
        name = "GITHUB_SYNC_INTERVAL_DAYS"
        value = "60"
      }
      env {
        name = "GITHUB_SYNC_ORGS"
        value = ""
      }
    }

    custom_scale_rule {
      name             = "redis-queue-sync"
      custom_rule_type = "redis"
      metadata = {
        address       = "valkey:6379"
        listName      = "github_sync"
        listLength    = tostring(var.celery_queue_scale_threshold)
        databaseIndex = "0"
        enableTLS     = "false"
      }
      authentication {
        secret_name       = "valkey-password"
        trigger_parameter = "password"
      }
    }
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }
  secret {
    name = "valkey-url"
    value = local.aca_valkey_url
  }
  secret {
    name = "valkey-password"
    value = var.secret_valkey_password
  }
  secret {
    name = "secret-key"
    value = var.secret_secret_key
  }
  secret {
    name = "encryption-key"
    value = var.secret_encryption_key
  }
  secret {
    name = "github-app-private-key-pem"
    value = var.secret_github_app_private_key
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [
    azurerm_container_app.db,
    azurerm_container_app.valkey,
  ]
}

################################################################################
# K. Container App Job: migrate (Alembic)
#    Manual trigger only — run before first deployment and after schema changes.
#    Run with: az containerapp job start \
#                --name <aca_migrate_job_name output> \
#                --resource-group <resource_group_name output>
################################################################################

resource "azurerm_container_app_job" "migrate" {
  name                         = "job-migrate-${local.name_prefix}"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  container_app_environment_id = azurerm_container_app_environment.main.id

  replica_timeout_in_seconds = 300
  replica_retry_limit        = 3

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "migrate"
      image   = local.image_api
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["alembic", "upgrade", "head"]

      env {
        name = "DATABASE_URL"
        secret_name = "db-url"
      }
    }
  }

  registry {
    server               = "ghcr.io"
    username             = var.ghcr_username
    password_secret_name = "ghcr-password"
  }

  secret {
    name = "ghcr-password"
    value = var.ghcr_token
  }
  secret {
    name = "db-url"
    value = local.aca_database_url
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags

  depends_on = [azurerm_container_app.db]
}

################################################################################
# L. DNS — Cutover records
#
# TXT record: created immediately for domain ownership verification.
#   Azure must verify domain ownership before issuing a managed TLS cert.
#   The A record → CNAME swap happens at cutover (aca_cutover_complete = true).
#
# CNAME record: count-gated. Created only when aca_cutover_complete = true.
#   Before cutover, the existing A record in dns.tf serves traffic to the VM.
#   At cutover, set aca_cutover_complete = true then terraform apply.
#   The A record in dns.tf is count-gated inversely (see dns.tf).
################################################################################

resource "azurerm_dns_txt_record" "aca_domain_verification" {
  count               = var.dns_zone_name != "" ? 1 : 0
  name                = "asuid.${var.dns_record_name}"
  zone_name           = var.dns_zone_name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = 300

  record {
    value = azurerm_container_app_environment.main.custom_domain_verification_id
  }

  tags = local.common_tags
}

resource "azurerm_dns_cname_record" "aca_frontend" {
  count               = var.dns_zone_name != "" && var.aca_cutover_complete ? 1 : 0
  name                = var.dns_record_name
  zone_name           = var.dns_zone_name
  resource_group_name = var.dns_zone_resource_group
  ttl                 = 300
  record              = azurerm_container_app.frontend.ingress[0].fqdn

  tags = local.common_tags
}

################################################################################
# M. Outputs (also see outputs.tf for the canonical output file)
################################################################################

output "aca_environment_fqdn" {
  value       = azurerm_container_app_environment.main.default_domain
  description = "Default domain for the Container Apps environment (for smoke testing before cutover)"
}

output "aca_frontend_fqdn" {
  value       = azurerm_container_app.frontend.ingress[0].fqdn
  description = "Auto-generated FQDN of the frontend Container App (before custom domain)"
}

output "aca_migrate_job_name" {
  value       = azurerm_container_app_job.migrate.name
  description = "Run with: az containerapp job start --name <value> --resource-group rg-octowatch-dev"
}

output "premium_storage_name" {
  value       = azurerm_storage_account.premium.name
  description = "Premium storage account name for Azure Files shares"
}
