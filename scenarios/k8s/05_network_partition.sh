#!/usr/bin/env bash
# 05_network_partition.sh — Scenario 5: Network Partition (Kubernetes)
#
# Tests split-brain behavior using NetworkPolicy to isolate a Redis pod
# from the rest of the cluster.
#
# Required environment variables:
#   LOCUST_FILE       - Path to the Locustfile to run
#
# Optional environment variables:
#   K8S_NAMESPACE         - Kubernetes namespace (default: redis-oss)
#   K8S_PARTITION_POD     - Pod to isolate (default: redis-0)
#   K8S_LOCAL_REDIS_PORT  - Local port for Redis port-forward (default: 16379)
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:16379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   PARTITION_DURATION    - How long the partition lasts in seconds (default: 60)
#
# Usage:
#   LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     ./scenarios/k8s/05_network_partition.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/k8s_helpers.sh"

PLATFORM="k8s-oss"
K8S_PARTITION_POD="${K8S_PARTITION_POD:-redis-0}"
PARTITION_DURATION="${PARTITION_DURATION:-60}"

NETPOL_NAME="locust-poc-partition"

# ── NetworkPolicy helpers ─────────────────────────────────────────────────────

inject_k8s_partition() {
    local pod="$1"
    log_info "Injecting NetworkPolicy partition on pod ${pod}..."
    # Get the pod's IP to create a targeted deny policy
    local pod_ip
    pod_ip=$(kubectl get pod "${pod}" -n "${K8S_NAMESPACE}" \
        -o jsonpath='{.status.podIP}' 2>/dev/null)

    # Create a NetworkPolicy that blocks all ingress/egress for the target pod
    # We use the statefulset pod name label (statefulset.kubernetes.io/pod-name)
    cat <<EOF | kubectl apply -n "${K8S_NAMESPACE}" -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ${NETPOL_NAME}
  namespace: ${K8S_NAMESPACE}
  labels:
    app.kubernetes.io/part-of: locust-poc-lab
    lab/purpose: network-partition-test
spec:
  podSelector:
    matchLabels:
      statefulset.kubernetes.io/pod-name: ${pod}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
EOF
    k8s_mark_event "partition_injected" "pod=${pod} pod_ip=${pod_ip}" "${pod}"
    log_ok "NetworkPolicy ${NETPOL_NAME} applied — pod ${pod} is isolated"
}

heal_k8s_partition() {
    log_info "Removing NetworkPolicy partition..."
    kubectl delete networkpolicy "${NETPOL_NAME}" -n "${K8S_NAMESPACE}" --ignore-not-found
    k8s_mark_event "partition_healed" "policy=${NETPOL_NAME}"
    log_ok "NetworkPolicy ${NETPOL_NAME} removed — partition healed"
}

