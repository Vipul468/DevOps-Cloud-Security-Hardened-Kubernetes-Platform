# Architecture

```text
Developer
   |
   v
GitHub Repository
   |
   v
GitHub Actions CI
   |-- pytest
   |-- Docker build
   |
   v
Docker Image
   |
   v
Kubernetes
   |
   +-- Namespace
   +-- Ingress
   +-- Service
   +-- Deployment (2 replicas)
   +-- ConfigMap
   +-- RBAC
   +-- NetworkPolicy
   +-- Pod Security / seccomp / non-root
```

The project starts locally and can later be extended to AWS EKS with Terraform.
