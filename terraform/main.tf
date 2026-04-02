/* ------------------------------------------------------------------ */
/*  Locals                                                             */
/* ------------------------------------------------------------------ */

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

/* ------------------------------------------------------------------ */
/*  Random secrets                                                     */
/* ------------------------------------------------------------------ */

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "random_password" "valkey" {
  length  = 32
  special = false
}

resource "random_password" "minio_root" {
  length  = 32
  special = false
}

resource "random_password" "minio_ingest" {
  length  = 32
  special = false
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "encryption_key" {
  length  = 64
  special = false
}

/* ------------------------------------------------------------------ */
/*  SSH Key                                                            */
/* ------------------------------------------------------------------ */

resource "tls_private_key" "vm" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

/* ------------------------------------------------------------------ */
/*  Resource Group                                                     */
/* ------------------------------------------------------------------ */

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}

/* ------------------------------------------------------------------ */
/*  Networking                                                         */
/* ------------------------------------------------------------------ */

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.0.0.0/16"]
  tags                = local.common_tags
}

resource "azurerm_subnet" "main" {
  name                 = "snet-${local.name_prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_network_security_group" "main" {
  name                = "nsg-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  security_rule {
    name                       = "AllowHTTP"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  dynamic "security_rule" {
    for_each = length(var.allowed_ssh_cidrs) > 0 ? [1] : []
    content {
      name                       = "AllowSSH"
      priority                   = 200
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "22"
      source_address_prefixes    = var.allowed_ssh_cidrs
      destination_address_prefix = "*"
    }
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "main" {
  subnet_id                 = azurerm_subnet.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}

resource "azurerm_public_ip" "main" {
  name                = "pip-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = local.name_prefix
  tags                = local.common_tags
}

resource "azurerm_network_interface" "main" {
  name                = "nic-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main.id
  }
}

/* ------------------------------------------------------------------ */
/*  Virtual Machine                                                    */
/* ------------------------------------------------------------------ */

resource "azurerm_linux_virtual_machine" "main" {
  name                = "vm-${local.name_prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [azurerm_network_interface.main.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = tls_private_key.vm.public_key_openssh
  }

  os_disk {
    name                 = "osdisk-${local.name_prefix}"
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  custom_data = base64encode(templatefile("${path.module}/templates/cloud-init.yml", {
    admin_username       = var.admin_username
    acr_name             = var.acr_name
    acr_login_server     = azurerm_container_registry.main.login_server
    fqdn                 = azurerm_public_ip.main.fqdn
    postgres_password    = random_password.postgres.result
    valkey_password      = random_password.valkey.result
    minio_root_password  = random_password.minio_root.result
    minio_ingest_password = random_password.minio_ingest.result
    secret_key           = random_password.secret_key.result
    encryption_key       = random_password.encryption_key.result
    github_client_id     = var.github_client_id
    github_client_secret = var.github_client_secret
    github_app_id        = var.github_app_id
    github_enterprise_slug = var.github_enterprise_slug
    initial_admin_logins = var.initial_admin_logins
  }))

  tags = local.common_tags
}

/* ------------------------------------------------------------------ */
/*  Data Disk                                                          */
/* ------------------------------------------------------------------ */

resource "azurerm_managed_disk" "data" {
  name                 = "datadisk-${local.name_prefix}"
  location             = azurerm_resource_group.main.location
  resource_group_name  = azurerm_resource_group.main.name
  storage_account_type = "Premium_LRS"
  create_option        = "Empty"
  disk_size_gb         = var.data_disk_size_gb
  tags                 = local.common_tags
}

resource "azurerm_virtual_machine_data_disk_attachment" "data" {
  managed_disk_id    = azurerm_managed_disk.data.id
  virtual_machine_id = azurerm_linux_virtual_machine.main.id
  lun                = 0
  caching            = "ReadWrite"
}
