# OctoWatch — Azure Single-VM Deployment

This Terraform configuration deploys OctoWatch on a single Azure Linux VM running Docker Compose. It provisions all required infrastructure including networking, Key Vault, managed identity, and storage, then bootstraps the VM via cloud-init.

## Architecture Overview

```
Internet
   │
   ▼
Azure Public IP (Standard, Static)
   │
   ▼
Network Security Group (SSH/80/443 in, all out)
   │
   ▼
Network Interface → Virtual Network (10.0.0.0/16) → Subnet (10.0.1.0/24)
   │
   ▼
Ubuntu 24.04 LTS VM (Standard_D4s_v5 default)
   │  ├── OS Disk: Premium SSD 128 GiB
   │  ├── Data Disk: Premium SSD 256 GiB → /mnt/octowatch-data
   │  │     ├── pg_data/      (TimescaleDB bind mount)
   │  │     └── valkey_data/  (Valkey bind mount)
   │  └── User-Assigned Managed Identity → Key Vault (Secrets User)
   │
   ▼
Docker Compose Stack (managed by cloud-init + systemd)
   ├── nginx:1.28-alpine        (TLS termination, :80/:443)
   ├── octowatch-frontend       (React SPA, :3001 internal)
   ├── octowatch-api            (FastAPI, :8000 internal)
   ├── octowatch-worker × 5    (Celery workers)
   ├── beat                     (Celery scheduler)
   ├── timescaledb:2.25.1-pg16  (PostgreSQL + TimescaleDB)
   ├── valkey:9.0.3-alpine      (Redis-compatible cache/broker)
   └── octowatch-worker × 5    (Celery workers + beat)

Azure Resources
   ├── Key Vault (RBAC, soft-delete, purge protection)
   ├── Storage Account (LRS — backups + boot diagnostics)
   └── User-Assigned Managed Identity
```

## Prerequisites

