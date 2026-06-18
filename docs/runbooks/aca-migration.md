# Archived: Azure Container Apps Migration Runbook

> **Status: Archived / deprecated**
>
> OctoWatch no longer recommends Azure Container Apps as an active deployment
> target. New Azure deployments should use the self-managed kubeadm Kubernetes
> cluster documented in [`ADR-002`](../adr/ADR-002-aks-to-self-managed-k8s.md)
> and [`docs/deployment-options.md`](../deployment-options.md).
>
> This document is retained only as historical reference for environments that
> previously evaluated ACA.

---

## Historical Note

This runbook described a migration path from the older Docker Compose VM
deployment to Azure Container Apps (ACA). It is no longer the preferred or
maintained deployment path.

If you are planning a current migration, use this sequence instead:

1. Provision the self-managed kubeadm cluster with Terraform.
2. Restore data with `pg_dump` / `pg_restore`.
3. Deploy the Helm chart from the management VM.
4. Cut DNS to the Azure Standard Load Balancer IP.

For backup and cutover procedures, see:

- [`docs/runbooks/backup-restore.md`](./backup-restore.md)
- [`docs/deployment-guide.md`](../deployment-guide.md)
- [`docs/adr/ADR-002-aks-to-self-managed-k8s.md`](../adr/ADR-002-aks-to-self-managed-k8s.md)
