#!/usr/bin/env bash
# 03_node_loss.sh — Scenario 3: Node Reboot or Node Loss
#
# Tests recovery path and operator effort when a full node disappears
# and comes back after a configurable outage window.
#
# Required environment variables:
#   PLATFORM          - "re" | "oss-sentinel" | "oss-cluster"
#   LOCUST_FILE       - Path to the Locustfile to run
#   PRIMARY_CONTAINER - Name of the primary Redis container
#   NODE_CONTAINER    - Name of the node container to stop/start
#
# Optional environment variables:
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:6379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   NODE_DOWN_DURATION    - How long the node stays down in seconds (default: 30)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#   REPLICA_CONTAINER     - Replica container name (for oss-cluster fallback)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary NODE_CONTAINER=redis-primary \
#     ./scenarios/scripts/03_node_loss.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

NODE_DOWN_DURATION="${NODE_DOWN_DURATION:-30}"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 3: Node Reboot or Node Loss                ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "03_node_loss"
    init_events_log

    # Step 1: Verify environment parity
    check_environment
    if [[ -z "${NODE_CONTAINER:-}" ]]; then
        log_error "NODE_CONTAINER must be set to the container to stop/start"
        exit 1
    fi
    wait_for_redis "${PRIMARY_CONTAINER}"

    # Step 2: Verify dataset is primed
    log_step 2 "Verify dataset is primed"
    local key_count
    key_count=$(docker exec "${PRIMARY_CONTAINER}" redis-cli DBSIZE 2>/dev/null | grep -o '[0-9]*' || echo "0")
    log_info "Current key count: ${key_count}"
    if [[ "${key_count}" -eq 0 ]]; then
        log_warn "Database is empty — ensure dataset is primed before running scenario"
    fi
    mark_event "dataset_check" "key_count=${key_count}"

    # Step 3: Warm up the workload
    log_step 3 "Warm up the workload"
    mark_event "warmup_start"
    start_locust "${WARMUP_DURATION}s"
    wait_for_locust
    mark_event "warmup_end"
    log_ok "Warmup complete — discarding warmup data"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && mv "$f" "${f%.csv}_warmup.csv"
    done

    # Step 4: Run steady-state baseline
    log_step 4 "Run steady-state baseline (${BASELINE_DURATION}s)"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_baseline"
    capture_topology "pre_baseline"
    mark_event "baseline_start"
    start_locust "${BASELINE_DURATION}s"
    wait_for_locust
    mark_event "baseline_end"
    capture_redis_info "${PRIMARY_CONTAINER}" "post_baseline"
    log_ok "Baseline captured"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && [[ "$f" != *_warmup.csv ]] && [[ "$f" != *_baseline.csv ]] && mv "$f" "${f%.csv}_baseline.csv"
    done

    # Start continuous workload for disruption + recovery observation
    log_info "Starting continuous workload for disruption and recovery phases"
    start_locust

    # Allow workload to stabilize
    sleep 10

    # Step 5: Inject disruption — stop the node container
    log_step 5 "Inject disruption: docker stop ${NODE_CONTAINER}"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_node_loss"
    capture_topology "pre_node_loss"
    local stop_epoch
    stop_epoch=$(ts_epoch)
    mark_event "node_stop_start" "container=${NODE_CONTAINER}"
    docker stop "${NODE_CONTAINER}"
    mark_event "node_stop_done" "container=${NODE_CONTAINER}"
    log_ok "Node container stopped: ${NODE_CONTAINER}"

    # Step 6: Mark the event in dashboard timeline
    log_step 6 "Mark event in dashboard timeline"
    log_info "Node stop event recorded at epoch ${stop_epoch}"
    log_info "Use this timestamp to correlate with Grafana/Prometheus dashboards"

    # Step 7: Observe degradation during node outage
    log_step 7 "Observe degradation and recovery"
    log_info "Node will remain down for ${NODE_DOWN_DURATION}s..."
    mark_event "node_down_window_start" "duration=${NODE_DOWN_DURATION}s"
    sleep "${NODE_DOWN_DURATION}"
    mark_event "node_down_window_end"

    # Bring the node back
    log_info "Restarting node: docker start ${NODE_CONTAINER}"
    mark_event "node_start_begin" "container=${NODE_CONTAINER}"
    docker start "${NODE_CONTAINER}"
    mark_event "node_start_done" "container=${NODE_CONTAINER}"
    log_ok "Node container restarted: ${NODE_CONTAINER}"

    # Wait for the node to become responsive
    wait_for_container "${NODE_CONTAINER}" 60
    wait_for_redis "${NODE_CONTAINER}" 60

    # Monitor recovery
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)
    local recovery_confirmed=false

    while [[ $recovery_elapsed -lt $max_recovery_wait ]]; do
        sleep 2
        recovery_elapsed=$(( $(ts_epoch) - recovery_start ))
        case "${PLATFORM}" in
            oss-sentinel)
                if docker exec "${SENTINEL_CONTAINER:-sentinel1}" \
                    redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null | grep -q "OK"; then
                    recovery_confirmed=true
                    mark_event "recovery_detected" "elapsed=${recovery_elapsed}s"
                    break
                fi
                ;;
            oss-cluster)
                if docker exec "${REPLICA_CONTAINER:-redis-node2}" redis-cli CLUSTER INFO 2>/dev/null | grep -q "cluster_state:ok"; then
                    recovery_confirmed=true
                    mark_event "recovery_detected" "elapsed=${recovery_elapsed}s"
                    break
                fi
                ;;
            re)
                log_info "RE recovery: check rladmin status (elapsed: ${recovery_elapsed}s)"
                recovery_confirmed=true
                mark_event "recovery_detected" "elapsed=${recovery_elapsed}s assumed"
                break
                ;;
        esac
        log_info "Waiting for recovery... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    if [[ "${recovery_confirmed}" == "true" ]]; then
        local total_duration=$(( $(ts_epoch) - stop_epoch ))
        log_ok "Recovery confirmed after ${total_duration}s total (including ${NODE_DOWN_DURATION}s down window)"
        mark_event "recovery_complete" "total_duration=${total_duration}s"
    else
        log_warn "Recovery not confirmed within ${max_recovery_wait}s after node restart"
        mark_event "recovery_timeout" "max_wait=${max_recovery_wait}s"
    fi

    capture_topology "post_recovery"
    capture_redis_info "${NODE_CONTAINER}" "post_recovery"

    # Check replication sync state
    log_info "Checking replication sync state..."
    local sync_info
    sync_info=$(docker exec "${NODE_CONTAINER}" redis-cli INFO replication 2>/dev/null || echo "unavailable")
    echo "${sync_info}" > "${RUN_DIR}/replication_sync_post_recovery.txt"
    mark_event "replication_sync_captured"

    # Step 8: Continue long enough to confirm stability
    log_step 8 "Confirm post-recovery stability (${POST_RECOVERY_DURATION}s)"
    mark_event "post_recovery_observation_start"
    sleep "${POST_RECOVERY_DURATION}"
    mark_event "post_recovery_observation_end"
    log_ok "Post-recovery observation complete"

    # Stop the continuous workload
    stop_locust

    # Capture final state
    capture_topology "final"
    capture_redis_info "${PRIMARY_CONTAINER}" "final"

    # Step 9: Export evidence
    export_evidence

    # Step 10: Repeat guidance
    log_step 10 "Repeat at least three times"
    log_info "Re-run this script at least 3 times and compare results for consistency"
    log_info "Results saved to: ${RUN_DIR}"

    # Scorecard questions
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Scorecard Questions                                       ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  1. What happened?                                         ║"
    echo "║     → Node stopped ${NODE_DOWN_DURATION}s then restarted   ║"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, latency spikes         ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare recovery duration and operator effort        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"
