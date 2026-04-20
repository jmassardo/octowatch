################################################################################
# OctoWatch — VM Auto-Restart
#
# Watches for Azure Resource Health "Unavailable" events on the VM and
# automatically starts it back up via an Automation Account runbook.
# Handles the case where the VM is shut down by subscription-level policies.
################################################################################

# ── Automation Account ─────────────────────────────────────────────────────────

resource "azurerm_automation_account" "main" {
  name                = "aa-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku_name            = "Basic"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  tags = local.common_tags
}

# Give the user-assigned identity permission to start the VM.
resource "azurerm_role_assignment" "automation_vm_contributor" {
  scope                = azurerm_linux_virtual_machine.main.id
  role_definition_name = "Virtual Machine Contributor"
  principal_id         = azurerm_user_assigned_identity.vm.principal_id
}

# ── Runbook ────────────────────────────────────────────────────────────────────

resource "azurerm_automation_runbook" "start_vm" {
  name                    = "Start-OctowatchVM"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  automation_account_name = azurerm_automation_account.main.name
  log_verbose             = false
  log_progress            = false
  runbook_type            = "PowerShell"
  tags                    = local.common_tags

  content = <<-POWERSHELL
    param([object]$WebhookData)

    # Authenticate using the user-assigned managed identity attached to this Automation Account.
    Connect-AzAccount -Identity -AccountId "${azurerm_user_assigned_identity.vm.client_id}" | Out-Null

    $vmName   = "${azurerm_linux_virtual_machine.main.name}"
    $rgName   = "${azurerm_resource_group.main.name}"

    $vm = Get-AzVM -ResourceGroupName $rgName -Name $vmName -Status
    $powerState = ($vm.Statuses | Where-Object { $_.Code -like "PowerState/*" }).DisplayStatus

    Write-Output "VM '$vmName' current state: $powerState"

    if ($powerState -ne "VM running") {
        Write-Output "Starting VM '$vmName'..."
        Start-AzVM -ResourceGroupName $rgName -Name $vmName
        Write-Output "Start command issued successfully."
    } else {
        Write-Output "VM is already running — no action needed."
    }
  POWERSHELL
}

# ── Webhook (called by the Action Group) ──────────────────────────────────────

resource "azurerm_automation_webhook" "start_vm" {
  name                    = "wh-start-octowatch-vm"
  resource_group_name     = azurerm_resource_group.main.name
  automation_account_name = azurerm_automation_account.main.name
  runbook_name            = azurerm_automation_runbook.start_vm.name
  expiry_time             = "2030-01-01T00:00:00Z"
  enabled                 = true
}

# ── Action Group ───────────────────────────────────────────────────────────────

resource "azurerm_monitor_action_group" "restart_vm" {
  name                = "ag-${local.name_prefix}-restart"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "oct-restart"
  tags                = local.common_tags

  webhook_receiver {
    name                    = "start-vm-runbook"
    service_uri             = azurerm_automation_webhook.start_vm.uri
    use_common_alert_schema = true
  }
}

# ── Resource Health Alert ──────────────────────────────────────────────────────
# Fires when the VM transitions to Unavailable (shutdown/deallocation).

resource "azurerm_monitor_activity_log_alert" "vm_unavailable" {
  name                = "ala-${local.name_prefix}-unavailable"
  resource_group_name = azurerm_resource_group.main.name
  location            = "global"
  scopes              = [azurerm_linux_virtual_machine.main.id]
  description         = "Restart OctoWatch VM when Azure reports it as Unavailable."
  tags                = local.common_tags

  criteria {
    category = "ResourceHealth"

    resource_health {
      current  = ["Unavailable"]
      previous = ["Available"]
      reason   = ["PlatformInitiated", "UserInitiated", "Unknown"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.restart_vm.id
  }
}
