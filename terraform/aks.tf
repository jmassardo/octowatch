# terraform/aks.tf
# AKS cluster + supporting infrastructure for OctoWatch migration
# 
# Two-phase apply required on first run:
#   Phase 1: terraform apply -target=azurerm_subnet.aks -target=azurerm_network_security_group.aks -target=azurerm_kubernetes_cluster.main
#   Phase 2: terraform apply

provider "kubernetes" {
  host                   = var.enable_aks ? azurerm_kubernetes_cluster.main[0].kube_config[0].host : "https://localhost"
  client_certificate     = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].client_certificate) : ""
  client_key             = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].client_key) : ""
  cluster_ca_certificate = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].cluster_ca_certificate) : ""
}

provider "helm" {
  kubernetes {
    host                   = var.enable_aks ? azurerm_kubernetes_cluster.main[0].kube_config[0].host : "https://localhost"
    client_certificate     = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].client_certificate) : ""
    client_key             = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].client_key) : ""
    cluster_ca_certificate = var.enable_aks ? base64decode(azurerm_kubernetes_cluster.main[0].kube_config[0].cluster_ca_certificate) : ""
  }
}

# AKS Subnet — 10.0.4.0/22 (avoids VM 10.0.0.0/24 and ACA 10.0.2.0/23)
resource "azurerm_subnet" "aks" {
  count = var.enable_aks ? 1 : 0
  name                 = "snet-aks-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.4.0/22"]

  # Microsoft.KeyVault service endpoint enables the VNet firewall rule on
  # kv-oct-dev-i6iv6t that allows pods to pull secrets from Key Vault.
  # Applied live on 2026-04-23 via: az network vnet subnet update
  #   --service-endpoints Microsoft.KeyVault
  service_endpoints = ["Microsoft.KeyVault"]
}

