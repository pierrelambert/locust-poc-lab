#!/usr/bin/env bash
# 03_node_loss.sh — Scenario 3: Node Loss (Kubernetes)
#
# Tests recovery when a k8s node is drained/cordoned, simulating
# a full node disappearance. Uses kubectl drain + cordon.
#
# Required environment variables:
#   LOCUST_FILE       - Path to the Locustfile to run
#
# Optional environment variables:
#   K8S_NAMESPACE         - Kubernetes namespace (default: redis-oss)
#   K8S_PRIMARY_POD       - Pod whose node to drain (default: redis-0)
#   K8S_LOCAL_REDIS_PORT  - Local port for Redis port-forward (default: 16379)
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:16379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   NODE_DOWN_DURATION    - How long the node stays cordoned in seconds (default: 30)
#
# Usage:
#   LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     ./scenarios/k8s/03_node_loss.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/k8s_helpers.sh"

PLATFORM="k8s-oss"
K8S_PRIMARY_POD="${K8S_PRIMARY_POD:-redis-0}"
NODE_DOWN_DURATION="${NODE_DOWN_DURATION:-30}"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 3: Node Loss (k8s)                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "03_node_loss"
    init_events_log

    # Step 1: Verify k8s environment
    k8s_check_environment
    local target_node
    target_node=$(k8s_get_pod_node "${K8S_PRIMARY_POD}")
    if [[ -z "${target_node}" ]]; then
        log_error "Could not determine node for pod ${K8S_PRIMARY_POD}"
        exit 1
    fi
    log_info "Target node: ${target_node} (hosting pod ${K8S_PRIMARY_POD})"

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
    k8s_capture_redis_info "${K8S_PRIMARY_POD}" "pre_baseline"
    k8s_capture_topology "pre_baseline"
    k8s_mark_event "baseline_start"
    start_locust "${BASELINE_DURATION}s"
    wait_for_locust
    k8s_mark_event "baseline_end"
    k8s_capture_redis_info "${K8S_PRIMARY_POD}" "post_baseline"
    log_ok "Baseline captured"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && [[ "$f" != *_warmup.csv ]] && [[ "$f" != *_baseline.csv ]] && mv "$f" "${f%.csv}_baseline.csv"
    done

    # Start continuous workload
    log_info "Starting continuous workload for disruption and recovery phases"
    start_locust
    sleep 10

    # Step 5: Drain the node
    log_step 5 "Inject disruption: kubectl drain ${target_node}"
    k8s_capture_redis_info "${K8S_PRIMARY_POD}" "pre_node_loss"
    k8s_capture_topology "pre_node_loss"
    local drain_epoch
    drain_epoch=$(ts_epoch)
    k8s_mark_event "node_drain_start" "node=${target_node}" "${K8S_PRIMARY_POD}" "${target_node}"
    kubectl drain "${target_node}" --ignore-daemonsets --delete-emptydir-data \
        --force --grace-period=10 --timeout=60s 2>&1 | tee "${RUN_DIR}/drain_output.txt" || true
    k8s_mark_event "node_drain_done" "node=${target_node}" "${K8S_PRIMARY_POD}" "${target_node}"
    log_ok "Node drained: ${target_node}"

    # Step 6: Mark event
    log_step 6 "Mark event in dashboard timeline"
    log_info "Drain event recorded at epoch ${drain_epoch}"

    # Step 7: Observe during node outage
    log_step 7 "Observe degradation and recovery"
    log_info "Node will remain cordoned for ${NODE_DOWN_DURATION}s..."
    k8s_mark_event "node_down_window_start" "duration=${NODE_DOWN_DURATION}s"

    # Re-establish port-forward (may have died)
    stop_port_forwards
    sleep 3
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis" || true

    sleep "${NODE_DOWN_DURATION}"
    k8s_mark_event "node_down_window_end"

    # Uncordon the node
    log_info "Uncordoning node: ${target_node}"
    k8s_mark_event "node_uncordon_start" "node=${target_node}" "" "${target_node}"
    kubectl uncordon "${target_node}"
    k8s_mark_event "node_uncordon_done" "node=${target_node}" "" "${target_node}"
    log_ok "Node uncordoned: ${target_node}"

    # Wait for pods to reschedule
    log_info "Waiting for pods to become ready..."
    wait_for_all_pods_ready "${K8S_REDIS_LABEL}" 180 || true
    wait_for_all_pods_ready "${K8S_SENTINEL_LABEL}" 120 || true

    # Re-establish port-forward
    stop_port_forwards
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis" || true

    # Monitor sentinel recovery
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)
    local recovery_confirmed=false

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

    local total_duration=$(( $(ts_epoch) - drain_epoch ))
    if [[ "${recovery_confirmed}" == "true" ]]; then
        log_ok "Recovery confirmed after ${total_duration}s total"
        k8s_mark_event "recovery_complete" "total_duration=${total_duration}s"
    else
        log_warn "Recovery not confirmed within ${max_recovery_wait}s"
        k8s_mark_event "recovery_timeout" "max_wait=${max_recovery_wait}s"
    fi

    k8s_capture_topology "post_recovery"

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
    echo "║     → Node drained for ${NODE_DOWN_DURATION}s then uncordoned"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, latency spikes         ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare recovery duration and operator effort        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

