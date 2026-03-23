#!/usr/bin/env bash
# teardown.sh — Remove Redis Cluster (Opstree)
set -euo pipefail

NAMESPACE="redis-cluster-opstree"

echo "Tearing down Redis Cluster (Opstree)…"
kubectl delete namespace "${NAMESPACE}" --grace-period=0 --force 2>/dev/null || true
echo "✅ Cluster (Opstree) removed"

