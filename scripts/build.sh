#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-hardened-k8s-app:local}"

echo "Building ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" -f docker/Dockerfile .

echo "Build completed."
