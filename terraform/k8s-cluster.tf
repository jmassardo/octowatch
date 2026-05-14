################################################################################
# OctoWatch — Self-Managed Kubernetes Cluster
#
# Provisions a 3-node kubeadm Kubernetes cluster plus a dedicated management VM.
# The management VM is the sole admin entry point (bastion, CI runner, kubectl).
# K8s nodes have NO public IPs — all admin traffic flows through the mgmt subnet.
#
# Architecture:
#   Management subnet (10.0.10.0/28) — 1 bastion/admin VM with public IP
#   K8s cluster subnet (10.0.8.0/24)  — 3 nodes (1 CP + 2 workers), no public IPs
#   Azure Standard LB               — public IP for HTTP/S app traffic only
#
# This file is additive — it does NOT modify any existing AKS, ACA, or VM resources.
################################################################################

locals {
  k8s_node_ips = ["10.0.8.10", "10.0.8.11", "10.0.8.12"]
  k8s_mgmt_ip  = "10.0.10.4"
}

################################################################################
# A. Networking — Subnets + NSGs
################################################################################

# ── Management Subnet (bastion VM) ────────────────────────────────────────────

resource "azurerm_subnet" "k8s_mgmt" {
  name                 = "snet-mgmt-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.10.0/28"]
}

resource "azurerm_network_security_group" "k8s_mgmt" {
  name                = "nsg-mgmt-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  security_rule {
    name                       = "AllowSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.ssh_source_cidr
    destination_address_prefix = "*"
    description                = "SSH from trusted CIDR only."
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
    description                = "Deny all unlisted inbound traffic."
  }
}

resource "azurerm_subnet_network_security_group_association" "k8s_mgmt" {
  subnet_id                 = azurerm_subnet.k8s_mgmt.id
  network_security_group_id = azurerm_network_security_group.k8s_mgmt.id
}

# ── K8s Cluster Subnet ───────────────────────────────────────────────────────

resource "azurerm_subnet" "k8s_cluster" {
  name                 = "snet-k8s-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.8.0/24"]
}

resource "azurerm_network_security_group" "k8s_cluster" {
  name                = "nsg-k8s-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  # ── Inbound from Management Subnet ─────────────────────────────────────────

  security_rule {
    name                       = "AllowSSHFromMgmt"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "10.0.10.0/28"
    destination_address_prefix = "*"
    description                = "SSH from management subnet only."
  }

  security_rule {
    name                       = "AllowK8sAPIFromMgmt"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "6443"
    source_address_prefix      = "10.0.10.0/28"
    destination_address_prefix = "*"
    description                = "Kubernetes API from management subnet."
  }

  # ── Inbound from Cluster Subnet (inter-node) ──────────────────────────────

  security_rule {
    name                       = "AllowKubeletCluster"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "10250"
    source_address_prefixes    = ["10.0.8.0/24", "10.0.10.0/28"]
    destination_address_prefix = "*"
    description                = "Kubelet API from cluster + management subnets."
  }

  security_rule {
    name                       = "AllowEtcdCluster"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "2379-2380"
    source_address_prefix      = "10.0.8.0/24"
    destination_address_prefix = "*"
    description                = "etcd client + peer from cluster subnet."
  }

  security_rule {
    name                       = "AllowFlannelVXLAN"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "8472"
    source_address_prefix      = "10.0.8.0/24"
    destination_address_prefix = "*"
    description                = "Flannel VXLAN overlay traffic between nodes."
  }

  # ── Inbound from Internet (via Load Balancer) ─────────────────────────────

  security_rule {
    name                       = "AllowHTTPFromLB"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
    description                = "HTTP traffic via Azure LB (ingress-nginx hostPort)."
  }

  security_rule {
    name                       = "AllowHTTPSFromLB"
    priority                   = 210
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
    description                = "HTTPS traffic via Azure LB (ingress-nginx hostPort)."
  }

  # ── Allow Azure LB health probes ────────────────────────────────────────────

  security_rule {
    name                       = "AllowAzureLBProbes"
    priority                   = 250
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
    description                = "Azure LB health probes."
  }

  # ── Allow K8s API from cluster subnet (workers → CP) ──────────────────────

  security_rule {
    name                       = "AllowK8sAPIFromCluster"
    priority                   = 115
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "6443"
    source_address_prefix      = "10.0.8.0/24"
    destination_address_prefix = "*"
    description                = "Kubernetes API from cluster subnet (workers to CP)."
  }

  # ── Deny all other inbound traffic ────────────────────────────────────────
  # Priority 4000 overrides Azure's default AllowVNetInBound (65000).

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
    description                = "Deny all unlisted inbound (overrides default AllowVNetInBound)."
  }
}

