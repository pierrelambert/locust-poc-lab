#!/usr/bin/env bash
# deploy.sh — Deploy Redis Cluster via Opstree Redis Operator (Helm + CRDs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="redis-cluster-opstree"

echo "══════════════════════════════════════════"
echo "  Redis Cluster (Opstree) — Deploy"
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

# Apply RedisCluster CRD
echo "Deploying RedisCluster CRD…"
cat <<EOF | kubectl apply -f -
---
apiVersion: redis.redis.opstreelabs.in/v1beta2
kind: RedisCluster
metadata:
  name: redis-cluster
  namespace: ${NAMESPACE}
spec:
  clusterSize: 3
  clusterVersion: v7
  kubernetesConfig:
    image: quay.io/opstree/redis:v7.0.12
    imagePullPolicy: IfNotPresent
  redisExporter:
    enabled: true
    image: quay.io/opstree/redis-exporter:v1.44.0
  redisLeader:
    replicas: 3
    redisConfig:
      additionalRedisConfig: |
        cluster-enabled yes
        cluster-node-timeout 2000
        cluster-replica-validity-factor 0
        cluster-require-full-coverage no
        appendonly yes
        appendfsync everysec
  redisFollower:
    replicas: 3
    redisConfig:
      additionalRedisConfig: |
        cluster-enabled yes
        cluster-node-timeout 2000
        cluster-replica-validity-factor 0
        cluster-require-full-coverage no
        appendonly yes
        appendfsync everysec
  storage:
    volumeClaimTemplate:
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: ${STORAGE_CLASS}
        resources:
          requests:
            storage: 1Gi
EOF

echo "Waiting for leader pods…"
kubectl wait --for=condition=ready pod \
    -l app=redis-cluster-leader \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo "Waiting for follower pods…"
kubectl wait --for=condition=ready pod \
    -l app=redis-cluster-follower \
    -n "${NAMESPACE}" \
    --timeout=300s || echo "⚠️  Some pods not ready yet"

echo ""
echo "✅ Redis Cluster (Opstree) deployed in namespace ${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}"

