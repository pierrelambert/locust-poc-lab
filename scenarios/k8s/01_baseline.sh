#!/usr/bin/env bash
# 01_baseline.sh — Scenario 1: Steady-State Baseline (Kubernetes)
#
# Establishes normal SLA behavior on k8s before any disruption.
# Uses port-forward to reach Redis running in the cluster.
#
# Required environment variables:
#   LOCUST_FILE       - Path to the Locustfile to run
#
# Optional environment variables:
#   K8S_NAMESPACE         - Kubernetes namespace (default: redis-oss)
#   K8S_LOCAL_REDIS_PORT  - Local port for Redis port-forward (default: 16379)
#   LOCUST_USERS          - Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE     - User spawn rate (default: 2)
#   LOCUST_HOST           - Redis host URL (default: redis://localhost:16379)
#   WORKLOAD_PROFILE      - Path to workload profile YAML
#   BASELINE_DURATION     - Baseline run duration in seconds (default: 600)
#   WARMUP_DURATION       - Warmup duration in seconds (default: 60)
#
# Usage:
#   LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
#     ./scenarios/k8s/01_baseline.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/k8s_helpers.sh"

# Override PLATFORM for evidence compatibility
PLATFORM="k8s-oss"

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║        Scenario 1: Steady-State Baseline (k8s)             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"

    setup_run_dir "01_baseline"
    init_events_log

    # Step 1: Verify k8s environment
    k8s_check_environment

    # Start port-forward to Redis
    start_port_forward "${K8S_REDIS_SERVICE}" "${K8S_LOCAL_REDIS_PORT}" "${K8S_REDIS_PORT}" "redis"
    wait_for_k8s_redis "${K8S_LOCAL_REDIS_PORT}"

    # Step 2: Verify dataset is primed
    k8s_check_dataset "${K8S_LOCAL_REDIS_PORT}"

    # Step 3: Warm up the workload
    log_step 3 "Warm up the workload"
    k8s_mark_event "warmup_start"
    k8s_capture_redis_info "redis-0" "pre_warmup"
    start_locust "${WARMUP_DURATION}s"
    wait_for_locust
    k8s_mark_event "warmup_end"
    log_ok "Warmup complete (${WARMUP_DURATION}s) — discarding warmup data"
    for f in "${RUN_DIR}"/locust_*.csv; do
        [[ -f "$f" ]] && mv "$f" "${f%.csv}_warmup.csv"
    done

    # Step 4: Run steady-state baseline
    log_step 4 "Run steady-state baseline (${BASELINE_DURATION}s)"
    k8s_capture_redis_info "redis-0" "pre_baseline"
    k8s_capture_topology "pre_baseline"
    k8s_mark_event "baseline_start"
    start_locust "${BASELINE_DURATION}s"
    wait_for_locust
    k8s_mark_event "baseline_end"
    k8s_capture_redis_info "redis-0" "post_baseline"
    k8s_capture_topology "post_baseline"
    log_ok "Baseline run complete"

    # Step 5–8: No disruption for baseline
    log_step 5 "Inject disruption"
    log_info "Scenario 1 is a baseline — no disruption injected"
    k8s_mark_event "no_disruption" "baseline scenario"

    log_step 6 "Mark event in dashboard timeline"
    log_info "No disruption event — baseline only"

    log_step 7 "Observe degradation and recovery"
    log_info "Baseline scenario — expecting stable metrics throughout"

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
    echo "║  Baseline complete (k8s). Review results in:               ║"
    echo "║  ${RUN_DIR}"
    echo "╚══════════════════════════════════════════════════════════════╝"
}

main "$@"

