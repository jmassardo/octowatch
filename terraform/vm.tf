################################################################################
# OctoWatch — Virtual Machine
# Includes: managed data disk, Linux VM, disk attachment,
#           cloud-init config data source, optional auto-shutdown schedule.
################################################################################

# ── Managed Data Disk ──────────────────────────────────────────────────────────
# Premium SSD attached at LUN 0; cloud-init formats it as ext4 and mounts it
# at /mnt/octowatch-data. All persistent Docker volumes bind-mount here.

resource "azurerm_managed_disk" "data" {
  name                 = "disk-${local.name_prefix}-data"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  storage_account_type = "Premium_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_size_gb
  tags                 = local.common_tags
}

# ── Cloud-Init Configuration ───────────────────────────────────────────────────
# Rendered as gzip+base64 for custom_data. Two template files are used:
#   1. docker-compose.yml.tpl — compose content with bind-mount volumes and GHCR images.
#      Base64-encoded before injection so the Terraform template engine does not
#      need to escape the many ${...} references inside the compose file.
#   2. cloud-init.yaml.tpl — main cloud-init config referencing the above.

data "cloudinit_config" "main" {
  gzip          = true
  base64_encode = true

  part {
    filename     = "cloud-init.yaml"
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/templates/cloud-init.yaml.tpl", {
      # Identity & Key Vault (kept for potential future use)
      managed_identity_client_id = azurerm_user_assigned_identity.vm.client_id
      key_vault_name             = local.key_vault_name

      # TLS
      tls_mode      = var.tls_mode
      tls_domain    = local.tls_domain
      certbot_email = var.certbot_email

      # GHCR
      ghcr_username  = var.ghcr_username
      ghcr_token     = var.ghcr_token
      ghcr_owner     = var.ghcr_owner
      ghcr_image_tag = var.ghcr_image_tag

      # Misc
      environment          = var.environment
      storage_account_name = azurerm_storage_account.main.name
      # Storage account key: used for backup uploads (avoids RBAC role assignment).
      storage_account_key = azurerm_storage_account.main.primary_access_key

      # Only secret_github_app_private_key is needed directly in cloud-init
      # (to optionally write the key file). All other secrets go via env_file_b64.
      secret_github_app_private_key = var.secret_github_app_private_key

      # Secrets rendered into .env at provision time; base64-encoded so YAML
      # literal blocks don't need to handle KEY=VALUE indentation.
      env_file_b64 = base64encode(templatefile("${path.module}/templates/env.tpl", {
        secret_database_url           = var.secret_database_url
        secret_secret_key             = var.secret_secret_key
        secret_encryption_key         = var.secret_encryption_key
        secret_valkey_url             = var.secret_valkey_url
        secret_valkey_password        = var.secret_valkey_password
        secret_postgres_user          = var.secret_postgres_user
        secret_postgres_password      = var.secret_postgres_password
        secret_postgres_db            = var.secret_postgres_db
        secret_github_client_id       = var.secret_github_client_id
        secret_github_client_secret   = var.secret_github_client_secret
        secret_github_rules_repo      = var.secret_github_rules_repo
        secret_github_rules_token     = var.secret_github_rules_token
        secret_initial_admin_logins   = var.secret_initial_admin_logins
        secret_app_base_url           = var.secret_app_base_url
        secret_github_app_id          = var.secret_github_app_id
        secret_github_app_private_key = var.secret_github_app_private_key
        secret_github_enterprise_slug = var.secret_github_enterprise_slug
        secret_maxmind_license_key    = var.secret_maxmind_license_key
        secret_okta_org_url           = var.secret_okta_org_url
        secret_okta_api_token         = var.secret_okta_api_token
        secret_azure_ad_tenant_id     = var.secret_azure_ad_tenant_id
        secret_azure_ad_client_id     = var.secret_azure_ad_client_id
        secret_azure_ad_client_secret = var.secret_azure_ad_client_secret
        secret_slack_bot_token        = var.secret_slack_bot_token
        secret_smtp_host              = var.secret_smtp_host
        secret_smtp_username          = var.secret_smtp_username
        secret_smtp_password          = var.secret_smtp_password
        secret_jira_url               = var.secret_jira_url
        secret_jira_username          = var.secret_jira_username
        secret_jira_api_token         = var.secret_jira_api_token
      }))

      # Pre-rendered, base64-encoded docker-compose.yml with GHCR image names
      # and bind-mount volumes substituted. Using b64 avoids escaping the many
      # ${VAR} references inside the compose file.
      compose_b64 = base64encode(
        templatefile("${path.module}/templates/docker-compose.yml.tpl", {
          ghcr_owner     = var.ghcr_owner
          ghcr_image_tag = var.ghcr_image_tag
        })
      )

      # nginx.conf read directly from the repository (no template vars needed).
      nginx_conf_b64 = base64encode(file("${path.module}/../nginx/nginx.conf"))
    })
  }
}

# ── Linux Virtual Machine ──────────────────────────────────────────────────────

resource "azurerm_linux_virtual_machine" "main" {
  name                = "vm-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size

  # Admin user — password auth is disabled; key-only.
  admin_username                  = "octowatch"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "octowatch"
    public_key = var.ssh_public_key
  }

  # Attach to the NIC created in networking.tf.
  network_interface_ids = [azurerm_network_interface.main.id]

  # User-assigned managed identity for Key Vault and Storage access.
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  # OS disk: Premium SSD, 128 GiB. ReadWrite caching improves sequential I/O.
  os_disk {
    name                 = "osdisk-${local.name_prefix}"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 128
  }

  # Ubuntu 24.04 LTS — latest patch release.
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # cloud-init rendered by the data source above.
  custom_data = data.cloudinit_config.main.rendered

  # Boot diagnostics stored in the managed storage account.
  boot_diagnostics {
    storage_account_uri = azurerm_storage_account.main.primary_blob_endpoint
  }

  tags = local.common_tags

  # Changing custom_data requires VM replacement (Azure limitation).
  # Application updates (new image versions) are handled by the deploy pipeline
  # via SSH + docker compose pull, NOT by re-provisioning the VM.
  lifecycle {
    ignore_changes = [custom_data]
  }
}

# ── Data Disk Attachment ───────────────────────────────────────────────────────

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.main.id
  lun                = 0
  caching            = "ReadWrite"
}

# ── Optional: Auto-Shutdown Schedule ──────────────────────────────────────────
# Useful in dev/staging to reduce costs. Disabled in production by default.

resource "azurerm_dev_test_global_vm_shutdown_schedule" "main" {
  count = var.enable_auto_shutdown ? 1 : 0

  virtual_machine_id = azurerm_linux_virtual_machine.main.id
  location           = azurerm_resource_group.main.location
  enabled            = true

  daily_recurrence_time = var.auto_shutdown_time
  timezone              = "UTC"

  notification_settings {
    enabled = false
  }

  tags = local.common_tags
}