# Ensure partition is cleaned up on exit
_partition_cleanup() {
    kubectl delete networkpolicy "${NETPOL_NAME}" -n "${K8S_NAMESPACE}" --ignore-not-found 2>/dev/null || true
    k8s_cleanup
}
trap _partition_cleanup EXIT

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 5: Network Partition (k8s)                 ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "05_network_partition"
    init_events_log

    # Step 1: Verify k8s environment
    k8s_check_environment
    log_info "Partition target pod: ${K8S_PARTITION_POD}"

    # Start port-forward
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis"
    wait_for_k8s_redis "${K8S_LOCAL_REDIS_PORT}"

    # Step 2: Verify dataset
    k8s_check_dataset "${K8S_LOCAL_REDIS_PORT}"

    # Step 3: Warm up
    log_step 3 "Warm up the workload"
    k8s_mark_event "warmup_start"
    start_locust "${WARMUP_DURATION}s"
    wait_for_locust
    k8s_mark_event "warmup_end"
    log_ok "Warmup complete — discarding warmup data"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && mv "$f" "${f%.csv}_warmup.csv"
    done

    # Step 4: Baseline
    log_step 4 "Run steady-state baseline (${BASELINE_DURATION}s)"
    k8s_capture_redis_info "${K8S_PARTITION_POD}" "pre_baseline"
    k8s_capture_topology "pre_baseline"
    k8s_mark_event "baseline_start"
    start_locust "${BASELINE_DURATION}s"
    wait_for_locust
    k8s_mark_event "baseline_end"
    k8s_capture_redis_info "${K8S_PARTITION_POD}" "post_baseline"
    log_ok "Baseline captured"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && [[ "$f" != *_warmup.csv ]] && [[ "$f" != *_baseline.csv ]] && mv "$f" "${f%.csv}_baseline.csv"
    done

    # Start continuous workload
    log_info "Starting continuous workload for partition phase"
    start_locust
    sleep 10

    # Step 5: Inject partition
    log_step 5 "Inject disruption: NetworkPolicy partition on ${K8S_PARTITION_POD}"
    k8s_capture_redis_info "${K8S_PARTITION_POD}" "pre_partition"
    k8s_capture_topology "pre_partition"
    local partition_epoch
    partition_epoch=$(ts_epoch)
    inject_k8s_partition "${K8S_PARTITION_POD}"

    # Step 6: Mark event
    log_step 6 "Mark event in dashboard timeline"
    log_info "Partition event recorded at epoch ${partition_epoch}"

    # Step 7: Observe during partition
    log_step 7 "Observe degradation and recovery"
    log_info "Partition will remain active for ${PARTITION_DURATION}s..."
    k8s_mark_event "partition_window_start" "duration=${PARTITION_DURATION}s"

    local monitor_interval=5 elapsed=0
    while [[ $elapsed -lt $PARTITION_DURATION ]]; do
        sleep "${monitor_interval}"
        elapsed=$((elapsed + monitor_interval))
        local sentinel_pod
        sentinel_pod=$(kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_SENTINEL_LABEL}" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "${sentinel_pod}" ]]; then
            local sentinel_master
            sentinel_master=$(kubectl exec "${sentinel_pod}" -n "${K8S_NAMESPACE}" -- \
                redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster 2>/dev/null || echo "unknown")
            k8s_mark_event "partition_monitor" "elapsed=${elapsed}s sentinel_master=${sentinel_master}"
        fi
        log_info "Partition active: ${elapsed}s / ${PARTITION_DURATION}s"
    done
    k8s_mark_event "partition_window_end"

    # Heal partition
    log_info "Healing network partition..."
    heal_k8s_partition

    # Monitor recovery
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)
    local recovery_confirmed=false

    # Re-establish port-forward if needed
    stop_port_forwards
    sleep 2
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis" || true

    while [[ $recovery_elapsed -lt $max_recovery_wait ]]; do
        sleep 2
        recovery_elapsed=$(( $(ts_epoch) - recovery_start ))
        local sentinel_pod
        sentinel_pod=$(kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_SENTINEL_LABEL}" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "${sentinel_pod}" ]]; then
            if kubectl exec "${sentinel_pod}" -n "${K8S_NAMESPACE}" -- \
                redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null | grep -q "OK"; then
                recovery_confirmed=true
                k8s_mark_event "recovery_detected" "elapsed=${recovery_elapsed}s"
                break
            fi
        fi
        log_info "Waiting for recovery... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    local total_duration=$(( $(ts_epoch) - partition_epoch ))
    if [[ "${recovery_confirmed}" == "true" ]]; then
        log_ok "Recovery confirmed after ${total_duration}s total (partition: ${PARTITION_DURATION}s)"
        k8s_mark_event "recovery_complete" "total_duration=${total_duration}s"
    else
        log_warn "Recovery not confirmed within ${max_recovery_wait}s after partition heal"
        k8s_mark_event "recovery_timeout" "max_wait=${max_recovery_wait}s"
    fi

    k8s_capture_topology "post_recovery"
    k8s_capture_redis_info "${K8S_PARTITION_POD}" "post_recovery"

    # Step 8: Post-recovery stability
    log_step 8 "Confirm post-recovery stability (${POST_RECOVERY_DURATION}s)"
    k8s_mark_event "post_recovery_observation_start"
    sleep "${POST_RECOVERY_DURATION}"
    k8s_mark_event "post_recovery_observation_end"
    log_ok "Post-recovery observation complete"

    stop_locust
    k8s_capture_topology "final"

    # Step 9: Export evidence
    export_evidence

    # Step 10: Repeat guidance
    log_step 10 "Repeat at least three times"
    log_info "Re-run this script at least 3 times and compare results"
    log_info "Results saved to: ${RUN_DIR}"

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Scorecard Questions (k8s)                                 ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  1. What happened?                                         ║"
    echo "║     → NetworkPolicy partition for ${PARTITION_DURATION}s"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, split-brain writes     ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare write safety and diagnostic clarity          ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Total duration: ${total_duration}s"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

