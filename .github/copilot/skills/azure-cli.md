---
name: azure-cli
description: Run Azure CLI commands against the OctoWatch Azure subscription. Use for managing Azure resources, checking resource status, and troubleshooting infrastructure.
---

# Azure CLI Skill

Run Azure CLI (`az`) commands against the OctoWatch Azure subscription.

## Prerequisites
- Azure CLI must be installed and authenticated (`az login`)
- Target subscription should be set: `az account set --subscription <sub-id>`

## Common Operations

### Check resource status
```bash
az vm list --resource-group octowatch-rg -o table
az vm show --resource-group octowatch-rg --name <vm-name> -o table
```

### View networking
```bash
az network nsg rule list --resource-group octowatch-rg --nsg-name <nsg-name> -o table
az network lb show --resource-group octowatch-rg --name <lb-name> -o table
```

### Check DNS
```bash
az network dns record-set list --resource-group octowatch-rg --zone-name <zone> -o table
```

### VM operations
```bash
az vm start --resource-group octowatch-rg --name <vm-name>
az vm stop --resource-group octowatch-rg --name <vm-name>
az vm restart --resource-group octowatch-rg --name <vm-name>
```

## Safety
- Always use `--resource-group octowatch-rg` to scope commands
- Never delete resources without explicit user confirmation
- Use `-o table` for readable output, `-o json` for scripting
