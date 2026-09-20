# DevOps Cloud Security-Hardened Kubernetes Platform

A beginner-friendly DevOps project demonstrating a security-hardened Flask application on Kubernetes.

## Components
- Python Flask application
- Docker container
- Kubernetes Namespace, ConfigMap, Deployment, Service, Ingress
- RBAC and NetworkPolicy
- Terraform project structure for infrastructure automation
- GitHub Actions CI
- Local deployment scripts

## Project goal
Build and understand the platform from scratch. Start locally with Docker/Kubernetes, then add Terraform and cloud deployment.

## Local quick start
```bash
cd app
pip install -r requirements.txt
python app.py
```

Run tests:
```bash
pytest
```

Build Docker image:
```bash
docker build -t hardened-k8s-app:local -f docker/Dockerfile .
```

Deploy to a local Kubernetes cluster:
```bash
bash scripts/deploy-local.sh
```

> The Terraform files are intentionally a starting scaffold. Cloud-specific resources should be added after the local Kubernetes lab is working.
