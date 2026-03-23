#!/usr/bin/env bash
# teardown.sh — Remove Redis Sentinel (Bitnami)
set -euo pipefail

NAMESPACE="redis-sentinel-bitnami"

echo "Tearing down Redis Sentinel (Bitnami)…"
helm uninstall redis-sentinel -n "${NAMESPACE}" 2>/dev/null || true
kubectl delete namespace "${NAMESPACE}" --grace-period=0 --force 2>/dev/null || true
echo "✅ Sentinel (Bitnami) removed"