# NSG for AKS subnet
resource "azurerm_network_security_group" "aks" {
  count = var.enable_aks ? 1 : 0
  name                = "nsg-aks-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  security_rule {
    name                       = "AllowHttpsInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHttpInbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowKubeletVnet"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "10250"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowLBNodePorts"
    priority                   = 150
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "30000-32767"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyAllInternetInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "aks" {
  count = var.enable_aks ? 1 : 0
  subnet_id                 = azurerm_subnet.aks[0].id
  network_security_group_id = azurerm_network_security_group.aks[0].id
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  count = var.enable_aks ? 1 : 0
  name                = "aks-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "aks-${local.name_prefix}"
  sku_tier            = "Standard"
  tags                = local.common_tags

  # Legacy default pool — kept at minimum size because AKS requires a default
  # node pool and zones cannot be added after creation. The real system workloads
  # run on system4 (zone-redundant). This pool will be removed when the cluster
  # is next recreated.
  default_node_pool {
    name                         = "system3"
    vm_size                      = var.aks_node_size
    min_count                    = 1
    max_count                    = 1
    auto_scaling_enabled         = true
    vnet_subnet_id               = azurerm_subnet.aks[0].id
    os_disk_size_gb              = 128
    os_disk_type                 = "Managed"
    only_critical_addons_enabled = false

    upgrade_settings {
      max_surge                     = "10%"
      drain_timeout_in_minutes      = 0
      node_soak_duration_in_minutes = 0
      undrainable_node_behavior     = "Schedule"
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  network_profile {
    network_plugin = "kubenet"
    pod_cidr       = "10.244.0.0/16"
    service_cidr   = "10.245.0.0/16"
    dns_service_ip = "10.245.0.10"
  }

  # ── Security: Azure Policy add-on ─────────────────────────────────────────────
  # Enforces Azure Policy for Kubernetes (Gatekeeper-based). Applied live on
  # 2026-04-23 via: az aks enable-addons --addons azure-policy
  azure_policy_enabled = true

  # ── Security: Key Vault Secrets Store CSI Driver ───────────────────────────────
  # Allows pods to mount Azure Key Vault secrets as volumes. Applied live on
  # 2026-04-23 via: az aks enable-addons --addons azure-keyvault-secrets-provider
  key_vault_secrets_provider {
    secret_rotation_enabled  = false
    secret_rotation_interval = "2m"
  }

  # ── Security: API Server Authorized IP Ranges ──────────────────────────────────
  # Restricts access to the Kubernetes API server to known admin CIDRs and
  # GitHub Actions runner IP ranges. Applied live on 2026-04-23.
  # IMPORTANT: AKS rejects private CIDRs (e.g. 10.x.x.x) in this list — node-to-
  # control-plane traffic is internal and not subject to this allowlist.
  # Update var.aks_api_server_authorized_ip_ranges in terraform.tfvars when admin
  # IPs change (e.g. new office, new CI/CD provider IPs).
  # NOTE: azurerm v4.x uses api_server_access_profile block (top-level
  # api_server_authorized_ip_ranges was removed in v4.0).
  api_server_access_profile {
    authorized_ip_ranges = var.aks_api_server_authorized_ip_ranges
  }

  # ── Security: Private Cluster (future) ────────────────────────────────────────
  # Private clusters can ONLY be configured at cluster creation time — they cannot
  # be retrofitted to an existing cluster.
  # To enable private cluster: set aks_private_cluster=true in terraform.tfvars
  # and RECREATE the cluster (terraform destroy + apply or use blue-green approach).
  # When private_cluster_enabled=true, the API server FQDN is only resolvable from
  # within the VNet; CI/CD runners must use a self-hosted runner or VPN.
  private_cluster_enabled             = var.aks_private_cluster
  private_cluster_public_fqdn_enabled = !var.aks_private_cluster

  # ── Security: KMS etcd Encryption (future) ────────────────────────────────────
  # Encrypts Kubernetes secrets at rest in etcd using a customer-managed key in
  # Azure Key Vault. Requires:
  #   1. A Key Vault key (RSA 2048/3072/4096 or EC P-256/P-384)
  #   2. Key Vault access from the cluster's identity (key unwrap/wrap permissions)
  #   3. The key_vault_key_id set in var.aks_kms_key_id
  # Cannot be easily disabled once enabled. Set aks_kms_key_id in terraform.tfvars
  # to activate. Leave empty (default) to skip.
  dynamic "key_management_service" {
    for_each = var.aks_kms_key_id != "" ? [1] : []
    content {
      key_vault_key_id         = var.aks_kms_key_id
      key_vault_network_access = "Private"
    }
  }
}

# ── Zone-Redundant System Pool ────────────────────────────────────────────────
# Primary system pool spread across availability zones 1, 2, 3 for resilience
# against host/rack/zone failures. Replaces the non-zonal system3 default pool.
resource "azurerm_kubernetes_cluster_node_pool" "system4" {
  count = var.enable_aks ? 1 : 0
  name                  = "system4"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main[0].id
  vm_size               = var.aks_node_size
  vnet_subnet_id        = azurerm_subnet.aks[0].id
  mode                  = "System"
  zones                 = ["1", "2", "3"]

  auto_scaling_enabled = true
  min_count            = 3
  max_count            = 6

  upgrade_settings {
    max_surge                     = "10%"
    drain_timeout_in_minutes      = 0
    node_soak_duration_in_minutes = 0
    undrainable_node_behavior     = "Schedule"
  }
}

# ── Zone-Redundant Worker Pool ───────────────────────────────────────────────
# Runs application workloads (API, frontend, workers, databases).
# Spread across availability zones 1, 2, 3 for resilience. Uses D4s_v4
# (non-burstable) instead of the previous B4ms to avoid CPU credit issues.
resource "azurerm_kubernetes_cluster_node_pool" "pool3" {
  count = var.enable_aks ? 1 : 0
  name                  = "pool3"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main[0].id
  vm_size               = var.aks_node_size
  vnet_subnet_id        = azurerm_subnet.aks[0].id
  mode                  = "User"
  zones                 = ["1", "2", "3"]

  auto_scaling_enabled = true
  min_count            = 3
  max_count            = 6
  scale_down_mode      = "Delete"

  upgrade_settings {
    max_surge                     = "10%"
    drain_timeout_in_minutes      = 0
    node_soak_duration_in_minutes = 0
    undrainable_node_behavior     = "Schedule"
  }
}

# ── NAT Gateway — static egress IP for AKS nodes ──────────────────────────────
# Gives all AKS nodes a single, stable public egress IP. Benefits:
#   1. AKS pods always leave via a known IP → add it permanently to API server
#      authorized ranges so GitHub Actions / admin tools running in-cluster work.
#   2. External services (GitHub webhooks, Slack, Jira) can allowlist one IP.
#   3. Eliminates the "which Azure egress IP am I today?" problem.

resource "azurerm_public_ip" "aks_egress" {
  count = var.enable_aks ? 1 : 0
  name                = "pip-aks-egress-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  allocation_method   = "Static"
  zones               = ["1", "2", "3"]
  tags                = merge(local.common_tags, { purpose = "aks-nat-egress" })
}

resource "azurerm_nat_gateway" "aks" {
  count = var.enable_aks ? 1 : 0
  name                    = "nat-aks-${local.name_prefix}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  sku_name                = "Standard"
  idle_timeout_in_minutes = 10
  zones                   = ["1", "2", "3"]
  tags                    = local.common_tags
}

resource "azurerm_nat_gateway_public_ip_association" "aks" {
  count = var.enable_aks ? 1 : 0
  nat_gateway_id       = azurerm_nat_gateway.aks[0].id
  public_ip_address_id = azurerm_public_ip.aks_egress[0].id
}

resource "azurerm_subnet_nat_gateway_association" "aks" {
  count = var.enable_aks ? 1 : 0
  subnet_id      = azurerm_subnet.aks[0].id
  nat_gateway_id = azurerm_nat_gateway.aks[0].id
}

# Kubernetes namespace
resource "kubernetes_namespace" "octowatch" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name = "octowatch"
  }
  depends_on = [azurerm_kubernetes_cluster.main]
}

# GHCR pull secret
resource "kubernetes_secret" "ghcr_pull_secret" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "ghcr-pull-secret"
    namespace = kubernetes_namespace.octowatch[0].metadata[0].name
  }
  type = "kubernetes.io/dockerconfigjson"
  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "ghcr.io" = {
          username = var.ghcr_username
          password = var.ghcr_token
          auth     = base64encode("${var.ghcr_username}:${var.ghcr_token}")
        }
      }
    })
  }
}

