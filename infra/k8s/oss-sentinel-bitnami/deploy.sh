#!/usr/bin/env bash
# deploy.sh — Deploy Redis Sentinel via Bitnami Helm chart
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="redis-sentinel-bitnami"

echo "══════════════════════════════════════════"
echo "  Redis Sentinel (Bitnami) — Deploy"
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
architecture: replication
auth:
  enabled: false
master:
  count: 1
  persistence:
    enabled: true
    storageClass: ${STORAGE_CLASS}
    size: 1Gi
  resources:
    requests: { memory: 256Mi, cpu: 100m }
    limits:   { memory: 512Mi, cpu: 500m }
replica:
  replicaCount: 2
  persistence:
    enabled: true
    storageClass: ${STORAGE_CLASS}
    size: 1Gi
  resources:
    requests: { memory: 256Mi, cpu: 100m }
    limits:   { memory: 512Mi, cpu: 500m }
sentinel:
  enabled: true
  quorum: 2
  downAfterMilliseconds: 5000
  failoverTimeout: 10000
  parallelSyncs: 1
  resources:
    requests: { memory: 128Mi, cpu: 50m }
    limits:   { memory: 256Mi, cpu: 200m }
metrics:
  enabled: true
  resources:
    requests: { memory: 64Mi, cpu: 50m }
    limits:   { memory: 128Mi, cpu: 100m }
EOF

helm upgrade --install redis-sentinel bitnami/redis \
    --namespace "${NAMESPACE}" \
    --values "${VALUES_FILE}" \
    --wait --timeout=10m

echo "Waiting for pods…"
kubectl wait --for=condition=ready pod \
    -l app.kubernetes.io/name=redis \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo ""
echo "✅ Redis Sentinel (Bitnami) deployed in namespace ${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}"

