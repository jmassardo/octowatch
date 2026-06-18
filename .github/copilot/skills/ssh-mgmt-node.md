---
name: ssh-mgmt-node
description: SSH to the OctoWatch management VM (bastion host) to run commands on the cluster. Use for Kubernetes operations, deployments, log inspection, and troubleshooting.
---

# SSH to Management Node Skill

Connect to the OctoWatch management/bastion VM to run commands against the Kubernetes cluster.

## Connection

### Direct to management VM
```bash
ssh octowatch@<mgmt-public-ip>
```

### Jump to K8s nodes via management VM
```bash
ssh -J octowatch@<mgmt-public-ip> octowatch@<node-ip>
```

The management VM IP is available from Terraform outputs:
```bash
cd terraform && terraform output k8s_mgmt_public_ip
```

## Common Operations on Management VM

### Kubernetes cluster status
```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl top nodes
kubectl top pods -A
```

### Application status
```bash
kubectl get pods -n octowatch
kubectl logs -n octowatch deployment/backend --tail=50
kubectl logs -n octowatch deployment/celery-worker --tail=50
```

### Helm operations
```bash
helm list -n octowatch
helm history octowatch -n octowatch
helm rollback octowatch <revision> -n octowatch
```

### Deploy latest
```bash
helm upgrade --install octowatch ./helm \
  -n octowatch \
  -f helm/values.yaml \
  --set backend.image.tag=<tag> \
  --set frontend.image.tag=<tag>
```

### Database access
```bash
kubectl exec -it -n octowatch deployment/backend -- \
  python -c "from app.config import settings; print(settings.database_url)"
```

### Check certificates
```bash
kubectl get certificates -n octowatch
kubectl describe certificate -n octowatch
```

## Safety
- The management VM is the only entry point to the cluster — treat it carefully
- K8s nodes have no public IPs and can only be reached via the mgmt VM
- Always specify namespace (`-n octowatch`) for application commands
- Use `kubectl drain` before taking nodes offline for maintenance