# Main application secrets
resource "kubernetes_secret" "octowatch_secrets" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "octowatch-secrets"
    namespace = kubernetes_namespace.octowatch[0].metadata[0].name
    annotations = {
      "helm.sh/resource-policy" = "keep"
    }
  }
  data = {
    "secret-key"                      = var.secret_secret_key
    "database-url"                    = local.aks_database_url
    "valkey-url"                      = local.aks_valkey_url
    "valkey-password"                 = var.secret_valkey_password
    "github-client-id"                = var.secret_github_client_id
    "github-client-secret"            = var.secret_github_client_secret
    "github-rules-token"              = var.secret_github_rules_token
    "slack-bot-token"                 = var.secret_slack_bot_token
    "smtp-host"                       = var.secret_smtp_host
    "smtp-username"                   = var.secret_smtp_username
    "smtp-password"                   = var.secret_smtp_password
    "jira-url"                        = var.secret_jira_url
    "jira-username"                   = var.secret_jira_username
    "jira-api-token"                  = var.secret_jira_api_token
    "github-app-id"                   = var.secret_github_app_id
    "github-enterprise-slug"          = var.secret_github_enterprise_slug
    "maxmind-license-key"             = var.secret_maxmind_license_key
    "okta-org-url"                    = var.secret_okta_org_url
    "okta-api-token"                  = var.secret_okta_api_token
    "encryption-key"                  = var.secret_encryption_key
    "initial-admin-logins"            = var.secret_initial_admin_logins
    "app-base-url"                    = "https://octowatch.jmassardo.azure.csa-github.com"
    "azure-storage-connection-string" = var.secret_azure_storage_connection_string
  }
}

# PostgreSQL credentials (for Bitnami postgresql chart)
resource "kubernetes_secret" "octowatch_db_secret" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "octowatch-db-secret"
    namespace = kubernetes_namespace.octowatch[0].metadata[0].name
    annotations = {
      "helm.sh/resource-policy" = "keep"
    }
  }
  data = {
    "postgres-password" = var.secret_postgres_password
    "app-password"      = var.secret_postgres_password
    "password"          = var.secret_postgres_password
  }
}

