#!/usr/bin/env bash
# 04_rolling_upgrade.sh — Scenario 4: Rolling Upgrade Under Load
#
# Day-2 operations proof — demonstrates whether maintenance can happen
# without service disruption by performing a sequential node restart
# under continuous workload.
#
# Required environment variables:
#   PLATFORM          - "re" | "oss-sentinel" | "oss-cluster"
#   LOCUST_FILE       - Path to the Locustfile to run
#   PRIMARY_CONTAINER - Name of the primary Redis container
#   NODE_CONTAINERS   - Space-separated list of containers to restart sequentially
#
# Optional environment variables:
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:6379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   NODE_RESTART_PAUSE    - Pause between node restarts in seconds (default: 15)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#   REPLICA_CONTAINER     - Replica container name (for oss-cluster fallback)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary \
#     NODE_CONTAINERS="redis-replica1 redis-replica2 redis-primary" \
#     ./scenarios/scripts/04_rolling_upgrade.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

NODE_RESTART_PAUSE="${NODE_RESTART_PAUSE:-15}"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 4: Rolling Upgrade Under Load              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "04_rolling_upgrade"
    init_events_log

    # Step 1: Verify environment parity
    check_environment
    if [[ -z "${NODE_CONTAINERS:-}" ]]; then
        log_error "NODE_CONTAINERS must be set to a space-separated list of containers to restart"
        exit 1
    fi
    # Convert to array
    local -a nodes
    read -ra nodes <<< "${NODE_CONTAINERS}"
    log_info "Rolling restart order: ${nodes[*]} (${#nodes[@]} nodes)"
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

    # Start continuous workload for rolling upgrade observation
    log_info "Starting continuous workload for rolling upgrade phase"
    start_locust

    # Allow workload to stabilize
    sleep 10

    # Step 5: Inject disruption — sequential node restart
    log_step 5 "Inject disruption: rolling restart of ${#nodes[@]} nodes"
    capture_topology "pre_rolling_upgrade"
    local upgrade_start_epoch node_index=0 operator_steps=0
    upgrade_start_epoch=$(ts_epoch)
    mark_event "rolling_upgrade_start" "nodes=${NODE_CONTAINERS}"

    for node in "${nodes[@]}"; do
        node_index=$((node_index + 1))
        log_info "── Node ${node_index}/${#nodes[@]}: ${node} ──"
        operator_steps=$((operator_steps + 1))

        # Capture pre-restart state for this node
        capture_redis_info "${node}" "pre_restart_node${node_index}" 2>/dev/null || true

        # Stop the node (simulates upgrade shutdown)
        local node_stop_epoch
        node_stop_epoch=$(ts_epoch)
        mark_event "node_restart_stop" "node=${node} index=${node_index}/${#nodes[@]}"
        docker stop "${node}"
        log_info "Node ${node} stopped"
        operator_steps=$((operator_steps + 1))

        # Brief pause to simulate upgrade binary swap
        sleep 3

        # Start the node (simulates upgraded node coming back)
        docker start "${node}"
        mark_event "node_restart_start" "node=${node} index=${node_index}/${#nodes[@]}"
        log_info "Node ${node} started"
        operator_steps=$((operator_steps + 1))

        # Wait for the node to become responsive
        wait_for_container "${node}" 60
        wait_for_redis "${node}" 60
        local node_restart_duration=$(( $(ts_epoch) - node_stop_epoch ))
        mark_event "node_restart_complete" "node=${node} duration=${node_restart_duration}s"
        log_ok "Node ${node} back online after ${node_restart_duration}s"

        # Health check between restarts
        operator_steps=$((operator_steps + 1))
        case "${PLATFORM}" in
            oss-sentinel)
                local quorum_ok
                quorum_ok=$(docker exec "${SENTINEL_CONTAINER:-sentinel1}" \
                    redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null || echo "FAIL")
                log_info "Sentinel quorum check: ${quorum_ok}"
                mark_event "health_check" "node=${node} quorum=${quorum_ok}"
                ;;
            oss-cluster)
                local cluster_state
                cluster_state=$(docker exec "${node}" redis-cli CLUSTER INFO 2>/dev/null | grep cluster_state | tr -d '\r' || echo "unknown")
                log_info "Cluster state: ${cluster_state}"
                mark_event "health_check" "node=${node} ${cluster_state}"
                ;;
            re)
                log_info "RE health check: verify via rladmin status"
                mark_event "health_check" "node=${node} re_check_manual"
                ;;
        esac

        # Pause between nodes (unless this is the last one)
        if [[ $node_index -lt ${#nodes[@]} ]]; then
            log_info "Pausing ${NODE_RESTART_PAUSE}s before next node..."
            sleep "${NODE_RESTART_PAUSE}"
        fi
    done

    local upgrade_duration=$(( $(ts_epoch) - upgrade_start_epoch ))
    mark_event "rolling_upgrade_complete" "total_duration=${upgrade_duration}s nodes=${#nodes[@]} operator_steps=${operator_steps}"
    log_ok "Rolling upgrade complete: ${#nodes[@]} nodes in ${upgrade_duration}s (${operator_steps} operator steps)"

    # Step 6: Mark the event in dashboard timeline
    log_step 6 "Mark event in dashboard timeline"
    log_info "Rolling upgrade window: epoch ${upgrade_start_epoch} to $(ts_epoch)"
    log_info "Use these timestamps to correlate with Grafana/Prometheus dashboards"

    # Step 7: Observe post-upgrade state
    log_step 7 "Observe degradation and recovery"
    capture_topology "post_rolling_upgrade"
    capture_redis_info "${PRIMARY_CONTAINER}" "post_rolling_upgrade"

    # Check replication sync state
    log_info "Checking replication sync state across nodes..."
    for node in "${nodes[@]}"; do
        local sync_info
        sync_info=$(docker exec "${node}" redis-cli INFO replication 2>/dev/null || echo "unavailable")
        echo "=== ${node} ===" >> "${RUN_DIR}/replication_sync_post_upgrade.txt"
        echo "${sync_info}" >> "${RUN_DIR}/replication_sync_post_upgrade.txt"
    done
    mark_event "replication_sync_captured"

    # Step 8: Continue long enough to confirm stability
    log_step 8 "Confirm post-upgrade stability (${POST_RECOVERY_DURATION}s)"
    mark_event "post_recovery_observation_start"
    sleep "${POST_RECOVERY_DURATION}"
    mark_event "post_recovery_observation_end"
    log_ok "Post-upgrade observation complete"

    # Stop the continuous workload
    stop_locust

    # Capture final state
    capture_topology "final"
    capture_redis_info "${PRIMARY_CONTAINER}" "final"

    # Step 9: Export evidence
    export_evidence

    # Write operator effort summary
    local effort_file="${RUN_DIR}/operator_effort.json"
    cat > "${effort_file}" <<EFFORTEOF
{
  "total_nodes_restarted": ${#nodes[@]},
  "total_operator_steps": ${operator_steps},
  "total_upgrade_duration_seconds": ${upgrade_duration},
  "node_restart_pause_seconds": ${NODE_RESTART_PAUSE},
  "platform": "${PLATFORM}",
  "node_order": "${NODE_CONTAINERS}"
}
EFFORTEOF
    log_ok "Operator effort summary saved to ${effort_file}"

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
    echo "║     → ${#nodes[@]} nodes restarted sequentially under load ║"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors per node restart        ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare operator steps and total upgrade duration    ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Operator steps: ${operator_steps}  Duration: ${upgrade_duration}s"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"
