# ADR-002: Migrate from AKS to a Self-Managed Kubernetes Cluster

| Field      | Value         |
|------------|---------------|
| **Status** | Accepted      |
| **Date**   | 2026-06-17    |
| **Author** | Platform Team |

---

## Context

OctoWatch's original Azure Kubernetes deployment model assumed a managed
[AKS](https://azure.microsoft.com/products/kubernetes-service/) control plane.
That model worked, but it introduced trade-offs that no longer matched the
project's operational goals:

- **Cost control**: AKS added managed-service cost and encouraged extra Azure
  dependencies that were not required for OctoWatch's workload profile.
- **Full cluster control**: the team needed direct control over Kubernetes
  version pinning, bootstrap flow, node layout, storage choices, and ingress
  configuration.
- **No abstraction layer**: debugging kubeadm, kubelet, ingress, storage, and
  networking directly is simpler than reasoning through AKS-specific behavior.
- **Simpler networking**: OctoWatch only needs a small, fixed footprint — a
  management subnet, a cluster subnet, and a public HTTP/S load balancer. A
  self-managed topology maps to that requirement cleanly.

Terraform now defines both worlds:

- `terraform/k8s-cluster.tf` provisions the current primary topology.
- `terraform/aks.tf` remains as a legacy path, gated behind `var.enable_aks`.

The production topology is:

- **Management subnet**: `10.0.10.0/28`
- **Cluster subnet**: `10.0.8.0/24`
- **Cluster shape**: 1 control-plane VM + 2 worker VMs
- **Ingress**: Azure Standard Load Balancer for HTTP/S
- **Admin entry point**: a dedicated management VM acting as bastion, `kubectl`
  host, Helm host, and CI runner

---

## Decision

OctoWatch will run on a **self-managed kubeadm-provisioned Kubernetes cluster on
Azure VMs**.

The selected architecture is:

- **3 cluster nodes** on Azure VMs:
  - 1 control-plane node
  - 2 worker nodes
- **1 dedicated management VM** in the management subnet:
  - SSH bastion / jump host
  - `kubectl` and Helm administration endpoint
  - GitHub Actions self-hosted runner
  - etcd backup host
- **Terraform-managed infrastructure** for networking, load balancer, storage,
  node bootstrap, and management VM bootstrap
- **Helm-based application deployment** onto the kubeadm cluster

AKS is no longer the recommended deployment target for OctoWatch. It remains in
Terraform only as a compatibility path for legacy environments that still need
it.

---

## Consequences

### Positive

- **Full operational control** over Kubernetes bootstrap, upgrades, add-ons,
  storage classes, ingress mode, and node placement.
- **Lower Azure service cost** by removing the managed AKS control-plane path
  from the primary architecture.
- **Simpler infrastructure model** that maps directly to OctoWatch's actual
  needs: one bastion/admin VM, one cluster subnet, one public load balancer.
- **Single source of truth in Terraform** for the entire Azure footprint,
  including the management VM and kubeadm cluster nodes.

### Negative / Trade-offs

- **Cluster lifecycle becomes our responsibility**: Kubernetes upgrades, OS
  patching, node replacement, and operational runbooks must be owned by the
  platform team.
- **More direct infrastructure ownership** means more responsibility for etcd
  backups, ingress controller maintenance, and storage-class decisions.
- **Legacy AKS paths remain in the repository** and must be clearly documented
  as deprecated to avoid operator confusion.

---

## Migration Path

The migration from AKS to the self-managed cluster followed this sequence:

1. **Provision the new infrastructure** with Terraform:
   - management VM
   - 3-node kubeadm cluster
   - Azure Standard Load Balancer
2. **Migrate data** from the existing environment using `pg_dump` / `pg_restore`.
3. **Deploy OctoWatch** to the new cluster with the Helm chart.
4. **Validate application health** on the new ingress endpoint.
5. **Cut DNS over** to the new load balancer IP.
6. **Retire or gate the old AKS resources** behind `var.enable_aks`.

This path preserved the existing application packaging model (Helm) while moving
cluster ownership from AKS to self-managed Kubernetes.

---

## Alternatives Considered

| Alternative | Reason rejected |
|-------------|-----------------|
| Stay on AKS | Higher ongoing platform abstraction and less direct control than desired |
| Move to Azure Container Apps | No longer aligned with the preferred operating model; documented as deprecated/archived |
| Return to single-VM Docker Compose for production | Useful for development and small installs, but not the desired primary production topology |
