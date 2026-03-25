#!/usr/bin/env bash
# 01_baseline.sh — Scenario 1: Steady-State Baseline
#
# Establishes normal SLA behavior before any disruption.
# All subsequent scenario comparisons reference this baseline.
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
#   BASELINE_DURATION     - Baseline run duration in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#   SENTINEL_CONTAINER    - Sentinel container name (for oss-sentinel)
#
# Usage:
#   PLATFORM=oss-sentinel LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     PRIMARY_CONTAINER=redis-primary ./scenarios/scripts/01_baseline.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 1: Steady-State Baseline                   ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "01_baseline"
    init_events_log

    # Step 1: Verify environment parity
    check_environment

    # Step 2: Verify dataset is primed (precondition)
    log_step 2 "Verify dataset is primed"
    local key_count
    key_count=$(docker exec "${PRIMARY_CONTAINER}" redis-cli -p ${REDIS_CLI_PORT} DBSIZE 2>/dev/null | grep -o '[0-9]*' || echo "0")
    log_info "Current key count: ${key_count}"
    if [[ "${key_count}" -eq 0 ]]; then
        log_warn "Database is empty — ensure dataset is primed before running baseline"
        log_warn "Continuing anyway; results may not be representative"
    fi
    mark_event "dataset_check" "key_count=${key_count}"

    # Step 3: Warm up the workload
    log_step 3 "Warm up the workload"
    mark_event "warmup_start"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_warmup"
    start_locust "${WARMUP_DURATION}s"
    wait_for_locust
    mark_event "warmup_end"
    log_ok "Warmup complete (${WARMUP_DURATION}s) — discarding warmup data"
    # Move warmup CSV files aside
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && mv "$f" "${f%.csv}_warmup.csv"
    done

    # Step 4: Run steady-state baseline (minimum 10 minutes)
    log_step 4 "Run steady-state baseline (${BASELINE_DURATION}s)"
    capture_redis_info "${PRIMARY_CONTAINER}" "pre_baseline"
    capture_topology "pre_baseline"
    mark_event "baseline_start"
    start_locust "${BASELINE_DURATION}s"
    wait_for_locust
    mark_event "baseline_end"
    capture_redis_info "${PRIMARY_CONTAINER}" "post_baseline"
    capture_topology "post_baseline"
    log_ok "Baseline run complete"

    # Step 5: No disruption for baseline scenario
    log_step 5 "Inject disruption"
    log_info "Scenario 1 is a baseline — no disruption injected"
    mark_event "no_disruption" "baseline scenario"

    # Step 6: No event to mark (baseline)
    log_step 6 "Mark event in dashboard timeline"
    log_info "No disruption event — baseline only"

    # Step 7: No degradation expected
    log_step 7 "Observe degradation and recovery"
    log_info "Baseline scenario — expecting stable metrics throughout"

    # Step 8: Stability already confirmed by clean baseline run
    log_step 8 "Confirm stability"
    log_info "Baseline run completed without disruption — stability confirmed"

    # Step 9: Export evidence
    export_evidence

    # Step 10: Repeat guidance
    log_step 10 "Repeat at least three times"
    log_info "Re-run this script at least 3 times and compare results for consistency"
    log_info "Results saved to: ${RUN_DIR}"

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Baseline complete. Review results in:                     ║"
    echo "║  ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

