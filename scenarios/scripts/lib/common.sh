#!/usr/bin/env bash
# common.sh — Shared helpers for scenario scripts
# Source this file: source "$(dirname "$0")/lib/common.sh"
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
RESULTS_DIR="${RESULTS_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")/results}"
BASELINE_DURATION="${BASELINE_DURATION:-600}"
WARMUP_DURATION="${WARMUP_DURATION:-60}"
POST_RECOVERY_DURATION="${POST_RECOVERY_DURATION:-300}"
LOCUST_USERS="${LOCUST_USERS:-10}"
LOCUST_SPAWN_RATE="${LOCUST_SPAWN_RATE:-2}"
LOCUST_HOST="${LOCUST_HOST:-redis://localhost:6379}"
LOCUST_FILE="${LOCUST_FILE:-}"
WORKLOAD_PROFILE="${WORKLOAD_PROFILE:-}"
PLATFORM="${PLATFORM:-}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $(date '+%Y-%m-%dT%H:%M:%S%z') $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $(date '+%Y-%m-%dT%H:%M:%S%z') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%Y-%m-%dT%H:%M:%S%z') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%dT%H:%M:%S%z') $*"; }
log_step()  { echo -e "\n${CYAN}━━━ Step $1: $2 ━━━${NC}"; }
ts_now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
ts_epoch() { date '+%s'; }

setup_run_dir() {
    local scenario_name="$1"
    local run_id="${scenario_name}_${PLATFORM}_$(date '+%Y%m%d_%H%M%S')"
    RUN_DIR="${RESULTS_DIR}/${run_id}"
    mkdir -p "${RUN_DIR}"
    export RUN_DIR RUN_ID="${run_id}"
    log_info "Run directory: ${RUN_DIR}"
}

check_environment() {
    log_step 1 "Verify environment parity"
    [[ -z "${PLATFORM}" ]] && { log_error "PLATFORM must be set (re | oss-sentinel | oss-cluster)"; exit 1; }
    [[ -z "${LOCUST_FILE}" ]] && { log_error "LOCUST_FILE must be set to a Locustfile path"; exit 1; }
    [[ ! -f "${LOCUST_FILE}" ]] && { log_error "Locustfile not found: ${LOCUST_FILE}"; exit 1; }
    local env_file="${RUN_DIR}/environment.json"
    cat > "${env_file}" <<ENVEOF
{
  "platform": "${PLATFORM}",
  "timestamp": "$(ts_now)",
  "locust_file": "${LOCUST_FILE}",
  "workload_profile": "${WORKLOAD_PROFILE}",
  "locust_users": ${LOCUST_USERS},
  "locust_spawn_rate": ${LOCUST_SPAWN_RATE},
  "locust_host": "${LOCUST_HOST}",
  "docker_compose_project": "${COMPOSE_PROJECT:-unknown}",
  "redis_version": "$(docker exec "${PRIMARY_CONTAINER:-redis-primary}" redis-cli INFO server 2>/dev/null | grep redis_version | tr -d '\r' || echo 'unavailable')"
}
ENVEOF
    log_ok "Environment metadata saved to ${env_file}"
}

container_is_running() {
    docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -q true
}

wait_for_container() {
    local name="$1" timeout="${2:-60}" elapsed=0
    log_info "Waiting for container ${name} (timeout: ${timeout}s)..."
    while ! container_is_running "$name"; do
        sleep 1; elapsed=$((elapsed + 1))
        [[ $elapsed -ge $timeout ]] && { log_error "Container ${name} did not start within ${timeout}s"; return 1; }
    done
    log_ok "Container ${name} is running"
}

wait_for_redis() {
    local container="$1" timeout="${2:-60}" elapsed=0
    log_info "Waiting for Redis PING on ${container} (timeout: ${timeout}s)..."
    while ! docker exec "$container" redis-cli PING 2>/dev/null | grep -q PONG; do
        sleep 1; elapsed=$((elapsed + 1))
        [[ $elapsed -ge $timeout ]] && { log_error "Redis on ${container} did not respond within ${timeout}s"; return 1; }
    done
    log_ok "Redis on ${container} is responding"
}

