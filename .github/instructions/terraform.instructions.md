---
applyTo: "terraform/**"
---

# Terraform Instructions

## Provider & Architecture
- Azure provider (`azurerm`) exclusively
- Self-managed kubeadm Kubernetes cluster on Azure VMs (migrated from AKS — see ADR-002)
- State stored in Azure Blob Storage with locking

## Resource Layout
- `main.tf` — Provider, resource group, shared resources
- `networking.tf` — VNet, subnets (app, k8s-nodes, k8s-mgmt), NSGs, LB
- `k8s-cluster.tf` — K8s node VMs (control plane + workers), cloud-init provisioning
- `k8s-mgmt.tf` — Management/bastion VM (CI runner, kubectl access)
- `dns.tf` — Azure DNS zones and records
- `variables.tf` — All input variables with descriptions and defaults
- `outputs.tf` — Connection strings, SSH commands, endpoints

## Conventions
- Use descriptive resource names: `azurerm_linux_virtual_machine.k8s_cp`
- Use `local.` for computed values and repeated expressions
- All VMs use `cloud-init` for provisioning (user_data with cloud-config YAML)
- K8s nodes have NO public IPs — admin access is via mgmt VM jump host
- NSG rules allow SSH only from `var.ssh_source_cidr`

## Important Notes
- Sensitive values (SSH keys, secrets) come from variables, never hardcoded.
- Run `terraform plan` before `terraform apply`. Never auto-approve in production.