# Valkey credentials (for Bitnami valkey chart)
resource "kubernetes_secret" "octowatch_valkey_secret" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "octowatch-valkey-secret"
    namespace = kubernetes_namespace.octowatch[0].metadata[0].name
    annotations = {
      "helm.sh/resource-policy" = "keep"
    }
  }
  data = {
    "valkey-password" = var.secret_valkey_password
  }
}

# GitHub App private key
resource "kubernetes_secret" "octowatch_github_app_key" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "octowatch-github-app-key"
    namespace = kubernetes_namespace.octowatch[0].metadata[0].name
    annotations = {
      "helm.sh/resource-policy" = "keep"
    }
  }
  data = {
    "github-app-key.pem" = var.secret_github_app_private_key
  }
}

# ingress-nginx
resource "helm_release" "ingress_nginx" {
  count = var.enable_aks ? 1 : 0
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = "4.10.1"
  namespace        = "ingress-nginx"
  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "controller.service.loadBalancerIP"
    value = ""
  }

  set {
    name  = "controller.replicaCount"
    value = "1"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# cert-manager
resource "helm_release" "cert_manager" {
  count = var.enable_aks ? 1 : 0
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = "1.14.5"
  namespace        = "cert-manager"
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  depends_on = [azurerm_kubernetes_cluster.main]
}

# KEDA
resource "helm_release" "keda" {
  count = var.enable_aks ? 1 : 0
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  version          = "2.14.2"
  namespace        = "keda"
  create_namespace = true

  depends_on = [azurerm_kubernetes_cluster.main]
}

# ArgoCD
resource "helm_release" "argocd" {
  count = var.enable_aks ? 1 : 0
  name             = "argo-cd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "6.7.14"
  namespace        = "argocd"
  create_namespace = true

  set {
    name  = "configs.secret.argocdServerAdminPassword"
    value = bcrypt(var.argocd_admin_password)
  }

  set {
    name  = "server.ingress.enabled"
    value = "true"
  }

  set {
    name  = "server.ingress.ingressClassName"
    value = "nginx"
  }

  set {
    name  = "server.ingress.hostname"
    value = "argocd.${local.tls_domain}"
  }

  set {
    name  = "server.ingress.tls"
    value = "true"
  }

  set {
    name  = "configs.params.server\\.insecure"
    value = "true"
  }

  depends_on = [helm_release.ingress_nginx, helm_release.cert_manager]
}

# ArgoCD Image Updater
resource "helm_release" "argocd_image_updater" {
  count = var.enable_aks ? 1 : 0
  name       = "argocd-image-updater"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-image-updater"
  version    = "0.9.6"
  namespace  = "argocd"

  set {
    name  = "config.registries[0].name"
    value = "ghcr"
  }

  set {
    name  = "config.registries[0].api_url"
    value = "https://ghcr.io"
  }

  set {
    name  = "config.registries[0].credentials"
    value = "secret:argocd/argocd-image-updater-secret#ghcr-token"
  }

  set {
    name  = "config.registries[0].default"
    value = "true"
  }

  depends_on = [helm_release.argocd]
}

# ArgoCD Image Updater secret (GHCR token + git PAT for writeback)
resource "kubernetes_secret" "argocd_image_updater_secret" {
  count = var.enable_aks ? 1 : 0
  metadata {
    name      = "argocd-image-updater-secret"
    namespace = "argocd"
  }
  data = {
    "ghcr-token" = "Bearer ${var.ghcr_token}"
    "git.token"  = var.argocd_github_pat
  }
  depends_on = [helm_release.argocd]
}

# Let's Encrypt ClusterIssuer
resource "kubernetes_manifest" "letsencrypt_prod_issuer" {
  count = var.enable_aks ? 1 : 0
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-prod"
    }
    spec = {
      acme = {
        email  = var.letsencrypt_email
        server = "https://acme-v02.api.letsencrypt.org/directory"
        privateKeySecretRef = {
          name = "letsencrypt-prod-private-key"
        }
        solvers = [
          {
            http01 = {
              ingress = {
                class = "nginx"
              }
            }
          }
        ]
      }
    }
  }
  depends_on = [helm_release.cert_manager]
}
