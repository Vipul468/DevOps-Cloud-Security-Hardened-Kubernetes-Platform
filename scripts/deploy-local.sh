#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-hardened-k8s-app:local}"

echo "Building image..."
docker build -t "${IMAGE_NAME}" -f docker/Dockerfile .

echo "Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/networkpolicy.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

echo "Waiting for deployment..."
kubectl rollout status deployment/hardened-app -n hardened-app

echo "Deployment complete."
kubectl get pods -n hardened-app
kubectl get svc -n hardened-app
