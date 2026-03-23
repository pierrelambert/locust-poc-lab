#!/usr/bin/env bash
# deploy.sh — Deploy Redis Sentinel via Opstree Redis Operator (Helm + CRDs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="redis-sentinel-opstree"

echo "══════════════════════════════════════════"
echo "  Redis Sentinel (Opstree) — Deploy"
echo "══════════════════════════════════════════"

# Prerequisites
command -v helm  >/dev/null 2>&1 || { echo "❌ helm not found"; exit 1; }
kubectl cluster-info >/dev/null 2>&1 || { echo "❌ Cannot reach k8s cluster"; exit 1; }
echo "✅ Prerequisites OK"

# Namespace
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Helm repo — Opstree operator
helm repo list 2>/dev/null | grep -q ot-helm || helm repo add ot-helm https://ot-container-kit.github.io/helm-charts/
helm repo update >/dev/null

echo "Installing Opstree Redis Operator…"
helm upgrade --install redis-operator ot-helm/redis-operator \
    --namespace "${NAMESPACE}" \
    --wait --timeout=5m

# Storage class
STORAGE_CLASS=$(bash "${SCRIPT_DIR}/../detect-storage-class.sh")
echo "Using StorageClass: ${STORAGE_CLASS}"

# Apply CRDs
echo "Deploying Redis + RedisSentinel CRDs…"
cat <<EOF | kubectl apply -f -
---
apiVersion: redis.redis.opstreelabs.in/v1beta2
kind: Redis
metadata:
  name: redis-sentinel
  namespace: ${NAMESPACE}
spec:
  kubernetesConfig:
    image: quay.io/opstree/redis:v7.0.12
    imagePullPolicy: IfNotPresent
  redisExporter:
    enabled: true
    image: quay.io/opstree/redis-exporter:v1.44.0
  storage:
    volumeClaimTemplate:
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: ${STORAGE_CLASS}
        resources:
          requests:
            storage: 1Gi
  redisConfig:
    additionalRedisConfig: |
      appendonly yes
      appendfsync everysec
---
apiVersion: redis.redis.opstreelabs.in/v1beta2
kind: RedisSentinel
metadata:
  name: redis-sentinel
  namespace: ${NAMESPACE}
spec:
  clusterSize: 3
  kubernetesConfig:
    image: quay.io/opstree/redis-sentinel:v7.0.12
    imagePullPolicy: IfNotPresent
  redisExporter:
    enabled: true
    image: quay.io/opstree/redis-exporter:v1.44.0
  redisSentinelConfig:
    redisReplicationName: redis-sentinel
    additionalSentinelConfig: |
      down-after-milliseconds 5000
      failover-timeout 10000
      parallel-syncs 1
EOF

echo "Waiting for Redis pods…"
kubectl wait --for=condition=ready pod \
    -l app=redis-sentinel \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo "Waiting for Sentinel pods…"
kubectl wait --for=condition=ready pod \
    -l app=redis-sentinel-sentinel \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo ""
echo "✅ Redis Sentinel (Opstree) deployed in namespace ${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}"