LOCUST_PID=""
start_locust() {
    local csv_prefix="${RUN_DIR}/locust" run_time="${1:-}"
    local extra_args=()
    [[ -n "${WORKLOAD_PROFILE}" ]] && extra_args+=(--config "${WORKLOAD_PROFILE}")
    [[ -n "${run_time}" ]] && extra_args+=(-t "${run_time}")
    log_info "Starting Locust: users=${LOCUST_USERS}, spawn_rate=${LOCUST_SPAWN_RATE}"
    locust -f "${LOCUST_FILE}" --headless --host "${LOCUST_HOST}" \
        -u "${LOCUST_USERS}" -r "${LOCUST_SPAWN_RATE}" \
        --csv "${csv_prefix}" --csv-full-history \
        "${extra_args[@]}" > "${RUN_DIR}/locust_stdout.log" 2>&1 &
    LOCUST_PID=$!
    log_ok "Locust started (PID: ${LOCUST_PID})"
}

stop_locust() {
    if [[ -n "${LOCUST_PID}" ]] && kill -0 "${LOCUST_PID}" 2>/dev/null; then
        log_info "Stopping Locust (PID: ${LOCUST_PID})..."
        kill "${LOCUST_PID}" 2>/dev/null || true
        wait "${LOCUST_PID}" 2>/dev/null || true
        log_ok "Locust stopped"
    fi
    LOCUST_PID=""
}

wait_for_locust() {
    if [[ -n "${LOCUST_PID}" ]]; then
        log_info "Waiting for Locust to finish..."
        wait "${LOCUST_PID}" 2>/dev/null || true
        log_ok "Locust run complete"; LOCUST_PID=""
    fi
}

EVENTS_FILE=""
init_events_log() { EVENTS_FILE="${RUN_DIR}/events.jsonl"; touch "${EVENTS_FILE}"; }
mark_event() {
    local event_name="$1" detail="${2:-}"
    echo "{\"timestamp\":\"$(ts_now)\",\"epoch\":$(ts_epoch),\"event\":\"${event_name}\",\"detail\":\"${detail}\"}" >> "${EVENTS_FILE}"
    log_info "Event marked: ${event_name} ${detail}"
}

capture_redis_info() {
    local container="$1" label="${2:-snapshot}"
    local outfile="${RUN_DIR}/redis_info_${label}_$(date '+%H%M%S').txt"
    docker exec "$container" redis-cli INFO ALL > "${outfile}" 2>/dev/null || true
    log_info "Redis INFO captured: ${outfile}"
}

capture_topology() {
    local label="${1:-snapshot}" outfile="${RUN_DIR}/topology_${label}.txt"
    case "${PLATFORM}" in
        oss-cluster)  docker exec "${PRIMARY_CONTAINER:-redis-node-1}" redis-cli CLUSTER NODES > "${outfile}" 2>/dev/null || true ;;
        oss-sentinel) docker exec "${SENTINEL_CONTAINER:-sentinel-1}" redis-cli -p 26379 SENTINEL masters > "${outfile}" 2>/dev/null || true ;;
        re)           echo "RE topology capture: use rladmin status" >> "${outfile}" ;;
    esac
    log_info "Topology captured: ${outfile}"
}

export_evidence() {
    log_step 9 "Export evidence and record operator actions"
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
    local exporter="${repo_root}/observability/exporters/run_summary_exporter.py"
    if [[ -f "${exporter}" ]]; then
        log_info "Running evidence exporter..."
        python3 "${exporter}" "${RUN_DIR}" || log_warn "Evidence exporter failed — falling back to basic summary"
    else
        log_warn "Evidence exporter not found at ${exporter} — writing basic summary"
        local summary="${RUN_DIR}/run_summary.json"
        cat > "${summary}" <<SUMEOF
{
  "run_id": "${RUN_ID}",
  "platform": "${PLATFORM}",
  "completed_at": "$(ts_now)",
  "results_dir": "${RUN_DIR}",
  "files": $(ls -1 "${RUN_DIR}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip().split('\n')))" 2>/dev/null || echo '[]')
}
SUMEOF
    fi
    log_ok "Evidence exported to ${RUN_DIR}"
}

cleanup() { stop_locust; log_info "Cleanup complete"; }
trap cleanup EXIT