### Tools Required

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Terraform | 1.7.0 | [terraform.io](https://developer.hashicorp.com/terraform/downloads) |
| Azure CLI | 2.55.0 | [learn.microsoft.com](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| jq | any | `apt install jq` / `brew install jq` |

### Azure Permissions

The principal running `terraform apply` must have:

- **Contributor** on the target subscription (to create resources)
- **User Access Administrator** on the subscription (to create RBAC role assignments)
- Alternatively: a custom role combining both above on the resource group scope

### Remote State Backend

Create the Terraform state backend resources before first `init`:

```bash
# Create resource group for state
az group create \
  --name rg-tfstate \
  --location eastus2

# Create storage account (name must be globally unique)
az storage account create \
  --name stterraformstate<suffix> \
  --resource-group rg-tfstate \
  --sku Standard_LRS \
  --min-tls-version TLS1_2

# Create container
az storage container create \
  --name tfstate \
  --account-name stterraformstate<suffix>
```

### SSH Key Pair

Generate an ED25519 key pair for the VM admin user:

```bash
ssh-keygen -t ed25519 -C "octowatch-vm" -f ~/.ssh/octowatch_vm
```

### GitHub OAuth App

Create a GitHub OAuth App at **Settings → Developer settings → OAuth Apps**:
- **Homepage URL**: `https://<your-domain>`
- **Authorization callback URL**: `https://<your-domain>/auth/github/callback`

Note the Client ID and Client Secret.

### GitHub PAT for GHCR

Create a GitHub Personal Access Token with `read:packages` scope to pull
images from GitHub Container Registry.

---

## Deployment Steps

### 1. Authenticate to Azure

```bash
az login
az account set --subscription <subscription-id>
```

### 2. Copy and fill in variables

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values (DO NOT commit this file)
```

### 3. Initialize Terraform

```bash
terraform init \
  -backend-config="resource_group_name=rg-tfstate" \
  -backend-config="storage_account_name=stterraformstate<suffix>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=octowatch-${ENVIRONMENT}.tfstate"
```

### 4. Plan and review

```bash
terraform plan -var-file=terraform.tfvars
```

### 5. Apply

```bash
terraform apply -var-file=terraform.tfvars
```

Terraform will output the public IP, FQDN, SSH command, and Key Vault name.

### 6. Monitor cloud-init bootstrap

The VM runs cloud-init at first boot. This takes 5–15 minutes (package installs,
Docker setup, image pulls). Monitor progress:

```bash
# Get the VM's public IP from Terraform output
VM_IP=$(terraform output -raw vm_public_ip)

# SSH to the VM (using the key generated in prerequisites)
ssh -i ~/.ssh/octowatch_vm octowatch@$VM_IP

# Tail cloud-init log
sudo tail -f /var/log/cloud-init-output.log

# Or watch systemd journal for cloud-final
sudo journalctl -u cloud-final -f
```

### 7. Verify the stack

Once cloud-init completes:

```bash
# On the VM — check stack status
cd /opt/octowatch/compose
docker compose ps

# Check health endpoint
curl -k https://localhost/health

# Check logs
docker compose logs --tail=50 api
```

---

## Post-Deployment Steps

### DNS Configuration

If using a custom domain (`tls_domain` variable), create a DNS A record pointing
to the VM's public IP:

```
A   octowatch.yourdomain.com  →  <VM_PUBLIC_IP>
```

### Let's Encrypt (if tls_mode = "letsencrypt")

Ensure DNS is resolving to the VM's IP **before** applying with Let's Encrypt
mode. certbot will fail the ACME HTTP-01 challenge if DNS is not configured.

### Initial Admin Access

Set `secret_initial_admin_logins` to a comma-separated list of GitHub usernames
that should receive the admin role on first login.

### HEC Audit Log Streaming

After the stack is running, configure GitHub Enterprise audit log streaming via HEC:
1. Go to GitHub Enterprise → **Settings → Audit log → Log streaming**
2. Select **Splunk HEC**
3. Configure with your HEC token and endpoint URL.

---

## Operations

### Updating Application Images

To deploy a new image tag:

```bash
# Update ghcr_image_tag in terraform.tfvars
terraform apply -var-file=terraform.tfvars

# The new docker-compose.yml is written by cloud-init on the NEXT boot only.
# For a running VM, pull and restart manually:
ssh octowatch@$VM_IP
cd /opt/octowatch/compose
docker compose pull
docker compose up -d --remove-orphans
```

For zero-downtime deploys, use a rolling restart per service:
```bash
docker compose pull api && docker compose up -d --no-deps api
```

### Rotating Secrets

1. Update the secret variable in `terraform.tfvars`
2. `terraform apply` — updates the Key Vault secret
3. On the VM, re-fetch secrets and restart:
   ```bash
   # As root on the VM
   az keyvault secret show \
     --vault-name <kv-name> \
     --name octowatch-secret-key \
     --query value -o tsv
   # Update .env and restart affected services
   docker compose up -d --no-deps api worker-detection worker-ingestion
   ```

### PostgreSQL Backups

Backups run daily at 03:00 UTC via cron. The backup script:
- Runs `pg_dump` against `DATABASE_URL` from `.env`
- Compresses with gzip
- Uploads to Azure Blob Storage (`pg-backups` container) using managed identity
- Stores backups under `YYYY/MM/DD/<timestamp>.sql.gz`

To run a manual backup:
```bash
sudo /opt/octowatch/scripts/backup-azure.sh
```

To restore from a backup:
```bash
BACKUP_FILE="path/to/backup.sql.gz"
az storage blob download \
  --account-name <storage-account> \
  --container-name pg-backups \
  --name "$BACKUP_FILE" \
  --file /tmp/restore.sql.gz \
  --auth-mode login

zcat /tmp/restore.sql.gz | docker compose exec -T db \
  psql -U $POSTGRES_USER $POSTGRES_DB
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api

# Boot diagnostics (Azure Portal)
# VM → Diagnostics → Boot diagnostics → Serial log
```

### Auto-Shutdown (Dev/Staging)

Enable cost-saving auto-shutdown for non-production environments:

```hcl
enable_auto_shutdown = true
auto_shutdown_time   = "1900"  # 7 PM UTC
```

---

## Security Notes

- All secrets are stored in Azure Key Vault (RBAC-enabled, soft-delete, purge protection)
- The VM accesses secrets via managed identity — no credentials are stored on disk
- The `.env` file on the VM is `chmod 600`, owned by `octowatch`
- SSH password authentication is disabled; root login is disabled
- The NSG blocks all inbound traffic except SSH (configurable CIDR), HTTP, HTTPS
- Docker daemon runs with `no-new-privileges` and `userns-remap`
- TLS 1.2+ enforced by nginx; HSTS with 2-year max-age

---

## Variables Reference

See [variables.tf](./variables.tf) for full documentation of all variables.
See [terraform.tfvars.example](./terraform.tfvars.example) for a template.

## Outputs Reference

| Output | Description |
|--------|-------------|
| `vm_public_ip` | VM's public IP address |
| `vm_fqdn` | Azure-assigned FQDN |
| `tls_domain` | Effective TLS domain |
| `ssh_command` | Ready-to-use SSH command |
| `resource_group_name` | Resource group name |
| `key_vault_name` | Key Vault resource name |
| `key_vault_uri` | Key Vault data-plane URI |
| `managed_identity_client_id` | Identity client ID |
| `managed_identity_principal_id` | Identity principal ID |
| `storage_account_name` | Storage account name |
| `vm_id` | VM Azure resource ID |

## Terraform File Map

| File | Purpose |
|------|---------|
| `main.tf` | Provider config, backend, data sources |
| `variables.tf` | All input variable declarations |
| `locals.tf` | Computed locals (name prefix, tags, KV name) |
| `resource_group.tf` | Resource group |
| `networking.tf` | VNet, subnet, NSG, public IP, NIC |
| `identity.tf` | User-assigned managed identity |
| `key_vault.tf` | Key Vault + RBAC assignments |
| `key_vault_secrets.tf` | All 36 application secrets |
| `storage.tf` | Storage account + backup container |
| `vm.tf` | Data disk, VM, cloud-init data source |
| `outputs.tf` | Output values |
| `templates/cloud-init.yaml.tpl` | VM bootstrap cloud-init config |
| `templates/docker-compose.yml.tpl` | Docker Compose with GHCR images + bind mounts |
