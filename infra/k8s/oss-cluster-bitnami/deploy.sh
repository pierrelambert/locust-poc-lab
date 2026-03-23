#!/usr/bin/env bash
# deploy.sh — Deploy Redis Cluster via Bitnami Helm chart
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="redis-cluster-bitnami"

echo "══════════════════════════════════════════"
echo "  Redis Cluster (Bitnami) — Deploy"
echo "══════════════════════════════════════════"

# Prerequisites
command -v helm  >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Cannot reach k8s cluster"; exit 1; }
echo "✅ Prerequisites OK"

# Helm repo
helm repo list 2>/dev/null | grep -q bitnami || helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update >/dev/null

# Namespace
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Storage class
STORAGE_CLASS=$(bash "${SCRIPT_DIR}/../detect-storage-class.sh")
echo "Using StorageClass: ${STORAGE_CLASS}"

# Values
VALUES_FILE=$(mktemp)
trap 'rm -f "${VALUES_FILE}"' EXIT
cat > "${VALUES_FILE}" <<EOF
cluster:
  nodes: 6
  replicas: 1
usePassword: false
persistence:
  enabled: true
  storageClass: ${STORAGE_CLASS}
  size: 1Gi
redis:
  resources:
    requests: { memory: 256Mi, cpu: 100m }
    limits:   { memory: 512Mi, cpu: 500m }
  configmap: |
    cluster-enabled yes
    cluster-node-timeout 2000
    cluster-replica-validity-factor 0
    cluster-require-full-coverage no
    appendonly yes
    appendfsync everysec
metrics:
  enabled: true
  resources:
    requests: { memory: 64Mi, cpu: 50m }
    limits:   { memory: 128Mi, cpu: 100m }
EOF

helm upgrade --install redis-cluster bitnami/redis-cluster \
    --namespace "${NAMESPACE}" \
    --values "${VALUES_FILE}" \
    --wait --timeout=10m

echo "Waiting for pods…"
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=redis-cluster \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo ""
echo "✅ Redis Cluster (Bitnami) deployed in namespace ${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}"

