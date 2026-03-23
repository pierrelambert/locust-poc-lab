#!/usr/bin/env bash
# 02_primary_kill.sh — Scenario 2: Primary Process Kill (Kubernetes)
#
# Kills the primary Redis pod via kubectl delete and measures
# failover quality, recovery time, and client impact.
#
# Required environment variables:
#   LOCUST_FILE       - Path to the Locustfile to run
#
# Optional environment variables:
#   K8S_NAMESPACE         - Kubernetes namespace (default: redis-oss)
#   K8S_PRIMARY_POD       - Pod to kill (default: redis-0)
#   K8S_LOCAL_REDIS_PORT  - Local port for Redis port-forward (default: 16379)
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:16379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#
# Usage:
#   LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     ./scenarios/k8s/02_primary_kill.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/k8s_helpers.sh"

PLATFORM="k8s-oss"
K8S_PRIMARY_POD="${K8S_PRIMARY_POD:-redis-0}"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 2: Primary Process Kill (k8s)              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "02_primary_kill"
    init_events_log

    # Step 1: Verify k8s environment
    k8s_check_environment
    local primary_node
    primary_node=$(k8s_get_pod_node "${K8S_PRIMARY_POD}")
    log_info "Primary pod: ${K8S_PRIMARY_POD} on node: ${primary_node}"

    # Start port-forward to Redis service (survives pod deletion via service)
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

    # Step 5: Kill the primary pod
    log_step 5 "Inject disruption: kubectl delete pod ${K8S_PRIMARY_POD}"
    k8s_capture_redis_info "${K8S_PRIMARY_POD}" "pre_kill"
    k8s_capture_topology "pre_kill"
    local kill_epoch
    kill_epoch=$(ts_epoch)
    k8s_mark_event "primary_kill_start" "pod=${K8S_PRIMARY_POD}" "${K8S_PRIMARY_POD}" "${primary_node}"
    kubectl delete pod "${K8S_PRIMARY_POD}" -n "${K8S_NAMESPACE}" --grace-period=0 --force 2>/dev/null || true
    k8s_mark_event "primary_kill_done" "pod=${K8S_PRIMARY_POD}" "${K8S_PRIMARY_POD}" "${primary_node}"
    log_ok "Primary pod deleted: ${K8S_PRIMARY_POD}"

    # Step 6: Mark event
    log_step 6 "Mark event in dashboard timeline"
    log_info "Kill event recorded at epoch ${kill_epoch}"

    # Step 7: Observe failover
    log_step 7 "Observe degradation and recovery"
    log_info "Monitoring failover behavior..."
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)
    local new_primary_found=false

    # Re-establish port-forward (old one may have died with the pod)
    stop_port_forwards
    sleep 3

    # Wait for StatefulSet to recreate the pod
    log_info "Waiting for pod ${K8S_PRIMARY_POD} to be recreated..."
    local pod_wait=0
    while [[ $pod_wait -lt 60 ]]; do
        if kubectl get pod "${K8S_PRIMARY_POD}" -n "${K8S_NAMESPACE}" &>/dev/null; then
            break
        fi
        sleep 1; pod_wait=$((pod_wait + 1))
    done

    # Wait for pod ready
    wait_for_pod_ready "${K8S_PRIMARY_POD}" 120 || true

    # Re-establish port-forward
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis"

    # Check sentinel for failover detection
    while [[ $recovery_elapsed -lt $max_recovery_wait ]]; do
        sleep 2
        recovery_elapsed=$(( $(ts_epoch) - recovery_start ))
        local sentinel_pod
        sentinel_pod=$(kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_SENTINEL_LABEL}" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "${sentinel_pod}" ]]; then
            if kubectl exec "${sentinel_pod}" -n "${K8S_NAMESPACE}" -- \
                redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null | grep -q "OK"; then
                new_primary_found=true
                k8s_mark_event "failover_detected" "elapsed=${recovery_elapsed}s" "${K8S_PRIMARY_POD}"
                break
            fi
        fi
        log_info "Waiting for failover... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    if [[ "${new_primary_found}" == "true" ]]; then
        local failover_duration=$(( $(ts_epoch) - kill_epoch ))
        log_ok "Failover detected after ${failover_duration}s total"
        k8s_mark_event "failover_complete" "duration=${failover_duration}s"
    else
        log_warn "Failover not confirmed within ${max_recovery_wait}s"
        k8s_mark_event "failover_timeout" "max_wait=${max_recovery_wait}s"
    fi

    k8s_capture_topology "post_failover"

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
    echo "║     → Primary pod deleted; review events.jsonl             ║"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, latency spikes         ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare failover duration across platforms           ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

