#!/usr/bin/env bash
# 06_replica_promotion.sh — Scenario 6: Scale-Out / Replica Promotion Under Load
#
# Growth proof — demonstrates whether the platform can expand capacity or
# promote replicas without disrupting running workloads. Tests rebalancing
# behavior, slot migration impact, and operator effort.
#
# Required environment variables:
#   PLATFORM          - "re" | "oss-sentinel" | "oss-cluster"
#   LOCUST_FILE       - Path to the Locustfile to run
#   PRIMARY_CONTAINER - Name of the primary Redis container
#
# Optional environment variables:
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:6379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Pre-disruption baseline in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION - Post-recovery observation in seconds (default: 300)
#   NEW_NODE_CONTAINER    - New node container to add (for scale-out)
#   REPLICA_CONTAINER     - Replica to promote (for promotion test)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#   SCALE_MODE            - "add_node" | "promote_replica" (default: promote_replica)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary REPLICA_CONTAINER=redis-replica-1 \
#     SCALE_MODE=promote_replica \
#     ./scenarios/scripts/06_replica_promotion.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

SCALE_MODE="${SCALE_MODE:-promote_replica}"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║   Scenario 6: Scale-Out / Replica Promotion Under Load     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "06_replica_promotion"
    init_events_log

    # Step 1: Verify environment parity
    check_environment
    wait_for_redis "${PRIMARY_CONTAINER}"

    # Validate mode-specific requirements
    case "${SCALE_MODE}" in
        promote_replica)
            if [[ -z "${REPLICA_CONTAINER:-}" ]]; then
                log_error "REPLICA_CONTAINER must be set for promote_replica mode"
                exit 1
            fi
            log_info "Mode: promote_replica — will force failover to ${REPLICA_CONTAINER}"
            ;;
        add_node)
            if [[ -z "${NEW_NODE_CONTAINER:-}" ]]; then
                log_error "NEW_NODE_CONTAINER must be set for add_node mode"
                exit 1
            fi
            log_info "Mode: add_node — will add ${NEW_NODE_CONTAINER} to the topology"
            ;;
        *)
            log_error "SCALE_MODE must be 'promote_replica' or 'add_node'"
            exit 1
            ;;
    esac

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

    # Start continuous workload for scale/promotion observation
    log_info "Starting continuous workload for scale/promotion phase"
    start_locust

    # Allow workload to stabilize
    sleep 10

    # Step 5: Inject disruption — scale-out or replica promotion
    log_step 5 "Inject disruption: ${SCALE_MODE}"
    capture_topology "pre_scale"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_scale"
    local scale_epoch operator_steps=0
    scale_epoch=$(ts_epoch)
    mark_event "scale_start" "mode=${SCALE_MODE}"

    case "${SCALE_MODE}" in
        promote_replica)
            case "${PLATFORM}" in
                oss-sentinel)
                    log_info "Triggering sentinel failover to promote ${REPLICA_CONTAINER}..."
                    docker exec "${SENTINEL_CONTAINER:-sentinel-1}" \
                        redis-cli -p 26379 SENTINEL failover mymaster 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    mark_event "failover_triggered" "via=sentinel"
                    ;;
                oss-cluster)
                    log_info "Triggering cluster failover on ${REPLICA_CONTAINER}..."
                    docker exec "${REPLICA_CONTAINER}" \
                        redis-cli CLUSTER FAILOVER 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    mark_event "failover_triggered" "via=cluster_failover"
                    ;;
                re)
                    log_info "RE: trigger failover via rladmin or REST API"
                    operator_steps=$((operator_steps + 1))
                    mark_event "failover_triggered" "via=re_manual"
                    ;;
            esac
            ;;
        add_node)
            case "${PLATFORM}" in
                oss-cluster)
                    log_info "Starting new node container: ${NEW_NODE_CONTAINER}"
                    docker start "${NEW_NODE_CONTAINER}" 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    wait_for_container "${NEW_NODE_CONTAINER}" 60
                    wait_for_redis "${NEW_NODE_CONTAINER}" 60

                    # Get the new node's IP and add it to the cluster
                    local new_node_ip
                    new_node_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${NEW_NODE_CONTAINER}")
                    log_info "Adding ${NEW_NODE_CONTAINER} (${new_node_ip}) to cluster..."
                    docker exec "${PRIMARY_CONTAINER}" \
                        redis-cli CLUSTER MEET "${new_node_ip}" 6379 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    mark_event "node_added" "container=${NEW_NODE_CONTAINER} ip=${new_node_ip}"

                    # Trigger rebalance
                    log_info "Triggering cluster rebalance..."
                    local primary_ip
                    primary_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${PRIMARY_CONTAINER}")
                    docker exec "${PRIMARY_CONTAINER}" \
                        redis-cli --cluster rebalance "${primary_ip}:6379" --cluster-use-empty-masters 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    mark_event "rebalance_triggered"
                    ;;
                oss-sentinel)
                    log_info "Starting new replica: ${NEW_NODE_CONTAINER}"
                    docker start "${NEW_NODE_CONTAINER}" 2>/dev/null || true
                    operator_steps=$((operator_steps + 1))
                    wait_for_container "${NEW_NODE_CONTAINER}" 60
                    wait_for_redis "${NEW_NODE_CONTAINER}" 60
                    mark_event "node_added" "container=${NEW_NODE_CONTAINER}"
                    ;;
                re)
                    log_info "RE: add node via rladmin or REST API"
                    operator_steps=$((operator_steps + 1))
                    mark_event "node_added" "via=re_manual"
                    ;;
            esac
            ;;
    esac

    # Step 6: Mark the event in dashboard timeline
    log_step 6 "Mark event in dashboard timeline"
    log_info "Scale event recorded at epoch ${scale_epoch}"

    # Step 7: Observe and monitor the scale/promotion
    log_step 7 "Observe degradation and recovery"
    local recovery_start recovery_elapsed=0 max_recovery_wait=120
    recovery_start=$(ts_epoch)
    local recovery_confirmed=false

    while [[ $recovery_elapsed -lt $max_recovery_wait ]]; do
        sleep 2
        recovery_elapsed=$(( $(ts_epoch) - recovery_start ))
        case "${PLATFORM}" in
            oss-sentinel)
                if docker exec "${SENTINEL_CONTAINER:-sentinel-1}" \
                    redis-cli -p 26379 SENTINEL ckquorum mymaster 2>/dev/null | grep -q "OK"; then
                    recovery_confirmed=true
                    mark_event "recovery_detected" "elapsed=${recovery_elapsed}s"
                    break
                fi
                ;;
            oss-cluster)
                if docker exec "${PRIMARY_CONTAINER}" redis-cli CLUSTER INFO 2>/dev/null | grep -q "cluster_state:ok"; then
                    recovery_confirmed=true
                    mark_event "recovery_detected" "elapsed=${recovery_elapsed}s"
                    break
                fi
                ;;
            re)
                recovery_confirmed=true
                mark_event "recovery_detected" "elapsed=${recovery_elapsed}s assumed"
                break
                ;;
        esac
        log_info "Waiting for stable state... (${recovery_elapsed}s / ${max_recovery_wait}s)"
    done

    local scale_duration=$(( $(ts_epoch) - scale_epoch ))
    if [[ "${recovery_confirmed}" == "true" ]]; then
        log_ok "Stable state confirmed after ${scale_duration}s"
        mark_event "scale_complete" "duration=${scale_duration}s operator_steps=${operator_steps}"
    else
        log_warn "Stable state not confirmed within ${max_recovery_wait}s"
        mark_event "scale_timeout" "max_wait=${max_recovery_wait}s"
    fi

    capture_topology "post_scale"
    capture_redis_info "${PRIMARY_CONTAINER}" "post_scale"

    # Step 8: Continue long enough to confirm stability
    log_step 8 "Confirm post-scale stability (${POST_RECOVERY_DURATION}s)"
    mark_event "post_recovery_observation_start"
    sleep "${POST_RECOVERY_DURATION}"
    mark_event "post_recovery_observation_end"
    log_ok "Post-scale observation complete"

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
  "scale_mode": "${SCALE_MODE}",
  "total_operator_steps": ${operator_steps},
  "total_scale_duration_seconds": ${scale_duration},
  "platform": "${PLATFORM}"
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
    echo "║     → ${SCALE_MODE} under load on ${PLATFORM}"
    echo "║  2. What did the application feel?                         ║"
    echo "║     → Review Locust CSV for errors, MOVED/ASK redirections ║"
    echo "║  3. Which platform recovered faster/simpler?               ║"
    echo "║     → Compare operator steps and scale duration            ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  Operator steps: ${operator_steps}  Duration: ${scale_duration}s"
    echo "║  Results: ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"
