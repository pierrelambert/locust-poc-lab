#!/usr/bin/env bash
# teardown.sh — Remove Redis Sentinel (Opstree)
set -euo pipefail

NAMESPACE="redis-sentinel-opstree"

echo "Tearing down Redis Sentinel (Opstree)…"
kubectl delete namespace "${NAMESPACE}" --grace-period=0 --force 2>/dev/null || true
echo "✅ Sentinel (Opstree) removed"

