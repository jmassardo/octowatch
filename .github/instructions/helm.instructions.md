---
applyTo: "helm/**"
---

# Helm Chart Instructions

## Chart Structure
- Single Helm chart for the complete OctoWatch stack
- Deploys: backend (FastAPI), frontend (Nginx), Celery workers, Valkey, ingress

## Conventions
- Use `{{ .Values.x }}` for all configurable values — no hardcoded images, replicas, or resource limits
- Image tags default to `{{ .Chart.AppVersion }}` but are overridable via `values.yaml`
- All containers include `resources.requests` and `resources.limits`
- Use `envFrom` with `secretRef` for sensitive configuration (DB passwords, API keys)
- Probes: `livenessProbe` and `readinessProbe` on all long-running containers

## Deployment Targets
- Self-managed kubeadm cluster (3 nodes) — primary production target
- Deployed via `helm upgrade --install` from the management VM's CI runner

## Values Organization
- `values.yaml` — defaults for production
- Override files can be passed via `-f` flag for different environments
