# terraform/aks.tf
# AKS cluster + supporting infrastructure for OctoWatch migration
# 
# Two-phase apply required on first run:
#   Phase 1: terraform apply -target=azurerm_subnet.aks -target=azurerm_network_security_group.aks -target=azurerm_kubernetes_cluster.main
#   Phase 2: terraform apply

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.main.kube_config[0].host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config[0].cluster_ca_certificate)
  }
}

# AKS Subnet — 10.0.4.0/22 (avoids VM 10.0.0.0/24 and ACA 10.0.2.0/23)
resource "azurerm_subnet" "aks" {
  name                 = "snet-aks-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.4.0/22"]
}

# NSG for AKS subnet
resource "azurerm_network_security_group" "aks" {
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
  subnet_id                 = azurerm_subnet.aks.id
  network_security_group_id = azurerm_network_security_group.aks.id
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "aks-${local.name_prefix}"
  sku_tier            = "Free"
  tags                = local.common_tags

  default_node_pool {
    name                         = "system"
    vm_size                      = var.aks_node_size
    min_count                    = 1
    max_count                    = 3
    auto_scaling_enabled         = true
    vnet_subnet_id               = azurerm_subnet.aks.id
    os_disk_size_gb              = 128
    os_disk_type                 = "Managed"
    only_critical_addons_enabled = false
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
}

# Kubernetes namespace
resource "kubernetes_namespace" "octowatch" {
  metadata {
    name = "octowatch"
  }
  depends_on = [azurerm_kubernetes_cluster.main]
}

# GHCR pull secret
resource "kubernetes_secret" "ghcr_pull_secret" {
  metadata {
    name      = "ghcr-pull-secret"
    namespace = kubernetes_namespace.octowatch.metadata[0].name
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
  metadata {
    name      = "octowatch-secrets"
    namespace = kubernetes_namespace.octowatch.metadata[0].name
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
    "azure-storage-connection-string" = azurerm_storage_account.main.primary_connection_string
  }
}

# PostgreSQL credentials (for Bitnami postgresql chart)
resource "kubernetes_secret" "octowatch_db_secret" {
  metadata {
    name      = "octowatch-db-secret"
    namespace = kubernetes_namespace.octowatch.metadata[0].name
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
  metadata {
    name      = "octowatch-valkey-secret"
    namespace = kubernetes_namespace.octowatch.metadata[0].name
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
  metadata {
    name      = "octowatch-github-app-key"
    namespace = kubernetes_namespace.octowatch.metadata[0].name
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
