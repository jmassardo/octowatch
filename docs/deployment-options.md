# OctoWatch Azure Deployment Options

**Version**: 1.0  
**Last Updated**: 2025  
**Status**: Reference Guide

---

## Table of Contents

1. [Overview](#overview)
2. [Application Stack Summary](#application-stack-summary)
3. [⚠️ Key Constraint: TimescaleDB](#️-key-constraint-timescaledb)
4. [Deployment Options](#deployment-options)
   - [Option 1: Single VM + Docker Compose](#option-1-single-vm--docker-compose)
   - [Option 2: Multi-VM High Availability](#option-2-multi-vm-high-availability)
   - [Option 3: Azure Container Apps](#option-3-azure-container-apps)
   - [Option 4: AKS (Azure Kubernetes Service)](#option-4-aks-azure-kubernetes-service)
   - [Option 5: Native Azure PaaS](#option-5-native-azure-paas)
   - [Option 6: Hybrid VM + Container Apps](#option-6-hybrid-vm--container-apps)
5. [Comparison Matrix](#comparison-matrix)
6. [Decision Guide](#decision-guide)
7. [Scaling Paths](#scaling-paths)
8. [Implementation Status](#implementation-status)
9. [Enterprise Sizing Guide](#enterprise-sizing-guide)
   - [Understanding Your Event Volume](#understanding-your-event-volume)
   - [Enterprise Scale: The Numbers](#enterprise-scale-the-numbers)
   - [Recommended Deployment: AKS](#recommended-deployment-aks)
   - [Ingest Pipeline Sizing](#ingest-pipeline-sizing)
   - [Cost Estimate for Enterprise Deployment](#cost-estimate-for-enterprise-deployment)
   - [Demo Environment Sizing](#demo-environment-sizing)

---

## Overview

OctoWatch can be deployed on Azure in six distinct ways, each making different trade-offs between cost, operational complexity, availability, and managed-service adoption. This guide helps you choose the right option for your situation — whether you are a developer standing up a proof-of-concept in an afternoon, an ops engineer designing a production-grade deployment for an enterprise security team, or a technical architect evaluating total cost of ownership.

Each option is documented with an ASCII architecture diagram, cost estimates based on current Azure list pricing (East US 2 region), honest pros and cons, and a clear "best for" recommendation. Where Terraform or Helm IaC already exists in this repository, that is called out explicitly.

**A note on cost estimates**: All figures use Azure Pay-As-You-Go list prices and represent a typical monthly spend range from minimum-viable to comfortable-production configurations. Reserved Instance (1-year) pricing reduces VM costs by approximately 30–40%. Your actual costs will vary based on region, data egress, storage I/O, and negotiated enterprise agreements.

---

## Application Stack Summary

OctoWatch consists of the following services:

| Service | Technology | Stateful? | Scaling Characteristic |
|---|---|---|---|
| **API** | FastAPI (Python) | No | Horizontally scalable; sessions stored in Valkey |
| **Worker: Ingestion** | Celery | No | Scale out for parallel source ingestion |
| **Worker: Detection** | Celery | No | CPU-bound rule evaluation; scale to vCPU count |
| **Worker: Baseline** | Celery | No | I/O-bound; single replica is fine |
| **Beat Scheduler** | Celery Beat | No | **Must be exactly 1 replica** — duplicates cause double-scheduled tasks |
| **Frontend** | React SPA (nginx-served) | No | Horizontally scalable static content |
| **Database** | TimescaleDB (PostgreSQL 16 + extension) | **Yes** | Requires persistent disk; TimescaleDB extension mandatory |
| **Cache / Queue** | Valkey 7.2 (Redis-compatible) | Semi | Session state + Celery broker; AOF persistence for dedup keys |
| **Object Storage** | None (HEC push) / S3-compatible / Azure Blob | Optional | Stores raw `.json.gz` audit log files when using S3 or Azure Blob ingestion mode (100 Gi+ typical) |
| **Reverse Proxy** | nginx | No | TLS termination + routing |

**Key characteristics**:

- **Stateless tier** (API, Workers, Frontend): freely horizontally scalable, no shared disk required.
- **Stateful tier** (TimescaleDB, Valkey): requires persistent storage, careful HA design, and backup strategy.
- **TimescaleDB is a hard dependency** — see the constraint section below.
- **HEC is the default ingest mode**: the app's `ingestion.mode` defaults to `hec` (Splunk-compatible HTTP Event Collector push). S3-compatible and Azure Blob modes are also supported. See [Option 5](#option-5-native-azure-paas) and [Option 6](#option-6-hybrid-vm--container-apps).
- **Valkey is Redis-protocol compatible**: Azure Cache for Redis works as a drop-in replacement.

---

## ⚠️ Key Constraint: TimescaleDB

**TimescaleDB is NOT available as an extension on Azure Database for PostgreSQL Flexible Server.**

This is the single most important architectural constraint when planning an OctoWatch Azure deployment. TimescaleDB provides:

- **Hypertables** — time-partitioned tables used by the `events` table for performant time-range queries across billions of rows.
- **Continuous aggregates** — incrementally maintained materialized views that power dashboards.
- **Native compression** — achieves ~90% storage reduction on audit log data.
- **Time-series functions** — `time_bucket()`, `first()`, `last()` used throughout the detection and reporting queries.

Azure's managed PostgreSQL (Flexible Server) only ships a curated allow-list of extensions, and TimescaleDB is not on it.

**Implications by option**:

| Option | TimescaleDB Strategy |
|---|---|
| 1 – Single VM | ✅ TimescaleDB runs in Docker container on the VM — full support |
| 2 – Multi-VM HA | ✅ TimescaleDB on dedicated VM(s) — full support |
| 3 – Container Apps | ✅ TimescaleDB as a Container App with Azure Files persistent volume |
| 4 – AKS | ✅ TimescaleDB via Helm on persistent Azure Disk (Premium SSD) |
| 5 – Native PaaS | ⚠️ **BLOCKER** — requires VM sidecar, ACI instance, or query refactor |
| 6 – Hybrid VM + Container Apps | ✅ TimescaleDB on the dedicated stateful VM |

**If you are evaluating Option 5 (Native PaaS)**, you have three viable paths:
1. **Sidecar VM/ACI**: Run TimescaleDB on a small dedicated Azure VM (B2ms, ~$30/mo) or Azure Container Instances, and point `DATABASE_URL` at it. This is the recommended path with no code changes.
2. **Refactor to plain PostgreSQL**: Remove hypertable DDL and rewrite time-range queries without `time_bucket()`. Significant engineering effort; loses compression and performance at scale.
3. **Accept limitation for PoC**: Use plain PostgreSQL for a non-production evaluation; plan to migrate to a TimescaleDB-capable deployment for production.

---

## Deployment Options

---

### Option 1: Single VM + Docker Compose

> **Status: ✅ Fully Implemented** — Terraform is at [`/terraform/`](../terraform/)

#### Description

The simplest and fastest deployment model. A single Azure Linux VM runs all OctoWatch services inside Docker Compose. The VM's data disk (Premium SSD, configurable size) provides persistence for TimescaleDB and Valkey. An nginx container terminates TLS (self-signed or Let's Encrypt via certbot) and routes traffic.

Secrets are stored in Azure Key Vault and fetched at boot via a user-assigned Managed Identity — no secrets are embedded in Terraform state or cloud-init scripts.

#### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Azure VM  (Standard_D4s_v5 or B2ms/D8s_v5)                │
│  Ubuntu 24.04 LTS                                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Docker Compose Network                              │  │
│  │                                                      │  │
│  │  [nginx :443] ──► [api :8000]                        │  │
│  │       │         ──► [frontend :3001]                 │  │
│  │       │                                              │  │
│  │  [worker-ingestion]  [worker-detection ×2]           │  │
│  │  [worker-baseline]   [beat-scheduler]                │  │
│  │                                                      │  │
│  │  [timescaledb :5432] [valkey :6379]                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Premium SSD Data Disk (/mnt/octowatch-data)  256 GiB      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
    Azure Key Vault (secrets via Managed Identity)
    Azure Storage Account (boot diagnostics + optional backups)
```

#### VM Size Guide

| SKU | vCPUs | RAM | Approx. Monthly Cost | Best For |
|---|---|---|---|---|
| `Standard_B2ms` | 2 | 8 GiB | ~$60–$70/mo | PoC / dev / low-volume |
| `Standard_D4s_v5` | 4 | 16 GiB | ~$140–$160/mo | Standard production |
| `Standard_D8s_v5` | 8 | 32 GiB | ~$280–$320/mo | High-volume / many workers |

> Add ~$20–$30/mo for the 256 GiB Premium SSD data disk, Key Vault (~$5/mo), and Storage Account (~$5/mo). Total all-in: **~$150–$500/month**.

#### When to Use

- Proof-of-concept or internal-team deployments
- Small to medium organizations (< 5M audit events/month)
- Teams without Kubernetes experience
- Budget-constrained deployments
- Situations requiring a fast (< 2 hour) initial deployment

#### Getting Started

```bash
# 1. Clone the repo and navigate to terraform/
cd terraform/

# 2. Create a terraform.tfvars file (see variables.tf for all options)
cat > terraform.tfvars <<EOF
environment        = "prod"
location           = "eastus2"
vm_size            = "Standard_D4s_v5"
dns_label          = "my-octowatch"
ssh_public_key     = "ssh-ed25519 AAAA..."
ghcr_username      = "my-github-user"
ghcr_token         = "ghp_..."
ghcr_owner         = "my-org"
# ... (add all secret_ variables)
EOF

# 3. Deploy
terraform init -backend-config="..." 
terraform apply
```

#### Pros
- ✅ Fully implemented — deploy today
- ✅ Simplest operations model (one VM, one SSH target)
- ✅ Full TimescaleDB support with no constraints
- ✅ Lowest cost option
- ✅ All secrets in Azure Key Vault with Managed Identity
- ✅ Let's Encrypt TLS support built in

#### Cons
- ❌ Single point of failure — VM downtime = application downtime
- ❌ No automatic failover or self-healing
- ❌ Vertical scaling only (requires VM resize + reboot)
- ❌ Manual backup/restore procedures
- ❌ No zero-downtime deployments

---

### Option 2: Multi-VM High Availability

> **Status: 🔧 Needs Build** — Terraform not yet written

#### Description

A production-hardened architecture that eliminates single points of failure by distributing OctoWatch across multiple VMs organized into tiers. Stateless application services (API, workers, frontend) run on VM Scale Sets behind Azure Application Gateway. Stateful services (TimescaleDB, Valkey) each run on dedicated VMs with Azure Availability Zone distribution.

#### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Azure Application Gateway (WAF v2)                                 │
│  + Azure Load Balancer (Standard SKU)                               │
└──────────────┬────────────────────────┬────────────────────────────┘
               │                        │
               ▼                        ▼
    ┌──────────────────┐      ┌──────────────────┐
    │  API VMSS        │      │  Frontend VMSS   │
    │  Zone 1 + 2 + 3  │      │  Zone 1 + 2      │
    │  (D2s_v5 ×2–10) │      │  (B1s ×2)        │
    └──────────────────┘      └──────────────────┘
               │
    ┌──────────────────┐
    │  Worker VMSS     │
    │  (D4s_v5 ×2–8)  │
    │  Beat: 1 VM only │
    └──────────────────┘
               │
    ┌──────────┬────────────┐
    ▼          ▼
┌──────────┐ ┌──────────┐
│ TimescaleDB│ │ Valkey   │
│ Primary   │ │ Primary  │
│ (Zone 1)  │ │ + 2 Sentinels│
│           │ │          │
│ Streaming │ └──────────┘
│ Replica   │
│ (Zone 2)  │
└──────────┘
```

> **Note on Celery Beat**: The Beat scheduler must always run as a single instance. In this architecture, Beat runs on one designated VM (not in the VMSS auto-scaling group) to prevent duplicate task scheduling. A watchdog script or Azure VM health extension should restart it if it crashes.

#### Cost Estimate

| Component | Configuration | Est. Monthly Cost |
|---|---|---|
| App Gateway WAF v2 | Standard | ~$250/mo |
| API VMSS (min 2) | D2s_v5 ×2 | ~$140/mo |
| Worker VMSS (min 2) | D4s_v5 ×2 | ~$280/mo |
| TimescaleDB Primary + Replica | D4s_v5 ×2 + Premium SSD | ~$380/mo |
| Valkey Sentinel ×3 | B2ms ×3 | ~$180/mo |
| **Total (minimum)** | | **~$1,230/mo** |
| **Total (comfortable prod)** | Scaled out | **~$1,940/mo** |

#### When to Use

- Production deployments requiring 99.9%+ uptime SLA
- Organizations with internal ops/SRE teams comfortable managing VMs
- Environments where Kubernetes is not permitted or preferred
- High-volume deployments (> 50M events/month)

#### Pros
- ✅ No single point of failure
- ✅ Availability Zone redundancy
- ✅ Full TimescaleDB support
- ✅ Auto-scaling for stateless tier
- ✅ Familiar VM-based operations model

#### Cons
- ❌ Significantly higher cost (~5× Option 1)
- ❌ Complex to provision and maintain (many VMs, replication configs)
- ❌ No Terraform IaC yet (needs to be built)
- ❌ Manual application deployment coordination across VMSS instances
- ❌ TimescaleDB replication requires PostgreSQL streaming replication setup

---

### Option 3: Azure Container Apps

> **Status: 🔧 Needs Build** — No IaC yet

#### Description

Azure Container Apps (ACA) provides a serverless container platform built on Kubernetes and KEDA (Kubernetes Event-Driven Autoscaling). Stateless services (API, workers, frontend) run as Container Apps with scale-to-zero on the consumption plan, paying only for actual usage. TimescaleDB runs as a Container App with an Azure Files persistent volume mount.

The app already supports `ingestion.mode: azure_blob` natively, allowing Azure Blob Storage to be used with zero code changes to the storage layer. HEC (HTTP Event Collector) push mode is the default and requires no object storage at all.

#### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Azure Container Apps Environment                           │
│  (Consumption Plan — scale to zero)                         │
│                                                             │
│  ┌─────────────┐  ┌────────────────────────────────────┐   │
│  │  API        │  │  Workers (KEDA autoscale)          │   │
│  │  (0–10 rep) │  │  ingestion: 0–5 replicas           │   │
│  │  HTTP scale │  │  detection: 0–10 replicas          │   │
│  └─────────────┘  │  baseline:  0–2 replicas           │   │
│                   │  beat:      1 replica (fixed)      │   │
│  ┌─────────────┐  └────────────────────────────────────┘   │
│  │  Frontend   │                                            │
│  │  (Static)   │  ┌────────────────────────────────────┐   │
│  └─────────────┘  │  TimescaleDB                       │   │
│                   │  Container App (1 replica, min 1)  │   │
│                   │  Azure Files persistent volume     │   │
│                   └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │
    Azure Cache for Redis (replaces Valkey)
    Azure Blob Storage (mode: azure_blob)
    Azure Container Registry
    Azure Key Vault (secrets via Managed Identity)
```

#### Cost Estimate

| Component | Configuration | Est. Monthly Cost |
|---|---|---|
| Container Apps (consumption) | API + workers at moderate load | ~$80–$200/mo |
| TimescaleDB Container App | 2 vCPU / 4 GiB + Azure Files | ~$60–$100/mo |
| Azure Cache for Redis | C1 Standard (1 GiB) | ~$55/mo |
| Azure Blob Storage | 1 TiB + transactions | ~$20–$40/mo |
| Azure Container Registry | Basic tier | ~$5/mo |
| Azure Key Vault | Standard | ~$5/mo |
| **Total** | | **~$225–$405/mo** |

#### KEDA Scaling Configuration

Workers should scale on Valkey queue depth. Example KEDA scaler for the detection worker:

```yaml
# Container App scaling rules (set via Azure CLI or Bicep/ARM)
scale:
  minReplicas: 0
  maxReplicas: 10
  rules:
    - name: valkey-queue-depth
      custom:
        type: redis
        metadata:
          listName: celery
          listLength: "10"   # scale out when >10 items in queue
        auth:
          - secretRef: valkey-password
            triggerParameter: password
```

> **Important**: Celery Beat **must** be configured with `minReplicas: 1` and `maxReplicas: 1` to prevent duplicate scheduled tasks.

#### When to Use

- Variable workloads with quiet periods (scale-to-zero saves money)
- Teams wanting managed infrastructure without Kubernetes management overhead
- Organizations already using Azure Container Apps for other workloads
- Budget-conscious production deployments that can tolerate cold-start latency

#### Pros
- ✅ Scale-to-zero on consumption plan (significant savings for bursty workloads)
- ✅ Built-in KEDA autoscaling for Celery queue depth
- ✅ No cluster management overhead
- ✅ Native Azure Blob integration
- ✅ Azure Cache for Redis is a drop-in Valkey replacement
- ✅ Managed TLS, service discovery, and load balancing

#### Cons
- ❌ TimescaleDB on Azure Files has I/O performance constraints vs dedicated disk
- ❌ Cold-start latency (0→1 replica) for API under scale-to-zero
- ❌ Limited control over container networking compared to AKS
- ❌ Azure Files persistent volumes have higher latency than Premium SSD (affects DB performance at scale)
- ❌ No IaC yet (Bicep/Terraform needs to be written)

---

### Option 4: AKS (Azure Kubernetes Service)

> **Status: 🔧 Ready to Deploy** — Helm chart exists at [`/helm/`](../helm/); AKS cluster Terraform needs writing

#### Description

OctoWatch ships a production-ready Helm chart (`/helm/`) with full configuration for all services. AKS provides a managed Kubernetes control plane, leaving only worker node management to the operator. This is the most operationally flexible option and the recommended path for enterprise deployments with existing Kubernetes expertise.

TimescaleDB runs via the Bitnami PostgreSQL subchart with a custom `initdb` script to enable the TimescaleDB extension — mounted on Azure Disk Premium SSD for storage performance. cert-manager handles Let's Encrypt TLS automatically.

#### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AKS Cluster                                                        │
│                                                                     │
│  ┌────────────────────────────┐   ┌────────────────────────────┐   │
│  │  System Node Pool          │   │  User Node Pool            │   │
│  │  (Standard_D2s_v5 ×3)     │   │  (Standard_D4s_v5 ×2–10)  │   │
│  │  - kube-system             │   │  Autoscale on CPU/memory   │   │
│  │  - cert-manager            │   │                            │   │
│  │  - nginx ingress           │   │  Pods:                     │   │
│  │  - CSI drivers             │   │  - octowatch-api ×2+       │   │
│  └────────────────────────────┘   │  - octowatch-worker-* ×N  │   │
│                                   │  - octowatch-frontend ×2   │   │
│  ┌─────────────────────────────────────────────────────────┐   │   │
│  │  Persistent Workloads (StatefulSets)                    │   │   │
│  │  - timescaledb  (Azure Disk Premium SSD 50Gi+)          │   │   │
│  │  - valkey       (Azure Disk 2Gi)                        │   │   │
│  └─────────────────────────────────────────────────────────┘   │   │
│                                   └────────────────────────────┘   │
│                                                                     │
│  NGINX Ingress Controller ──► cert-manager ──► Let's Encrypt        │
│  Azure Key Vault CSI Driver ──► Secrets in Key Vault                │
└─────────────────────────────────────────────────────────────────────┘
```

#### Deployment

```bash
# 1. Add Helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# 2. Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# 3. Install NGINX ingress
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

# 4. Update helm/values.yaml for your environment, then install OctoWatch
helm dependency build helm/
helm install octowatch helm/ \
  --namespace octowatch --create-namespace \
  -f helm/values.yaml \
  --set global.image.tag=v1.0.0 \
  --set ingress.host=octowatch.example.com
```

#### Managed Services Option

For reduced operational burden, you can replace self-hosted stateful services with Azure managed equivalents (requires `helm/values.yaml` changes):

| Self-Hosted | Azure Managed | Notes |
|---|---|---|
| Valkey (in-cluster) | Azure Cache for Redis | Set `valkey.enabled: false`; configure `VALKEY_URL` env var |
| Object storage (in-cluster) | Azure Blob Storage | Set `ingestion.mode: azure_blob` |
| TimescaleDB (in-cluster) | ❌ Not available | Must stay in-cluster (see TimescaleDB constraint above) |

#### Cost Estimate

| Component | Configuration | Est. Monthly Cost |
|---|---|---|
| AKS System Node Pool | D2s_v5 ×3 (fixed) | ~$210/mo |
| AKS User Node Pool | D4s_v5 ×2–6 (autoscale) | ~$280–$840/mo |
| Azure Disk (DB) | Premium SSD, 100 GiB total | ~$17/mo |
| Azure Load Balancer | Standard | ~$18/mo |
| Container Registry | Standard | ~$20/mo |
| AKS control plane | Free tier or Standard ($0.10/hr) | ~$0–$73/mo |
| **Total** | | **~$563–$1,186/mo** |

> Replacing Valkey with Azure Cache for Redis (~$55/mo) eliminates in-cluster state management overhead — primarily valuable for reduced ops burden.

#### When to Use

- Enterprise production deployments
- Teams with existing Kubernetes / Helm expertise
- Environments requiring GitOps (Flux/ArgoCD) workflows
- Organizations standardizing on AKS for all workloads
- Deployments needing HPA (Horizontal Pod Autoscaler) and fine-grained resource controls
- When you want the ability to run multiple environments (dev/staging/prod) from the same Helm chart

#### Pros
- ✅ Helm chart already exists and is production-ready
- ✅ Full TimescaleDB support with Premium SSD performance
- ✅ HPA autoscaling for all stateless workloads
- ✅ Rolling deployments with zero downtime
- ✅ cert-manager automated TLS renewal
- ✅ Azure Key Vault CSI driver for secrets injection
- ✅ Network policies for pod-to-pod traffic restriction
- ✅ Prometheus metrics / ServiceMonitor already configured in Helm chart

#### Cons
- ❌ Kubernetes management overhead (upgrades, node pool management)
- ❌ Higher baseline cost (3 system nodes always running)
- ❌ Steeper learning curve for teams new to K8s
- ❌ AKS cluster Terraform still needs to be written
- ❌ TimescaleDB PVC backup requires custom CronJob (included in Helm chart as optional)

---

### Option 5: Native Azure PaaS

> **Status: 📋 Planned** — Not yet implemented; requires architectural decisions

#### Description

The most "cloud-native" option, replacing every self-hosted service with an Azure managed equivalent. API and workers run on Azure Container Apps or Azure App Service. The frontend becomes an Azure Static Web App. Valkey is replaced by Azure Cache for Redis. Object storage (for S3/Azure Blob ingest modes) is provided by Azure Blob Storage (natively supported via `ingestion.mode: azure_blob`). HEC push mode requires no object storage at all.

**⚠️ TimescaleDB Blocker**: Azure Database for PostgreSQL Flexible Server does not support the TimescaleDB extension. This must be resolved before production use — see options in the [Key Constraint](#️-key-constraint-timescaledb) section above. The recommended approach is a small dedicated VM or Azure Container Instances running TimescaleDB, VNet-peered to the PaaS environment.

#### Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Azure Front Door / Application Gateway (optional WAF)          │
└──────────────────┬────────────────────────────────┬────────────┘
                   │                                │
                   ▼                                ▼
    ┌──────────────────────────┐    ┌───────────────────────────┐
    │  Azure Container Apps    │    │  Azure Static Web Apps    │
    │  - API (0–N replicas)    │    │  - React frontend         │
    │  - Workers (KEDA)        │    │  - Global CDN             │
    │  - Beat (1 replica)      │    │  Free or Standard tier    │
    └──────────────────────────┘    └───────────────────────────┘
                   │
    ┌──────────────┴────────────────────────────┐
    │              │                            │
    ▼              ▼                            ▼
┌──────────┐  ┌──────────────────┐  ┌────────────────────────┐
│  ⚠️ DB  │  │ Azure Cache for  │  │  Azure Blob Storage    │
│ TimescaleDB│  │ Redis (Standard) │  │  (audit-logs container)│
│ on VM/ACI │  │ Valkey-compatible│  │  mode: azure_blob      │
│ (VNet-    │  │                  │  │                        │
│  peered)  │  └──────────────────┘  └────────────────────────┘
└──────────┘
    │
    ▼
Azure Key Vault
Azure Monitor / Application Insights
```

#### Cost Estimate

| Component | Configuration | Est. Monthly Cost |
|---|---|---|
| Azure Container Apps (consumption) | API + workers | ~$100–$300/mo |
| Azure Static Web Apps | Standard tier | ~$9/mo |
| TimescaleDB VM (workaround) | B2ms + 50 GiB SSD | ~$100/mo |
| Azure Cache for Redis | C1 Standard (1 GiB) | ~$55/mo |
| Azure Blob Storage | 1 TiB + transactions | ~$25/mo |
| Azure Database for PostgreSQL | Flexible, 2 vCPU / 8 GiB | ~$150/mo (if no TimescaleDB) |
| Azure Key Vault + Monitor | Standard | ~$30/mo |
| **Total (with TimescaleDB VM)** | | **~$469–$669/mo** |
| **Total (if refactored to plain PG)** | | **~$369–$569/mo** |

#### When to Use

- Organizations with a strict "no self-managed Kubernetes or VMs" policy (with TimescaleDB exception accepted)
- Maximum managed-service adoption requirements
- Teams wanting Azure-native monitoring and observability out of the box
- PoC environments where TimescaleDB constraints are acceptable short-term

#### Pros
- ✅ Highest managed-service percentage — minimal infrastructure ops
- ✅ Azure Blob + Azure Cache for Redis are drop-in replacements (no code changes needed)
- ✅ Azure Static Web Apps provides global CDN for the frontend at low cost
- ✅ Azure Monitor / Application Insights integration
- ✅ Azure Policy and compliance controls apply to managed services

#### Cons
- ❌ **TimescaleDB is a blocker** — requires VM sidecar or query refactor
- ❌ Highest per-unit cost for managed services vs self-hosted
- ❌ TimescaleDB VM partially negates the "fully managed" narrative
- ❌ No IaC written yet
- ❌ Azure App Service (if used instead of Container Apps) lacks KEDA worker autoscaling

---

### Option 6: Hybrid VM + Container Apps

> **Status: 🔧 Needs Build** — Partially composable from existing Terraform + Container Apps templates

#### Description

The pragmatic "best of both worlds" option. A single dedicated VM hosts the stateful tier (TimescaleDB, Valkey) — reusing the patterns from Option 1's Terraform. The stateless tier (API, workers, frontend) runs on Azure Container Apps with KEDA autoscaling. VNet integration connects the Container Apps environment to the VM's subnet for private connectivity.

This option cleanly separates concerns: the VM is a long-lived, manually managed "data appliance" while the application tier scales automatically and deploys via container image updates.

#### Architecture

```
Internet
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  Azure Container Apps Environment                              │
│  (VNet-integrated — snet-aca: 10.0.2.0/24)                   │
│                                                                │
│  ┌──────────────┐  ┌─────────────────────────────────────┐   │
│  │  API         │  │  Workers (KEDA autoscale)           │   │
│  │  HTTP Scale  │  │  ingestion / detection / baseline   │   │
│  └──────────────┘  │  beat: 1 replica (fixed)            │   │
│                    └─────────────────────────────────────┘   │
│  ┌──────────────┐                                            │
│  │  Frontend    │                                            │
│  └──────────────┘                                            │
└────────────────────────────────────────────────────────────────┘
         │  VNet peering / same VNet
         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stateful VM  (Standard_D4s_v5)                                │
│  (snet-data: 10.0.1.0/24)                                     │
│                                                                │
│  Docker Compose (stateful services only):                      │
│  ┌─────────────────┐  ┌──────────────┐                        │
│  │  TimescaleDB    │  │   Valkey     │                        │
│  │  :5432          │  │   :6379      │                        │
│  └─────────────────┘  └──────────────┘                        │
│                                                                │
│  Premium SSD Data Disk: 256 GiB                               │
└────────────────────────────────────────────────────────────────┘
         │
    Azure Key Vault (both tiers use Managed Identity)
```

#### Cost Estimate

| Component | Configuration | Est. Monthly Cost |
|---|---|---|
| Stateful VM | D4s_v5 + 256 GiB SSD | ~$165/mo |
| Container Apps (consumption) | API + workers | ~$80–$250/mo |
| Azure Container Registry | Basic | ~$5/mo |
| Azure Key Vault | Standard | ~$5/mo |
| Azure Load Balancer | Standard (for ACA ingress) | ~$18/mo |
| **Total** | | **~$273–$443/mo** |

> The default HEC push mode requires no object storage on the VM. If using S3 or Azure Blob ingest modes, object storage can be provided by an S3-compatible backend (e.g., AWS S3, Garage, or any S3-compatible store) or Azure Blob Storage rather than a self-hosted service on the VM.

#### VNet Integration Setup

```bash
# Container Apps environment must use VNet injection
az containerapp env create \
  --name octowatch-aca-env \
  --resource-group rg-octowatch-prod \
  --location eastus2 \
  --infrastructure-subnet-resource-id /subscriptions/.../snet-aca

# The stateful VM NSG must allow inbound from the ACA subnet:
# - Port 5432 (TimescaleDB) from 10.0.2.0/24
# - Port 6379 (Valkey)     from 10.0.2.0/24
```

#### When to Use

- **Recommended option** for most new production deployments
- Teams comfortable managing one VM but wanting modern container scaling
- Organizations wanting managed scaling without Kubernetes overhead
- Budget-conscious production deployments needing TimescaleDB performance
- Deployments expecting variable load (bursty detection events)

#### Pros
- ✅ Full TimescaleDB support with Premium SSD I/O performance
- ✅ KEDA autoscaling for all stateless workloads
- ✅ Lower baseline cost than AKS
- ✅ Simple operational model for the stateful VM (reuse Option 1 patterns)
- ✅ Zero-downtime deployments for stateless tier via Container Apps revision management
- ✅ Composable from existing Terraform + Container Apps bicep/ARM
- ✅ Native Azure Blob supported (use `ingestion.mode: azure_blob` for S3-compatible ingest)

#### Cons
- ❌ More moving parts than Option 1 (VM + Container Apps environment)
- ❌ VNet integration required (adds networking complexity)
- ❌ No IaC written yet (partial reuse of Option 1 Terraform possible)
- ❌ Stateful VM remains a SPOF for data services
- ❌ Beat scheduler must be carefully managed (1 replica in ACA)

---

## Comparison Matrix

| Dimension | Option 1: Single VM | Option 2: Multi-VM HA | Option 3: Container Apps | Option 4: AKS | Option 5: Native PaaS | Option 6: Hybrid |
|---|---|---|---|---|---|---|
| **Implementation Status** | ✅ Done | 🔧 Needs Build | 🔧 Needs Build | 🔧 Helm ready / AKS needs TF | 📋 Planned | 🔧 Needs Build |
| **Complexity** (1=simplest) | ⭐ 1 | ⭐⭐⭐⭐⭐ 5 | ⭐⭐⭐ 3 | ⭐⭐⭐⭐ 4 | ⭐⭐⭐ 3 | ⭐⭐ 2 |
| **Est. Monthly Cost** | $150–$500 | $800–$2,500 | $225–$405 | $400–$1,500 | $370–$670 | $275–$445 |
| **High Availability** | ❌ No | ✅ Full AZ HA | ⚠️ App HA only | ✅ Multi-node | ✅ Managed HA | ⚠️ App HA only |
| **Auto-scaling** | ❌ No | ⚠️ VMSS only | ✅ KEDA | ✅ HPA + KEDA | ✅ KEDA | ✅ KEDA |
| **TimescaleDB Support** | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ⚠️ Workaround | ✅ Full |
| **Managed Services %** | ~5% | ~10% | ~70% | ~30–70% | ~85% | ~50% |
| **Kubernetes Required** | ❌ No | ❌ No | ❌ No | ✅ Yes | ❌ No | ❌ No |
| **Ops Burden** | Low | High | Low-Medium | Medium | Low | Low-Medium |
| **Zero-downtime Deploy** | ❌ No | ⚠️ Complex | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Terraform Available** | ✅ Yes | ❌ No | ❌ No | ❌ Partial | ❌ No | ❌ Partial |
| **Best For** | PoC / small teams | Enterprise HA w/ Ops team | Bursty workloads | Kubernetes shops | Max managed services | Most new prod deployments |

---

## Decision Guide

Use this questionnaire to find your recommended option:

### Q1: Is this a proof-of-concept or evaluation?
→ **Yes** → Use **Option 1 (Single VM)**. It's deployed in under 2 hours with the existing Terraform.

### Q2: Is this a production deployment?
→ Continue to Q3.

### Q3: What is your monthly infrastructure budget?
- **Under $300/month** → **Option 1** (Single VM, B2ms or D4s_v5) or **Option 6** (Hybrid at minimum scale)
- **$300–$500/month** → **Option 6** (Hybrid VM + Container Apps) — best value/capability ratio
- **$500–$1,500/month** → **Option 3** (Container Apps) or **Option 4** (AKS)
- **$1,500+/month** → **Option 2** (Multi-VM HA) or **Option 4** (AKS with managed services)

### Q4: Do you require 99.9%+ uptime SLA?
→ **Yes** → **Option 2** (Multi-VM HA) or **Option 4** (AKS with multi-node pools + AZs)  
→ **No** → Continue to Q5.

### Q5: Does your team have Kubernetes expertise?
→ **Yes** → **Option 4 (AKS)** — the Helm chart is production-ready and maps directly.  
→ **No** → Continue to Q6.

### Q6: Do you expect highly variable load (bursty detection events)?
→ **Yes** → **Option 6** (Hybrid) or **Option 3** (Container Apps) for KEDA autoscaling.  
→ **No** → **Option 1** (Single VM) if budget-constrained, **Option 6** otherwise.

### Q7: Do you have a strict "no self-managed VMs or Kubernetes" policy?
→ **Yes** → **Option 5 (Native PaaS)** — but resolve the TimescaleDB constraint first.  
→ **No** → See recommendations above.

### Q8: Are you scaling to enterprise (millions of users, multiple orgs, strict compliance)?
→ **Option 4 (AKS)** with Azure Policy, OPA Gatekeeper, Azure Defender for Containers,  
and TimescaleDB on dedicated nodes with Azure Disk ZRS.

### Summary Recommendations by Persona

| Persona | Recommended Option |
|---|---|
| **Developer / PoC** | Option 1 — deploy in 2 hours |
| **Startup / Small Security Team** | Option 1 (start) → Option 6 (grow) |
| **Mid-size Org, No K8s** | Option 6 (Hybrid VM + Container Apps) |
| **Mid-size Org, Has K8s** | Option 4 (AKS with existing Helm chart) |
| **Enterprise, Ops Team** | Option 2 (Multi-VM HA) or Option 4 (AKS) |
| **Enterprise, Max Managed** | Option 5 (PaaS) after TimescaleDB resolution |
| **Budget-Constrained Prod** | Option 6 (~$300/mo with scale-to-zero) |

---

## Scaling Paths

OctoWatch is designed so that you can start simple and migrate upward as requirements grow. Below are the recommended evolution paths.

### Path A: PoC → Production (No K8s)

```
Option 1                    Option 6
Single VM          ──────►  Hybrid VM + Container Apps
(deploy today)              (add stateless scaling when load grows)
     │
     │ if HA needed
     ▼
Option 2
Multi-VM HA
```

**Migration steps (Option 1 → Option 6)**:
1. Keep the existing VM as the stateful data tier (no changes to TimescaleDB, Valkey).
2. Create a VNet-integrated Container Apps environment in the same VNet.
3. Deploy API, workers, and frontend as Container Apps.
4. Update NSG rules on the VM to allow inbound from the ACA subnet.
5. Decommission the application containers from Docker Compose on the VM.

### Path B: PoC → Kubernetes

```
Option 1                    Option 4
Single VM          ──────►  AKS
(deploy today)              (migrate using existing Helm chart)
```

**Migration steps (Option 1 → Option 4)**:
1. Provision an AKS cluster (3-node system pool + 2-node user pool).
2. Install cert-manager, NGINX ingress, and Azure Key Vault CSI driver.
3. Run `helm install octowatch helm/` — the Helm chart is already complete.
4. Migrate data: `pg_dump` from VM → restore to TimescaleDB PVC in AKS.
5. Cut DNS over to the AKS ingress IP.

### Path C: Container Apps → Full HA

```
Option 3                    Option 6                    Option 4
Container Apps     ──────►  Hybrid VM + Container Apps  ──────►  AKS
(fast start)                (add dedicated DB VM)                (full K8s)
```

**Trigger for Option 3 → Option 6**: TimescaleDB on Azure Files is showing I/O performance constraints (> 50M events/month, complex aggregation queries), or you need TimescaleDB streaming replication.

**Trigger for Option 6 → Option 4**: You need multi-AZ HA for the database tier, GitOps deployment workflows, or Kubernetes-native policy enforcement.

### Path D: Native PaaS Workaround Resolution

```
Option 5 (TimescaleDB on VM sidecar)  ──────►  Option 5 (TimescaleDB refactored)
                                               (if/when Azure adds extension support)
```

Watch for Azure announcements: [TimescaleDB extension for Azure Database for PostgreSQL is tracked in the Azure Feedback forum](https://feedback.azure.com/). If the extension becomes available, Option 5 becomes a clean fully-managed deployment.

---

## Implementation Status

| Option | Terraform | Helm | Documented | Est. Build Effort |
|---|---|---|---|---|
| **Option 1: Single VM + Docker Compose** | ✅ Complete (`/terraform/`) | N/A | ✅ This doc + deployment-guide.md | — Already done |
| **Option 2: Multi-VM HA** | ❌ Not started | N/A | ✅ This doc | 3–5 weeks (VMSS, AG, DB replication) |
| **Option 3: Azure Container Apps** | ❌ Not started | N/A | ✅ This doc | 1–2 weeks (Bicep/Terraform ACA) |
| **Option 4: AKS** | ❌ AKS cluster TF needed | ✅ Complete (`/helm/`) | ✅ This doc | 1–2 weeks (AKS cluster Terraform) |
| **Option 5: Native PaaS** | ❌ Not started | N/A | ✅ This doc | 2–3 weeks + TimescaleDB decision |
| **Option 6: Hybrid VM + Container Apps** | ⚠️ Partial (reuse Option 1) | N/A | ✅ This doc | 1–2 weeks (ACA env + VNet integration) |

### Recommended Build Priority

Given the Options analysis and typical adoption pattern, the recommended IaC build order is:

1. **Option 4 AKS Terraform** (1–2 weeks) — highest leverage, Helm chart already done, serves enterprise users
2. **Option 6 Hybrid Terraform** (1–2 weeks) — recommended for most new prod deployments, partial reuse of Option 1
3. **Option 3 Container Apps Terraform/Bicep** (1–2 weeks) — for consumption-based cost optimization
4. **Option 5 PaaS Bicep** (2–3 weeks) — after TimescaleDB strategy decision
5. **Option 2 Multi-VM HA Terraform** (3–5 weeks) — for customers with explicit Kubernetes-free HA requirements

---

## Enterprise Sizing Guide

This section covers deployment sizing for large enterprise customers based on
real-world scale analysis. The profile below represents a customer with 35,000
developers, 125 organizations, and 500 audit log events/second — a common
pattern for large enterprises with extensive integration ecosystems.

---

### Understanding Your Event Volume

A critical insight for large enterprises: **audit log volume is dominated by
machine activity, not human developers.**

The table below shows where a 500 eps ingest rate actually comes from in a
typical large enterprise with heavy integration use:

| Source | Estimated EPS | % of Total | Notes |
|---|---|---|---|
| Developer activity (35k devs, 50 events/day, 70% active) | ~14 eps | 3% | Push, PR, review, merge events |
| PM activity (4k PMs, 15 events/day via Jira/Rally/Aha!) | ~0.5 eps | <1% | Webhook callbacks from PM tooling |
| GitHub Actions workflows (~1.17M min/day = ~35M min/month) | ~14 eps | 3% | Workflow run lifecycle events |
| Integration bots (300 integrations × ~10 events/min avg) | ~470 eps | **94%** | CI/CD, security scanners, GitHub Apps |
| **Total** | **~500 eps** | **100%** | Confirmed via Splunk ingest stream |

> **Key takeaway:** If a customer tells you they have "500 events/second," ask
> how many integrations they have. The developers themselves likely account for
> fewer than 5% of that volume. This has major implications for both deployment
> sizing and demo data preparation — generating realistic demo data requires
> seeding integration-bot activity at scale, not just developer events.

---

### Enterprise Scale: The Numbers

The following table shows 6-month data projections at common enterprise ingest
rates. All storage figures assume TimescaleDB native compression (approximately
10× reduction on audit log data, which is highly repetitive JSON).

| Ingest Rate | Total Rows (6 mo) | Raw Storage | Compressed (TimescaleDB ~10×) | Recommended Option |
|---|---|---|---|---|
| **100 eps** | ~1.56 billion | ~780 GB | ~78 GB | Option 4 (AKS) or Option 1 (D8s_v5 + 256 GB disk) |
| **250 eps** | ~3.89 billion | ~1.9 TB | ~195 GB | Option 4 (AKS) — single VM approaching limits |
| **500 eps** | ~7.78 billion | ~3.9 TB | ~390 GB | **Option 4 (AKS) — only viable option** |
| **1,000 eps** | ~15.55 billion | ~7.8 TB | ~780 GB | Option 4 (AKS) with multi-node TimescaleDB or read replicas |

**Derivation**: rows = eps × 86,400 sec/day × 180 days. Raw storage assumes
~500 bytes/row average for audit log JSON. Compressed storage assumes 10×
TimescaleDB column compression on cold chunks.

> At 500 eps and 6 months of retention, you are storing approximately 7.78
> billion rows. TimescaleDB's compression and continuous aggregates are not
> optional at this scale — they are load-bearing architectural components.

---

### Recommended Deployment: AKS

#### Why Single VM and Container Apps Fall Short

For the 500 eps / 35k developer profile, **Option 4 (AKS) is the only viable
production option**:

- **Option 1 (Single VM)**: A single D8s_v5 (8 vCPU / 32 GB) can handle moderate
  ingest rates but cannot isolate the TimescaleDB I/O workload from the Celery
  ingest workers competing for CPU. At 500 eps, ingest workers and the database
  are co-tenants on the same disk I/O bus. Additionally, a single VM has no
  in-region HA — a VM reboot causes a full outage.

- **Option 3 (Container Apps)**: Container Apps scales individual services but
  shares a managed environment. The TimescaleDB container requires a persistent
  Azure Files volume (NFS-mounted), which introduces network storage latency
  that is measurable at high ingest rates. IOPS limits on Azure Files Standard
  and even Premium tiers fall short of the sustained write throughput required
  at 500 eps with concurrent query workloads.

- **Option 5 (Native PaaS)**: Azure Database for PostgreSQL Flexible Server does
  not support the TimescaleDB extension. This is a hard blocker for production
  use. See [⚠️ Key Constraint: TimescaleDB](#️-key-constraint-timescaledb).

#### AKS Node Pool Sizing

The following node pool layout is recommended for a 500 eps enterprise
deployment on AKS. All SKUs reference **East US 2 list pricing**.

| Component | Resource | Recommended SKU | Count | Purpose & Notes |
|---|---|---|---|---|
| AKS System Node Pool | VM | `Standard_D4s_v5` | 2 | `kube-system` workloads (CoreDNS, metrics-server, KEDA operator). Always on; use `CriticalAddonsOnly` taint. |
| API Worker Node Pool | VM | `Standard_D8s_v5` | 2–8 | Stateless API pods + frontend nginx. Autoscales on HTTP RPS (HPA). |
| Ingest Worker Node Pool | VM | `Standard_D8s_v5` | 4–12 | Celery ingest workers. Autoscales on Valkey queue depth via KEDA. |
| TimescaleDB Node | VM | `Standard_E16s_v5` | 1 | 16 vCPU / 128 GB RAM. Memory-optimized for TimescaleDB shared_buffers (32 GB) and work_mem (256 MB per connection). Dedicated node with `NoSchedule` taint. |
| TimescaleDB Data Disk | Disk | Premium SSD v2 | 1 | 2 TB, 6,000 IOPS provisioned, 400 MB/s throughput. Mounted as a Kubernetes PersistentVolume via the Azure Disk CSI driver. |

> **Why `Standard_E16s_v5` for TimescaleDB?** The E-series is memory-optimized
> (8 GB RAM per vCPU vs. 4 GB for D-series). At 500 eps with 7.78 billion rows,
> TimescaleDB's background jobs (compression, continuous aggregate refresh) run
> concurrently with live ingest queries. 128 GB RAM allows a 32 GB
> `shared_buffers` setting, keeping hot chunk data in memory and reducing disk
> reads to near zero for recent data.

#### TimescaleDB Tuning at This Scale

**Chunk interval**: The default 7-day chunk interval is appropriate for
low-to-medium ingest rates. At 500 eps (43 million rows/day), weekly chunks
grow to ~300 million rows before compression. Recommended settings:

```sql
-- Set daily chunks for the events hypertable at high ingest rates
SELECT set_chunk_time_interval('events', INTERVAL '1 day');

-- Enable compression on chunks older than 2 days
ALTER TABLE events SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'org_id, event_type',
  timescaledb.compress_orderby = 'created_at DESC'
);

SELECT add_compression_policy('events', INTERVAL '2 days');
```

**Continuous aggregates** are essential at this scale — never run dashboard
queries directly against the raw `events` hypertable for time ranges > 1 hour:

```sql
-- Hourly rollup: powers the last-24h and last-7d dashboard views
CREATE MATERIALIZED VIEW events_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', created_at) AS bucket,
  org_id,
  event_type,
  actor_type,
  COUNT(*) AS event_count
FROM events
GROUP BY 1, 2, 3, 4
WITH NO DATA;

SELECT add_continuous_aggregate_policy('events_hourly',
  start_offset => INTERVAL '3 hours',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour'
);

-- Daily rollup: powers the last-30d and last-90d views
CREATE MATERIALIZED VIEW events_daily
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', created_at) AS bucket,
  org_id,
  event_type,
  actor_type,
  COUNT(*) AS event_count
FROM events
GROUP BY 1, 2, 3, 4
WITH NO DATA;

SELECT add_continuous_aggregate_policy('events_daily',
  start_offset => INTERVAL '3 days',
  end_offset   => INTERVAL '1 day',
  schedule_interval => INTERVAL '1 day'
);
```

#### Celery Worker Concurrency

At 500 eps, ingest workers are I/O-bound (network fetch from S3/Blob +
database bulk inserts). Recommended Celery concurrency settings:

| Worker Type | Concurrency | Pool | Rationale |
|---|---|---|---|
| `worker-ingestion` | 16–32 | `prefork` | I/O-bound; high concurrency amortizes network wait time |
| `worker-detection` | 8–16 | `prefork` | CPU-bound rule evaluation; match to vCPU count |
| `worker-baseline` | 4 | `prefork` | Low-frequency scheduled job; minimal concurrency needed |
| `beat-scheduler` | 1 | N/A | **Always exactly 1 replica** — duplicates cause double-scheduled tasks |

Set via Helm values (`helm/values.yaml`):

```yaml
workers:
  ingestion:
    concurrency: 24       # D8s_v5 = 8 vCPU; 3× for I/O-bound tasks
    replicaCount: 6       # KEDA scales 4–12 based on queue depth
  detection:
    concurrency: 8        # Match vCPU count for CPU-bound tasks
    replicaCount: 2
```

#### KEDA Autoscaling for Ingest Workers

[KEDA](https://keda.sh/) (Kubernetes Event-Driven Autoscaler) scales the ingest
worker node pool based on the Valkey (Redis-compatible) queue depth. Install
KEDA via the AKS add-on or the official Helm chart, then apply a
`ScaledObject`:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: octowatch-ingest-worker-scaler
  namespace: octowatch
spec:
  scaleTargetRef:
    name: worker-ingestion
  pollingInterval: 15        # Check queue every 15 seconds
  cooldownPeriod:  120       # Wait 2 minutes before scaling down
  minReplicaCount: 4         # Always maintain 4 ingest workers
  maxReplicaCount: 12        # Cap at 12 to stay within node pool budget
  triggers:
    - type: redis
      metadata:
        address: valkey-service.octowatch.svc.cluster.local:6379
        listName: celery          # Celery's default task queue key
        listLength: "500"         # Scale up when queue > 500 tasks
        # One additional worker replica per 500 queued tasks
        activationListLength: "100"
```

> **Alert threshold**: If the Valkey `celery` list length exceeds **5,000
> items** (approximately 10 minutes of backlog at 500 eps), trigger a
> PagerDuty/Slack alert. This indicates ingest workers are falling behind and
> the node pool ceiling (12 replicas) may need to be raised.

#### Object Storage at 500 eps: Scale Considerations

At 500 eps, raw `.json.gz` audit log files arrive at approximately:

- **File arrival rate**: assuming ~10,000 events per file → 1 file every
  20 seconds, or **~4,320 files/day**
- **Daily ingest volume**: ~500 eps × 86,400 sec × ~0.4 KB/event ≈ **~17 GB/day**
  raw; approximately 1.7 GB/day after gzip compression

HEC push mode is the recommended default at this scale — events are pushed directly to OctoWatch's HTTP ingestion endpoint with no intermediate object storage. For S3-compatible or Azure Blob ingest modes, the table below compares approaches:

| Approach | Pros | Cons | When to Use |
|---|---|---|---|
| **HEC push (default)** | No object storage required; lowest latency; no polling | Requires GitHub Enterprise audit log streaming webhook configuration | All new deployments; preferred default |
| **S3-compatible (e.g., AWS S3, Garage)** | Durable intermediate storage; replay capability | Additional infrastructure or cost; polling overhead | Existing S3 workflows; air-gapped environments |
| **Azure Blob + Event Grid** | Fully managed, 99.9% SLA, auto-scales | Egress costs if data leaves region; slight refactor needed | 500+ eps, enterprise production on Azure |

To enable Azure Blob mode, set in your deployment:

```bash
INGEST_MODE=azure_blob
AZURE_BLOB_CONNECTION_STRING=<connection-string>
AZURE_BLOB_CONTAINER_NAME=octowatch-audit-logs
```

---

### Ingest Pipeline Sizing

At 500 eps, the ingest pipeline must process a continuous stream of compressed
audit log files from object storage (S3-compatible or Azure Blob) when using
file-based ingest modes. HEC push mode bypasses object storage entirely. The key sizing
parameters are:

#### File Arrival Rate

Assuming GitHub Enterprise Server batches audit log export files at
~10,000 events per file:

```
500 events/sec ÷ 10,000 events/file = 1 file every 20 seconds
= 3 files/minute
= 4,320 files/day
= ~130,000 files/month
```

Each file is approximately **200–500 KB compressed** (`.json.gz`), decompressing
to 2–5 MB of raw JSON. S3-compatible or Azure Blob storage for 30 days of raw files
is approximately **20–65 GB** — negligible compared to the TimescaleDB footprint.

#### Worker Count Derivation

Each Celery ingest task processes one file: decompress → parse → bulk insert
into TimescaleDB. Profiling on a `Standard_D8s_v5` (8 vCPU, 32 GB):

| Step | Typical Duration |
|---|---|
| Download from S3/Blob (200–500 KB) | ~150–300 ms |
| Decompress + JSON parse (10k events) | ~200–400 ms |
| TimescaleDB bulk insert (10k rows, `COPY`) | ~300–800 ms |
| **Total per file** | **~650 ms – 1.5 seconds** |

At 1 file per 20 seconds and ~1 second per file, a single worker processes
files roughly **20× faster than they arrive**. The minimum number of workers
needed to keep pace is just 1 — but at peak bursts (e.g., a large batch of
historical backfill files) the queue can spike. The KEDA configuration above
with a minimum of 4 workers and autoscale to 12 provides comfortable headroom.

#### Queue Depth Monitoring

Configure Azure Monitor or Prometheus alerts on the Valkey `celery` list length:

| Threshold | Action |
|---|---|
| > 500 tasks | Informational — KEDA is scaling up; no action needed |
| > 2,000 tasks (~7 min backlog) | Warning — investigate if workers are healthy |
| > 5,000 tasks (~17 min backlog) | **Alert** — workers may have crashed or node pool cap is too low |
| > 20,000 tasks | **Page on-call** — ingest is significantly behind; check TimescaleDB |

#### When to Move from S3-Compatible to Azure Blob + Event Grid

Consider replacing a self-hosted S3-compatible backend with Azure Blob + Event Grid when:

- Your audit log retention requirement exceeds 90 days (storage costs favour Blob
  tiering: Hot → Cool → Archive)
- You want to eliminate self-hosted object storage version upgrades and backup management
- Your security team requires Azure RBAC and private endpoint controls on object
  storage

With Azure Blob + Event Grid, file arrival triggers an Event Grid event that
enqueues a Celery task directly — no polling required, and no missed files.

---

### Cost Estimate for Enterprise Deployment

The following cost breakdown reflects a production AKS deployment for the 500
eps / 35,000 developer profile. All pricing is **Azure East US 2 Pay-As-You-Go
list prices** as of 2025. Reserved Instance (1-year) pricing reduces VM costs
by approximately 30–40%.

| Resource | SKU / Details | Est. Monthly Cost |
|---|---|---|
| AKS System node pool (2× `Standard_D4s_v5`, always on) | 2 × ~$140/mo | ~$280 |
| API node pool (avg 4× `Standard_D8s_v5`, autoscales 2–8) | 4 × ~$280/mo avg | ~$1,120 |
| Ingest node pool (avg 8× `Standard_D8s_v5`, autoscales 4–12) | 8 × ~$280/mo avg | ~$2,240 |
| TimescaleDB node (1× `Standard_E16s_v5`, always on) | 1 × ~$1,100/mo | ~$1,100 |
| TimescaleDB data disk (Premium SSD v2, 2 TB, 6,000 IOPS) | ~$0.131/GB + IOPS | ~$280 |
| Azure Load Balancer (Standard) + Public IP | Standard LB + 1 IP | ~$50 |
| Azure Key Vault (secrets + HSM operations) | ~5,000 ops/month | ~$5 |
| Azure Storage Account (TimescaleDB backups, pg_dump daily) | ~50 GB LRS, Cool tier | ~$50 |
| Azure Monitor / Log Analytics (container insights, alerts) | ~5 GB/day ingestion | ~$200 |
| **Total (Pay-As-You-Go)** | | **~$5,325/mo** |
| **Total (1-Year Reserved VMs)** | ~35% saving on VMs | **~$3,700/mo** |

> **Cost notes**:
> - VM costs dominate (~90% of total). Reserved Instances are strongly recommended
>   for the TimescaleDB node and system node pool (always-on workloads).
> - The API and ingest node pools autoscale — average costs depend on actual
>   traffic patterns. The figures above assume moderate sustained load.
> - Azure Blob egress costs are near zero if the AKS cluster and storage account
>   are in the same region.
> - This estimate does **not** include Azure Entra ID (free tier sufficient),
>   GitHub Enterprise licensing, or customer network egress fees.
> - **Region**: All prices reference `eastus2`. Other regions vary by up to ±15%.

---

### Demo Environment Sizing

For a demo environment simulating this customer's 500 eps / 35k developer
profile, the production AKS cluster is unnecessary — the demo workload is
read-heavy after seeding. Use **Option 1 (Single VM)** with an oversized disk:

| Resource | Demo Recommendation |
|---|---|
| VM SKU | `Standard_D8s_v5` (8 vCPU / 32 GB RAM) |
| Data disk | 2 TB Premium SSD v2 |
| Deployment method | Docker Compose (Option 1) |
| Estimated monthly cost | ~$340/mo (VM + disk) |

To seed the demo dataset:

```bash
python scripts/seed_demo_data.py --scale enterprise --seed 42
```

This generates approximately **7.78 billion event rows** across 6 months,
distributed to match the real customer profile:

- 94% integration-bot events (300 bots × realistic event cadence)
- 3% developer events (35k developers, 70% daily active, 50 events/day average)
- 3% GitHub Actions workflow events (~35M compute minutes/month)
- <1% PM-tool events (4k users × Jira/Rally/Aha! webhook callbacks)

**Estimated seeding time**: approximately **2–3 hours** with 4 parallel insert
workers on a `Standard_D8s_v5`. TimescaleDB compression runs automatically
on chunks older than 2 days and will reduce the 390 GB compressed footprint
further as the seeding job progresses.

After seeding, the demo VM handles dashboard queries efficiently because
continuous aggregates (`events_hourly`, `events_daily`) answer most UI queries
without touching the raw hypertable. See
[`docs/demo-data-seeder.md`](demo-data-seeder.md) for full seeder documentation
and `--scale` flag options (`small`, `medium`, `large`, `enterprise`).

---

## Additional Resources

- [`/terraform/`](../terraform/) — Option 1 Single VM deployment IaC
- [`/helm/`](../helm/) — Option 4 AKS Helm chart
- [`/docs/deployment-guide.md`](deployment-guide.md) — Step-by-step deployment guide for Option 1
- [`/docs/security-and-deployment.md`](security-and-deployment.md) — Security architecture, secrets management, environment variable reference
- [`/docs/architecture.md`](architecture.md) — Full system architecture documentation
- [`/docker-compose.yml`](../docker-compose.yml) — Local development and Option 1 service definitions
