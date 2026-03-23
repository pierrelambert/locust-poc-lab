#!/usr/bin/env bash
# teardown.sh — Remove Redis Cluster (Bitnami)
set -euo pipefail

NAMESPACE="redis-cluster-bitnami"

echo "Tearing down Redis Cluster (Bitnami)…"
helm uninstall redis-cluster -n "${NAMESPACE}" 2>/dev/null || true
kubectl delete namespace "${NAMESPACE}" --grace-period=0 --force 2>/dev/null || true
echo "✅ Cluster (Bitnami) removed"

