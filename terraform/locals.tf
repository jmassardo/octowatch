################################################################################
# OctoWatch — Local Values
################################################################################

locals {
  # Shared name prefix used across all resource names.
  name_prefix = "octowatch-${var.environment}"

  # Tags applied to every resource.
  common_tags = merge(
    {
      application = "octowatch"
      environment = var.environment
      managed_by  = "terraform"
      owner       = var.owner_tag
    },
    var.extra_tags
  )

  # Effective TLS domain — priority order:
  #   1. Existing Azure DNS zone record (dns_zone_name set)
  #   2. Explicit custom domain     (tls_domain set)
  #   3. Azure public IP FQDN       (fallback)
  tls_domain = (
    var.dns_zone_name != ""
    ? "${var.dns_record_name}.${var.dns_zone_name}"
    : var.tls_domain != ""
    ? var.tls_domain
    : "${var.dns_label}.${var.location}.cloudapp.azure.com"
  )

  # Key Vault names must be globally unique, 3-24 chars, alphanumeric + hyphens.
  key_vault_name = "kv-oct-${var.environment}-${random_string.kv_suffix.result}"

  # Modified docker-compose volume definitions that bind to the data disk.
  # These replace the anonymous volume declarations in the source compose file.
  compose_volume_override = <<-VOLUMES
volumes:
  pg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/octowatch-data/pg_data
  valkey_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/octowatch-data/valkey_data
VOLUMES
}

locals {
  aks_database_url = "postgresql+asyncpg://app_rw:${var.secret_postgres_password}@octowatch-postgresql.octowatch.svc.cluster.local:5432/auditlogs"
  aks_valkey_url   = "redis://:${var.secret_valkey_password}@octowatch-valkey-master.octowatch.svc.cluster.local:6379/0"
}