resource "azurerm_subnet_network_security_group_association" "k8s_cluster" {
  subnet_id                 = azurerm_subnet.k8s_cluster.id
  network_security_group_id = azurerm_network_security_group.k8s_cluster.id
}

################################################################################
# B. Management VM — Bastion / Admin / CI Runner
################################################################################

resource "azurerm_public_ip" "k8s_mgmt" {
  name                = "pip-mgmt-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  allocation_method   = "Static"
  tags                = merge(local.common_tags, { purpose = "k8s-management" })
}

resource "azurerm_network_interface" "k8s_mgmt" {
  name                = "nic-mgmt-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig-mgmt"
    subnet_id                     = azurerm_subnet.k8s_mgmt.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.k8s_mgmt_ip
    public_ip_address_id          = azurerm_public_ip.k8s_mgmt.id
  }
}

resource "azurerm_network_interface_security_group_association" "k8s_mgmt" {
  network_interface_id      = azurerm_network_interface.k8s_mgmt.id
  network_security_group_id = azurerm_network_security_group.k8s_mgmt.id
}

data "cloudinit_config" "k8s_mgmt" {
  gzip          = true
  base64_encode = true

  part {
    filename     = "cloud-init.yaml"
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/templates/cloud-init-mgmt.yaml.tpl", {
      environment          = var.environment
      control_plane_ip     = local.k8s_node_ips[0]
      k8s_node_ips         = local.k8s_node_ips
      storage_account_name = azurerm_storage_account.main.name
      storage_account_key  = azurerm_storage_account.main.primary_access_key
      ghcr_username        = var.ghcr_username
      ghcr_token           = var.ghcr_token
    })
  }
}

resource "azurerm_linux_virtual_machine" "k8s_mgmt" {
  name                = "vm-mgmt-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.k8s_mgmt_vm_size

  admin_username                  = "octowatch"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "octowatch"
    public_key = var.ssh_public_key
  }

  network_interface_ids = [azurerm_network_interface.k8s_mgmt.id]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  os_disk {
    name                 = "osdisk-mgmt-${local.name_prefix}"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = data.cloudinit_config.k8s_mgmt.rendered

  boot_diagnostics {
    storage_account_uri = azurerm_storage_account.main.primary_blob_endpoint
  }

  tags = merge(local.common_tags, { role = "k8s-management" })

  lifecycle {
    ignore_changes = [custom_data]
  }
}

################################################################################
# C. K8s Cluster Nodes — 1 Control-Plane + 2 Workers
################################################################################

# ── NICs (no public IP) ──────────────────────────────────────────────────────

resource "azurerm_network_interface" "k8s_node" {
  count               = 3
  name                = "nic-k8s-${count.index}-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags

  ip_configuration {
    name                          = "ipconfig-k8s"
    subnet_id                     = azurerm_subnet.k8s_cluster.id
    private_ip_address_allocation = "Static"
    private_ip_address            = local.k8s_node_ips[count.index]
  }
}

# ── Data Disks (local-path-provisioner storage) ──────────────────────────────

resource "azurerm_managed_disk" "k8s_data" {
  count                = 3
  name                 = "disk-k8s-${count.index}-${local.name_prefix}-data"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  storage_account_type = "Premium_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.k8s_data_disk_size_gb
  tags                 = merge(local.common_tags, { role = "k8s-node-${count.index}" })
}

# ── Cloud-Init ───────────────────────────────────────────────────────────────

data "cloudinit_config" "k8s_node" {
  count         = 3
  gzip          = true
  base64_encode = true

  part {
    filename     = "cloud-init.yaml"
    content_type = "text/cloud-config"
    content = templatefile("${path.module}/templates/cloud-init-k8s.yaml.tpl", {
      environment          = var.environment
      role                 = count.index == 0 ? "control-plane" : "worker"
      node_name            = "k8s-node-${count.index}"
      k8s_version          = var.k8s_version
      private_ip           = local.k8s_node_ips[count.index]
      control_plane_ip     = local.k8s_node_ips[0]
      pod_cidr             = "10.244.0.0/16"
      storage_account_name = azurerm_storage_account.main.name
      storage_account_key  = azurerm_storage_account.main.primary_access_key
    })
  }
}

# ── VMs ──────────────────────────────────────────────────────────────────────

