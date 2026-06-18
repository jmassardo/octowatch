---
name: k8s-operations
description: Run Kubernetes operations against the OctoWatch cluster. Use for managing deployments, debugging pods, scaling, and cluster maintenance.
---

# Kubernetes Operations Skill

Run kubectl and helm commands against the OctoWatch Kubernetes cluster. These commands must be run from the management VM (see ssh-mgmt-node skill).

## Cluster Architecture
- 3-node kubeadm cluster: 1 control plane + 2 workers
- CNI: Calico
- Ingress: NGINX Ingress Controller
- TLS: cert-manager with Let's Encrypt
- Application namespace: `octowatch`

## Debugging

### Pod issues
```bash
kubectl describe pod <pod-name> -n octowatch
kubectl logs <pod-name> -n octowatch --previous  # crashed container logs
kubectl exec -it <pod-name> -n octowatch -- /bin/sh
```

### Networking
```bash
kubectl get svc -n octowatch
kubectl get ingress -n octowatch
kubectl describe ingress -n octowatch
```

### Resource pressure
```bash
kubectl top nodes
kubectl top pods -n octowatch --sort-by=memory
kubectl describe node <node-name> | grep -A 5 "Conditions"
```

## Scaling
```bash
kubectl scale deployment backend -n octowatch --replicas=3
kubectl scale deployment celery-worker -n octowatch --replicas=4
```

## Maintenance

### Drain a node for maintenance
```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
# After maintenance:
kubectl uncordon <node-name>
```

### Certificate renewal
```bash
kubectl get certificates -n octowatch
kubectl delete certificate <cert-name> -n octowatch  # triggers renewal
```

### Restart a deployment
```bash
kubectl rollout restart deployment/backend -n octowatch
kubectl rollout status deployment/backend -n octowatch
```
