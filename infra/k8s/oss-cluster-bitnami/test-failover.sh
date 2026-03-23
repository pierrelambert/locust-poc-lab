#!/usr/bin/env bash
# test-failover.sh — Kill a cluster node, measure failover time, output JSON
set -euo pipefail

NAMESPACE="redis-cluster-bitnami"
VARIANT="cluster-bitnami"
RESULTS_DIR="${RESULTS_DIR:-results/k8s-comparison}"
MONITOR_DURATION="${MONITOR_DURATION:-60}"

echo "══════════════════════════════════════════"
echo "  Failover Test: Cluster (Bitnami)"
echo "══════════════════════════════════════════"

kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || { echo "❌ Namespace ${NAMESPACE} not found — run deploy.sh first"; exit 1; }

# Pick first cluster pod
TARGET_POD=$(kubectl get pods -n "${NAMESPACE}" \
    -l app.kubernetes.io/name=redis-cluster \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[[ -z "${TARGET_POD}" ]] && { echo "❌ No Redis cluster pod found"; exit 1; }
echo "Target pod: ${TARGET_POD}"

# Baseline PING (10s)
echo "Collecting baseline (10s)…"
BASELINE_OK=0; BASELINE_FAIL=0
END=$((SECONDS + 10))
while [[ $SECONDS -lt $END ]]; do
    if kubectl exec -n "${NAMESPACE}" "${TARGET_POD}" -- redis-cli -c CLUSTER INFO 2>/dev/null | grep -q "cluster_state:ok"; then
        BASELINE_OK=$((BASELINE_OK + 1))
    else
        BASELINE_FAIL=$((BASELINE_FAIL + 1))
    fi
    sleep 0.2
done

# Kill pod
echo "💥 Deleting pod ${TARGET_POD}…"
KILL_EPOCH=$(date +%s)
kubectl delete pod -n "${NAMESPACE}" "${TARGET_POD}" --grace-period=0 --force 2>/dev/null || true

# Monitor recovery
echo "Monitoring recovery (${MONITOR_DURATION}s)…"
RECOVER_OK=0; RECOVER_FAIL=0; FIRST_OK_EPOCH=""
END=$((SECONDS + MONITOR_DURATION))
while [[ $SECONDS -lt $END ]]; do
    # Check cluster health via any surviving pod
    ALIVE_POD=$(kubectl get pods -n "${NAMESPACE}" \
        -l app.kubernetes.io/name=redis-cluster \
        --field-selector=status.phase=Running \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -n "${ALIVE_POD}" ]] && kubectl exec -n "${NAMESPACE}" "${ALIVE_POD}" -- \
        redis-cli -c CLUSTER INFO 2>/dev/null | grep -q "cluster_state:ok"; then
        [[ -z "${FIRST_OK_EPOCH}" ]] && FIRST_OK_EPOCH=$(date +%s)
        RECOVER_OK=$((RECOVER_OK + 1))
    else
        RECOVER_FAIL=$((RECOVER_FAIL + 1))
    fi
    sleep 0.5
done

# Calculate
FAILOVER_SECONDS=0
if [[ -n "${FIRST_OK_EPOCH}" ]]; then
    FAILOVER_SECONDS=$(( FIRST_OK_EPOCH - KILL_EPOCH ))
fi

mkdir -p "${RESULTS_DIR}"
RESULTS_FILE="${RESULTS_DIR}/${VARIANT}-failover.json"
cat > "${RESULTS_FILE}" <<EOF
{
  "variant": "${VARIANT}",
  "namespace": "${NAMESPACE}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "kill_epoch": ${KILL_EPOCH},
  "failover_seconds": ${FAILOVER_SECONDS},
  "baseline": { "ok": ${BASELINE_OK}, "fail": ${BASELINE_FAIL} },
  "recovery": { "ok": ${RECOVER_OK}, "fail": ${RECOVER_FAIL} }
}
EOF

echo ""
echo "✅ Failover time: ${FAILOVER_SECONDS}s"
echo "   Results → ${RESULTS_FILE}"

