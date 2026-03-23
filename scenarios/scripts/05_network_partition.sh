#!/usr/bin/env bash
# 05_network_partition.sh — Scenario 5: Network Partition
#
# Hard resiliency proof — tests split-brain behavior, write safety, and
# diagnostic clarity under the most challenging failure mode.
#
# Required environment variables:
#   PLATFORM          - "re" | "oss-sentinel" | "oss-cluster"
#   LOCUST_FILE       - Path to the Locustfile to run
#   PRIMARY_CONTAINER - Name of the primary Redis container
#   PARTITION_TARGET  - Container to isolate via network partition
#
# Optional environment variables:
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:6379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   PARTITION_DURATION    - How long the partition lasts in seconds (default: 60)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#   REPLICA_CONTAINER     - Replica container name (for oss-cluster fallback)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary PARTITION_TARGET=redis-primary \
#     ./scenarios/scripts/05_network_partition.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

PARTITION_DURATION="${PARTITION_DURATION:-60}"

# ── Network partition helpers ─────────────────────────────────────────────────

inject_partition() {
    local container="$1"
    log_info "Injecting network partition on ${container}..."
    # Disconnect the container from its Docker network(s)
    local networks
    networks=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "${container}" | xargs)
    echo "${networks}" > "${RUN_DIR}/partitioned_networks.txt"
    for net in ${networks}; do
        docker network disconnect "${net}" "${container}" 2>/dev/null || true
        log_info "Disconnected ${container} from network: ${net}"
    done
    mark_event "partition_injected" "container=${container} networks=${networks}"
}

heal_partition() {
    local container="$1"
    log_info "Healing network partition on ${container}..."
    local networks
    networks=$(cat "${RUN_DIR}/partitioned_networks.txt" 2>/dev/null || echo "")
    for net in ${networks}; do
        docker network connect "${net}" "${container}" 2>/dev/null || true
        log_info "Reconnected ${container} to network: ${net}"
    done
    mark_event "partition_healed" "container=${container} networks=${networks}"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 5: Network Partition                       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "05_network_partition"
    init_events_log

    # Step 1: Verify environment parity
    check_environment
    if [[ -z "${PARTITION_TARGET:-}" ]]; then
        log_error "PARTITION_TARGET must be set to the container to isolate"
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

    # Start continuous workload for partition observation
    log_info "Starting continuous workload for partition phase"
    start_locust

    # Allow workload to stabilize
    sleep 10

    # Capture pre-partition write count for data consistency check
    local pre_partition_writes
    pre_partition_writes=$(docker exec "${PRIMARY_CONTAINER}" redis-cli INFO stats 2>/dev/null \
        | grep total_commands_processed | tr -d '\r' | cut -d: -f2 || echo "0")
    mark_event "pre_partition_write_count" "total_commands=${pre_partition_writes}"

    # Step 5: Inject disruption — network partition
    log_step 5 "Inject disruption: network partition on ${PARTITION_TARGET}"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_partition"
    capture_topology "pre_partition"
    local partition_epoch
    partition_epoch=$(ts_epoch)
    inject_partition "${PARTITION_TARGET}"
    log_ok "Network partition active on ${PARTITION_TARGET}"

    # Step 6: Mark the event in dashboard timeline
    log_step 6 "Mark event in dashboard timeline"
    log_info "Partition event recorded at epoch ${partition_epoch}"
    log_info "Use this timestamp to correlate with Grafana/Prometheus dashboards"

    # Step 7: Observe degradation during partition
    log_step 7 "Observe degradation and recovery"
    log_info "Partition will remain active for ${PARTITION_DURATION}s..."
    mark_event "partition_window_start" "duration=${PARTITION_DURATION}s"

    # Monitor split behavior during partition
    local monitor_interval=5 elapsed=0
    while [[ $elapsed -lt $PARTITION_DURATION ]]; do
        sleep "${monitor_interval}"
        elapsed=$((elapsed + monitor_interval))
        case "${PLATFORM}" in
            oss-sentinel)
                local sentinel_master
                sentinel_master=$(docker exec "${SENTINEL_CONTAINER:-sentinel1}" \
                    redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster 2>/dev/null || echo "unknown")
                mark_event "partition_monitor" "elapsed=${elapsed}s sentinel_master=${sentinel_master}"
                ;;
            oss-cluster)
                local cluster_state
                cluster_state=$(docker exec "${REPLICA_CONTAINER:-redis-node2}" \
                    redis-cli CLUSTER INFO 2>/dev/null | grep cluster_state | tr -d '\r' || echo "unknown")
                mark_event "partition_monitor" "elapsed=${elapsed}s ${cluster_state}"
                ;;
            re)
                local re_health
                re_health=$(_re_api GET "/v1/shards" 2>/dev/null | python3 -c "
import sys, json
try:
    shards = json.load(sys.stdin)
    active = sum(1 for s in shards if s.get('status') == 'active')
    masters = sum(1 for s in shards if s.get('role') == 'master' and s.get('status') == 'active')
    print(f'active_shards={active} masters={masters}')
except: print('unavailable')
" 2>/dev/null || echo "unavailable")
                mark_event "partition_monitor" "elapsed=${elapsed}s ${re_health}"
                ;;
        esac
        log_info "Partition active: ${elapsed}s / ${PARTITION_DURATION}s"
    done
    mark_event "partition_window_end"

    # Heal the partition
    log_info "Healing network partition..."
    heal_partition "${PARTITION_TARGET}"
    local heal_epoch
    heal_epoch=$(ts_epoch)
    log_ok "Network partition healed"

    # Wait for the partitioned node to become responsive
    wait_for_container "${PARTITION_TARGET}" 60
    wait_for_redis "${PARTITION_TARGET}" 60

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
                if wait_for_re_recovery "${max_recovery_wait}"; then
                    recovery_confirmed=true
                fi
                break
                ;;
        esac
        log_info "Waiting for recovery... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    local total_duration=$(( $(ts_epoch) - partition_epoch ))
    if [[ "${recovery_confirmed}" == "true" ]]; then
        log_ok "Recovery confirmed after ${total_duration}s total (partition: ${PARTITION_DURATION}s)"
        mark_event "recovery_complete" "total_duration=${total_duration}s"
    else
        log_warn "Recovery not confirmed within ${max_recovery_wait}s after partition heal"
        mark_event "recovery_timeout" "max_wait=${max_recovery_wait}s"
    fi

    capture_topology "post_recovery"
    capture_redis_info "${PRIMARY_CONTAINER}" "post_recovery"
    capture_redis_info "${PARTITION_TARGET}" "post_recovery_target"

    # Data consistency check
    log_info "Checking data consistency post-partition..."
    local post_partition_writes
    post_partition_writes=$(docker exec "${PRIMARY_CONTAINER}" redis-cli INFO stats 2>/dev/null \
        | grep total_commands_processed | tr -d '\r' | cut -d: -f2 || echo "0")
    mark_event "post_partition_write_count" "total_commands=${post_partition_writes}"

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
    echo "║     → Network partition for ${PARTITION_DURATION}s on ${PARTITION_TARGET}"
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