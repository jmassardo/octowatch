# OctoWatch — Azure Container Apps Migration Runbook

This runbook covers the complete migration of OctoWatch from the Docker Compose
VM deployment to Azure Container Apps (ACA). Follow each phase in order. Do not
skip steps.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Pre-Cutover Deployment](#2-pre-cutover-deployment)
3. [Cutover Sequence](#3-cutover-sequence)
4. [Rollback Procedure](#4-rollback-procedure)
5. [Post-Cutover Decommission](#5-post-cutover-decommission)

---

## 1. Prerequisites

Complete all items before running `terraform apply`.

### 1.1 Azure RBAC

The service principal or user running Terraform must have **Contributor** on the
resource group and **Network Contributor** on the VNet (to delegate the ACA
subnet). If using managed identity in CI, ensure the identity has these roles.

### 1.2 ACA subnet address space

Verify `10.0.2.0/23` does not conflict with any existing peered networks. The
ACA environment requires a **/23 or larger** dedicated subnet. The default CIDR
is set in `var.aca_subnet_cidr`.

### 1.3 Azure Files Premium availability

Confirm `FileStorage` Premium LRS is available in the target region:

```bash
az storage account list-types \
  --query "[?kind=='FileStorage' && tier=='Premium']" \
  --location eastus2
```

### 1.4 Container images published

All three images must exist in GHCR at the tag you intend to deploy:

```bash
docker manifest inspect ghcr.io/<owner>/octowatch/api:<tag>
docker manifest inspect ghcr.io/<owner>/octowatch/worker:<tag>
docker manifest inspect ghcr.io/<owner>/octowatch/frontend:<tag>
```

### 1.5 DNS TTL reduction

At least **24 hours before cutover**, lower the A record TTL to 60 seconds so
DNS caches flush quickly at cutover:

```bash
az network dns record-set a update \
  --resource-group <dns-zone-rg> \
  --zone-name <zone> \
  --name octowatch \
  --set ttl=60
```

Wait 24 hours for the original TTL to expire everywhere before proceeding.

### 1.6 GitHub Actions secrets

Ensure the following secrets are configured in the repository
(**Settings → Secrets and variables → Actions**) before enabling the ACA deploy
job:

| Secret | Value |
|--------|-------|
| `ACA_ENABLED` | `true` (activates the `deploy-aca` workflow job) |
| `AZURE_CREDENTIALS` | JSON output of `az ad sp create-for-rbac --sdk-auth` |
| `ACA_RESOURCE_GROUP` | e.g. `rg-octowatch-prod` |
| `ACA_ENVIRONMENT_NAME` | e.g. `cae-octowatch-prod` |
| `ACA_FRONTEND_URL` | e.g. `https://octowatch.example.com` |

To create `AZURE_CREDENTIALS` (requires a subscription Owner):

```bash
az ad sp create-for-rbac \
  --name "octowatch-github-actions" \
  --role Contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-octowatch-prod \
  --sdk-auth
```

Copy the JSON output as the `AZURE_CREDENTIALS` secret value.

---

## 2. Pre-Cutover Deployment

### 2.1 Apply Terraform (ACA infrastructure only)

`aca_cutover_complete` must be `false` (the default). This provisions the ACA
environment in parallel with the live VM — no traffic is shifted yet.

```bash
cd terraform

# Review the plan — verify only ACA resources are being created
terraform plan \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=false"

# Apply
terraform apply \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=false"
```

Expected new resources (≈20):

- `azurerm_subnet.aca`
- `azurerm_storage_account.premium` + 2 shares
- `azurerm_container_app_environment.main`
- `azurerm_container_app_environment_storage.*` (×2)
- `azurerm_container_app.*` (db, valkey, api, frontend, beat, 5 workers)
- `azurerm_container_app_job.migrate`
- `azurerm_dns_txt_record.aca_domain_verification`

The A record **remains active**. The VM continues serving production traffic.

### 2.2 Run the migration job (initial schema bootstrap)

```bash
# Get the job name from Terraform output
JOB_NAME=$(terraform output -raw aca_migrate_job_name)
RG=$(terraform output -raw resource_group_name)

# Trigger the Alembic migration
az containerapp job start \
  --name "$JOB_NAME" \
  --resource-group "$RG"

# Monitor until Succeeded
az containerapp job execution list \
  --name "$JOB_NAME" \
  --resource-group "$RG" \
  --query "sort_by([], &properties.startTime)[-1].{status:properties.status,start:properties.startTime}" \
  --output table
```

### 2.3 Smoke-test ACA on the default domain

The ACA environment has its own auto-generated FQDN before the custom domain is
applied. Test against it to verify the stack is functional:

```bash
ACA_URL="https://$(terraform output -raw aca_frontend_fqdn)"
echo "Smoke-testing $ACA_URL ..."
curl -sf "$ACA_URL/" | head -20
```

Also verify the API health endpoint:

```bash
API_FQDN=$(az containerapp show \
  --name api \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
curl -sf "https://${API_FQDN}/health"
```

### 2.4 Enable ACA deploy in GitHub Actions

Set `ACA_ENABLED=true` in repository secrets. From this point, every CI/CD push
updates **both** the VM and ACA in parallel. Verify a test deploy succeeds end-
to-end before proceeding to cutover.

---

## 3. Cutover Sequence

> **Estimated downtime: ~0 minutes** (DNS TTL is 60s; ACA serves requests as
> soon as the CNAME propagates).

| Time | Action |
|------|--------|
| **T−24h** | Lower DNS TTL to 60s ([§1.5](#15-dns-ttl-reduction)) |
| **T−1h** | Smoke-test ACA on the default domain ([§2.3](#23-smoke-test-aca-on-the-default-domain)) |
| **T+0** | Stop nginx on the VM to halt new requests (see below) |
| **T+2m** | Confirm queue drain: all Celery queues empty in Valkey |
| **T+3m** | Start `pg_dump` on the VM |
| **T+8m** | Upload dump to Azure Blob Storage (`pg-backups` container) |
| **T+10m** | Restore into ACA TimescaleDB (with timescaledb hooks) |
| **T+25m** | Restore complete — run integrity checks |
| **T+28m** | `terraform apply` with `aca_cutover_complete=true` |
| **T+30m** | Monitor ACA logs for errors |
| **T+35m** | Managed TLS cert auto-provisioned by ACA |
| **T+45m** | Confirm healthy — stop VM permanently |
| **T+72h** | Decommission VM resources ([§5](#5-post-cutover-decommission)) |

### Step-by-step commands

**T+0 — Stop VM nginx:**

```bash
ssh octowatch@$VM_HOST \
  "cd /opt/octowatch/compose && sudo docker compose stop nginx"
```

**T+2m — Confirm queue drain:**

```bash
ssh octowatch@$VM_HOST \
  "cd /opt/octowatch/compose && \
   sudo docker compose exec valkey valkey-cli -a \$VALKEY_PASSWORD \
     LLEN ingestion && \
   sudo docker compose exec valkey valkey-cli -a \$VALKEY_PASSWORD \
     LLEN detection && \
   sudo docker compose exec valkey valkey-cli -a \$VALKEY_PASSWORD \
     LLEN notification"
# All should return 0
```

**T+3m — pg_dump on VM:**

```bash
ssh octowatch@$VM_HOST "bash -s" <<'EOF'
set -eu
DUMP_FILE="/tmp/octowatch-migration-$(date +%Y%m%d-%H%M%S).dump"
sudo docker compose -f /opt/octowatch/compose/docker-compose.yml exec -T db \
  pg_dump \
    --username "$POSTGRES_USER" \
    --format=custom \
    --no-acl \
    --no-owner \
    "$POSTGRES_DB" > "$DUMP_FILE"
echo "Dump written to $DUMP_FILE ($(du -sh $DUMP_FILE | cut -f1))"
EOF
```

**T+8m — Upload dump to blob storage:**

```bash
ssh octowatch@$VM_HOST "bash -s" <<'EOF'
az storage blob upload \
  --account-name <storage_account_name> \
  --container-name pg-backups \
  --name "migration/$(ls -t /tmp/octowatch-migration-*.dump | head -1 | xargs basename)" \
  --file "$(ls -t /tmp/octowatch-migration-*.dump | head -1)" \
  --auth-mode login
echo "Upload complete."
EOF
```

**T+10m — Restore into ACA TimescaleDB:**

```bash
# Download dump locally (or use az containerapp exec if available)
az storage blob download \
  --account-name <storage_account_name> \
  --container-name pg-backups \
  --name "migration/<dump-file-name>" \
  --file /tmp/migration.dump

# Connect to ACA db via az containerapp exec (requires ACA CLI extension)
# Or restore by copying dump into db container:
az containerapp exec \
  --name db \
  --resource-group "$RG" \
  --command "psql -U $POSTGRES_USER $POSTGRES_DB -c 'SELECT timescaledb_pre_restore();'"

# Restore (run from a host with psql access to ACA db endpoint)
# NOTE: For TimescaleDB, pre_restore/post_restore hooks are required
az containerapp exec \
  --name db \
  --resource-group "$RG" \
  --command "pg_restore \
    --username $POSTGRES_USER \
    --dbname $POSTGRES_DB \
    --no-acl \
    --no-owner \
    --verbose \
    /tmp/migration.dump"

az containerapp exec \
  --name db \
  --resource-group "$RG" \
  --command "psql -U $POSTGRES_USER $POSTGRES_DB -c 'SELECT timescaledb_post_restore();'"
```

**T+25m — Integrity checks:**

```bash
# Row counts should match VM database
az containerapp exec --name db --resource-group "$RG" \
  --command "psql -U $POSTGRES_USER $POSTGRES_DB -c '
    SELECT schemaname, tablename, n_live_tup
    FROM pg_stat_user_tables
    ORDER BY n_live_tup DESC
    LIMIT 20;'"
```

**T+28m — DNS cutover via Terraform:**

```bash
cd terraform
terraform apply \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=true"
```

This:
- Destroys the `azurerm_dns_a_record.octowatch` (VM A record)
- Creates the `azurerm_dns_cname_record.aca_frontend` (CNAME to ACA)

Within 60 seconds (the reduced TTL), clients will resolve to ACA.

**T+30m — Monitor ACA logs:**

```bash
az containerapp logs show \
  --name api \
  --resource-group "$RG" \
  --follow \
  --tail 100

# Watch for errors across all apps
for APP in db valkey api frontend beat worker-ingestion worker-detection; do
  echo "=== $APP ===" && \
  az containerapp logs show --name "$APP" --resource-group "$RG" --tail 20
done
```

**T+35m — TLS certificate:**

Azure Container Apps automatically provisions a managed TLS certificate within
5–15 minutes of the CNAME record being active. Monitor in the Azure Portal:
Container App → Custom domains → Certificate status.

**T+45m — Confirm and stop VM:**

```bash
# Final smoke test via custom domain
curl -sf "https://$(terraform output -raw dns_fqdn)/" | head -5

# Stop VM (soft stop — preserves disk for 72h recovery window)
az vm deallocate \
  --name $(az vm list --resource-group "$RG" --query "[0].name" -o tsv) \
  --resource-group "$RG"
```

---

## 4. Rollback Procedure

### 4a. Rollback before T+28m (Terraform cutover not yet applied)

Simply restart the VM nginx — no DNS change is needed because the A record was
never removed:

```bash
ssh octowatch@$VM_HOST \
  "cd /opt/octowatch/compose && sudo docker compose start nginx"
```

### 4b. Rollback after T+28m (CNAME is live)

Re-apply Terraform with `aca_cutover_complete=false` to restore the A record
and remove the CNAME:

```bash
cd terraform
terraform apply \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=false"

# Restart VM nginx to accept traffic again
ssh octowatch@$VM_HOST \
  "cd /opt/octowatch/compose && sudo docker compose start nginx"
```

DNS will flip back within 60 seconds (the reduced TTL).

> **Note:** Any writes made to the ACA database after cutover will be lost on
> rollback since the VM database was not receiving writes during the ACA
> window. Consider the data loss window acceptable before triggering rollback.
> If not acceptable, perform a reverse pg_dump/pg_restore from ACA db → VM db
> before running the rollback Terraform apply.

---

## 5. Post-Cutover Decommission

Wait **72 hours** after successful cutover before decommissioning. This provides
a recovery window if issues surface after the rollback TTL window closes.

### 5.1 Verify no traffic to VM

Check VM nginx access logs confirm zero requests for ≥1 hour:

```bash
ssh octowatch@$VM_HOST \
  "sudo tail -100 /var/log/nginx/access.log 2>/dev/null || \
   sudo docker compose -f /opt/octowatch/compose/docker-compose.yml \
     exec nginx tail -100 /var/log/nginx/access.log"
```

### 5.2 Final data backup

Before destroying the VM, take a final backup of the VM PostgreSQL database:

```bash
ssh octowatch@$VM_HOST "bash -s" <<'EOF'
DUMP_FILE="/tmp/octowatch-final-$(date +%Y%m%d).dump"
sudo docker compose -f /opt/octowatch/compose/docker-compose.yml exec -T db \
  pg_dump --username "$POSTGRES_USER" --format=custom "$POSTGRES_DB" > "$DUMP_FILE"
az storage blob upload \
  --account-name <storage_account_name> \
  --container-name pg-backups \
  --name "decommission/$(basename $DUMP_FILE)" \
  --file "$DUMP_FILE" \
  --auth-mode login
echo "Final backup uploaded."
EOF
```

### 5.3 Restore normal DNS TTL

```bash
az network dns record-set cname update \
  --resource-group <dns-zone-rg> \
  --zone-name <zone> \
  --name octowatch \
  --set ttl=300
```

### 5.4 Decommission VM and related resources

Remove the `vm.tf` resources by destroying them selectively (avoids destroying
shared resources like storage, identity, and networking):

```bash
cd terraform

# Target-destroy only VM-specific resources
terraform destroy \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=true" \
  -target=azurerm_linux_virtual_machine.main \
  -target=azurerm_network_interface.main \
  -target=azurerm_network_interface_security_group_association.main \
  -target=azurerm_network_security_group.main \
  -target=azurerm_subnet_network_security_group_association.main \
  -target=azurerm_public_ip.main \
  -target=azurerm_managed_disk.data \
  -target=azurerm_virtual_machine_data_disk_attachment.data \
  -auto-approve

# Also destroy the Azure Automation account (scheduled VM ops)
terraform destroy \
  -var-file=terraform.tfvars \
  -var="aca_cutover_complete=true" \
  -target=azurerm_automation_account.main \
  -auto-approve
```

### 5.5 Clean up Terraform files (optional)

After decommission, the following Terraform files are no longer needed and can
be archived or removed:

- `terraform/vm.tf`
- `terraform/automation.tf`
- `terraform/templates/cloud-init.yaml.tpl`
- `terraform/templates/docker-compose.yml.tpl`
- `terraform/templates/env.tpl`

Remove related variables from `variables.tf` that are no longer referenced
(VM-specific vars like `vm_size`, `data_disk_size_gb`, `ssh_public_key`, etc.).

### 5.6 Remove SSH deploy from GitHub Actions

Once the VM is gone, remove the `deploy` job from `.github/workflows/deploy-azure.yml`
and keep only the `deploy-aca` job. Remove the VM SSH secrets from repository
settings.

---

## Appendix: Useful Commands

### Check ACA environment health

```bash
az containerapp list \
  --resource-group "$RG" \
  --query "[].{name:name,replicas:properties.template.scale.minReplicas,status:properties.latestRevisionName}" \
  --output table
```

### Stream logs from a specific container

```bash
az containerapp logs show \
  --name api \
  --resource-group "$RG" \
  --follow
```

### Manually trigger a KEDA scale-up (test)

```bash
# Push a test message to a queue
az containerapp exec --name valkey --resource-group "$RG" \
  --command "valkey-cli -a \$VALKEY_PASSWORD LPUSH ingestion test-message"
```

### List Container App job executions

```bash
az containerapp job execution list \
  --name "$(terraform output -raw aca_migrate_job_name)" \
  --resource-group "$RG" \
  --output table
```
