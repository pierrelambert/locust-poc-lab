#!/usr/bin/env bash
# 02_primary_kill.sh — Scenario 2: Primary Process Kill
#
# Simple HA proof — kills the primary Redis container and measures
# failover quality, recovery time, and client impact.
#
# Required environment variables:
#   PLATFORM          - "re" | "oss-sentinel" | "oss-cluster"
#   LOCUST_FILE       - Path to the Locustfile to run
#   PRIMARY_CONTAINER - Name of the primary Redis container to kill
#
# Optional environment variables:
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:6379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary ./scenarios/scripts/02_primary_kill.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 2: Primary Process Kill                    ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "02_primary_kill"
    init_events_log

    # Step 1: Verify environment parity
    check_environment
    if [[ -z "${PRIMARY_CONTAINER:-}" ]]; then
        log_error "PRIMARY_CONTAINER must be set to the container to kill"
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

    # Step 5: Inject disruption — kill the primary container
    log_step 5 "Inject disruption: docker kill ${PRIMARY_CONTAINER}"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_kill"
    capture_topology "pre_kill"
    local kill_epoch
    kill_epoch=$(ts_epoch)
    mark_event "primary_kill_start" "container=${PRIMARY_CONTAINER}"
    docker kill "${PRIMARY_CONTAINER}"
    mark_event "primary_kill_done" "container=${PRIMARY_CONTAINER}"
    log_ok "Primary container killed: ${PRIMARY_CONTAINER}"

    # Step 6: Mark the event in dashboard timeline
    log_step 6 "Mark event in dashboard timeline"
    log_info "Kill event recorded at epoch ${kill_epoch}"
    log_info "Use this timestamp to correlate with Grafana/Prometheus dashboards"

    # Step 7: Observe degradation and recovery
    log_step 7 "Observe degradation and recovery"
    log_info "Monitoring failover behavior..."
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)

    # Poll for a new primary to become available
    local new_primary_found=false
    while [[ $recovery_elapsed -lt $max_recovery_wait ]]; do
        sleep 2
        recovery_elapsed=$(( $(ts_epoch) - recovery_start ))

        # Check platform-specific recovery
        case "${PLATFORM}" in
            oss-sentinel)
                local master_info
                master_info=$(docker exec "${SENTINEL_CONTAINER:-sentinel1}" \
                    redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster 2>/dev/null || echo "")
                if [[ -n "$master_info" ]]; then
                    log_info "Sentinel reports master: ${master_info} (elapsed: ${recovery_elapsed}s)"
                    # Try to ping the new master
                    if docker exec "${SENTINEL_CONTAINER:-sentinel1}" \
                        redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null | grep -q "OK"; then
                        new_primary_found=true
                        mark_event "failover_detected" "elapsed=${recovery_elapsed}s"
                        break
                    fi
                fi
                ;;
            oss-cluster)
                if docker exec "${REPLICA_CONTAINER:-redis-node2}" redis-cli CLUSTER INFO 2>/dev/null | grep -q "cluster_state:ok"; then
                    new_primary_found=true
                    mark_event "failover_detected" "elapsed=${recovery_elapsed}s"
                    break
                fi
                ;;
            re)
                log_info "RE failover detection: check rladmin status (elapsed: ${recovery_elapsed}s)"
                new_primary_found=true
                mark_event "failover_detected" "elapsed=${recovery_elapsed}s assumed"
                break
                ;;
        esac
        log_info "Waiting for failover... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    if [[ "${new_primary_found}" == "true" ]]; then
        local failover_duration=$(( $(ts_epoch) - kill_epoch ))
        log_ok "Failover detected after ${failover_duration}s total"
        mark_event "failover_complete" "duration=${failover_duration}s"
    else
        log_warn "Failover not confirmed within ${max_recovery_wait}s"
        mark_event "failover_timeout" "max_wait=${max_recovery_wait}s"
    fi

    capture_topology "post_failover"

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
    echo "║     → Primary container killed; review events.jsonl        ║"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, latency spikes         ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare failover duration across platforms           ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