resource "azurerm_linux_virtual_machine" "k8s_node" {
  count               = 3
  name                = "vm-k8s-${count.index}-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.k8s_node_vm_size

  admin_username                  = "octowatch"
  disable_password_authentication = true

  admin_ssh_key {
    username   = "octowatch"
    public_key = var.ssh_public_key
  }

  network_interface_ids = [azurerm_network_interface.k8s_node[count.index].id]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  os_disk {
    name                 = "osdisk-k8s-${count.index}-${local.name_prefix}"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 128
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = data.cloudinit_config.k8s_node[count.index].rendered

  boot_diagnostics {
    storage_account_uri = azurerm_storage_account.main.primary_blob_endpoint
  }

  tags = merge(local.common_tags, {
    role = count.index == 0 ? "k8s-control-plane" : "k8s-worker"
  })

  # Nodes have no public IPs — they need the LB outbound rule for internet
  # access during cloud-init (apt, GHCR, kubeadm). Also need bootstrap container.
  depends_on = [
    azurerm_lb_outbound_rule.k8s,
    azurerm_network_interface_backend_address_pool_association.k8s,
    azurerm_storage_container.k8s_bootstrap,
  ]

  lifecycle {
    ignore_changes = [custom_data]
  }
}

# ── Data Disk Attachments ────────────────────────────────────────────────────

resource "azurerm_virtual_machine_data_disk_attachment" "k8s_data" {
  count              = 3
  managed_disk_id    = azurerm_managed_disk.k8s_data[count.index].id
  virtual_machine_id = azurerm_linux_virtual_machine.k8s_node[count.index].id
  lun                = 0
  caching            = "ReadWrite"
}

################################################################################
# D. Load Balancer — Public HTTP/S Traffic Only
################################################################################

resource "azurerm_public_ip" "k8s_lb" {
  name                = "pip-k8s-lb-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  allocation_method   = "Static"
  tags                = merge(local.common_tags, { purpose = "k8s-lb-ingress" })
}

resource "azurerm_lb" "k8s" {
  name                = "lb-k8s-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  tags                = local.common_tags

  frontend_ip_configuration {
    name                 = "k8s-lb-frontend"
    public_ip_address_id = azurerm_public_ip.k8s_lb.id
  }
}

resource "azurerm_lb_backend_address_pool" "k8s" {
  name            = "k8s-backend-pool"
  loadbalancer_id = azurerm_lb.k8s.id
}

resource "azurerm_network_interface_backend_address_pool_association" "k8s" {
  count                   = 3
  network_interface_id    = azurerm_network_interface.k8s_node[count.index].id
  ip_configuration_name   = "ipconfig-k8s"
  backend_address_pool_id = azurerm_lb_backend_address_pool.k8s.id
}

# ── Health Probe — TCP 80 (ingress-nginx hostPort) ───────────────────────────

resource "azurerm_lb_probe" "k8s_http" {
  name                = "probe-http"
  loadbalancer_id     = azurerm_lb.k8s.id
  protocol            = "Tcp"
  port                = 80
  interval_in_seconds = 10
  number_of_probes    = 3
}

resource "azurerm_lb_probe" "k8s_https" {
  name                = "probe-https"
  loadbalancer_id     = azurerm_lb.k8s.id
  protocol            = "Tcp"
  port                = 443
  interval_in_seconds = 10
  number_of_probes    = 3
}

# ── LB Rules (80 → 80, 443 → 443) ───────────────────────────────────────────
# disable_outbound_snat = true because outbound is handled by a dedicated rule.

resource "azurerm_lb_rule" "k8s_http" {
  name                           = "rule-http"
  loadbalancer_id                = azurerm_lb.k8s.id
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "k8s-lb-frontend"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.k8s.id]
  probe_id                       = azurerm_lb_probe.k8s_http.id
  disable_outbound_snat          = true
  idle_timeout_in_minutes        = 4
}

resource "azurerm_lb_rule" "k8s_https" {
  name                           = "rule-https"
  loadbalancer_id                = azurerm_lb.k8s.id
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "k8s-lb-frontend"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.k8s.id]
  probe_id                       = azurerm_lb_probe.k8s_https.id
  disable_outbound_snat          = true
  idle_timeout_in_minutes        = 4
}

# ── Outbound Rule — SNAT for cluster node internet access ────────────────────
# Required because Standard LB + no public IPs = no default outbound.
# Provides outbound for: apt updates, GHCR image pulls, Let's Encrypt ACME.

resource "azurerm_lb_outbound_rule" "k8s" {
  name                    = "outbound-all"
  loadbalancer_id         = azurerm_lb.k8s.id
  protocol                = "All"
  backend_address_pool_id = azurerm_lb_backend_address_pool.k8s.id

  frontend_ip_configuration {
    name = "k8s-lb-frontend"
  }
}

################################################################################
# E. Storage — Bootstrap Token Exchange + etcd Backups
################################################################################

resource "azurerm_storage_container" "k8s_bootstrap" {
  name                  = "k8s-bootstrap"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "etcd_backups" {
  name                  = "etcd-backups"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}
