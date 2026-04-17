################################################################################
# OctoWatch — Azure Single-VM Deployment
# Terraform entry point: provider configuration and backend
################################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state backend — configure via backend config file or env vars.
  # Example:
  #   terraform init \
  #     -backend-config="resource_group_name=rg-tfstate" \
  #     -backend-config="storage_account_name=stterraformstate" \
  #     -backend-config="container_name=tfstate" \
  #     -backend-config="key=octowatch.tfstate"
  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      # Retain soft-deleted vaults for 7-day recovery window (set in KV resource).
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    virtual_machine {
      # Remove OS disk automatically when VM is deleted.
      delete_os_disk_on_deletion     = true
      skip_shutdown_and_force_delete = false
    }
  }
}

# Current caller identity — used for Key Vault RBAC assignments.
data "azurerm_client_config" "current" {}
