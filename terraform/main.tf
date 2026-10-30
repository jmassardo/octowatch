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

  # State backend is LOCAL — there is no CI/CD terraform pipeline and no
  # confirmed remote state container today (checked rg-octowatch-dev-westus2 /
  # stoctowatchdevys2c87, the real RG/storage account for this environment;
  # no "tfstate" container exists there). Whoever runs `terraform apply`
  # must keep their own terraform.tfstate safe (back it up) until a real
  # remote backend is set up. The previous comment here named RG/storage
  # account values (rg-octowatch-dev / stoctowatchdevbn3idw) that don't
  # exist and never matched a working remote-backend config — don't chase
  # them again.
  backend "local" {}
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
