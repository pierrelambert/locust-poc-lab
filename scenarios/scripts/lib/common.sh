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
LOCUST_HOST="${LOCUST_HOST:-redis://localhost:6380}"
REDIS_CLI_PORT="${REDIS_CLI_PORT:-6379}"
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
  "redis_version": "$(docker exec "${PRIMARY_CONTAINER:-redis-primary}" redis-cli -p ${REDIS_CLI_PORT} INFO server 2>/dev/null | grep redis_version | tr -d '\r' || echo 'unavailable')"
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
    while ! docker exec "$container" redis-cli -p ${REDIS_CLI_PORT} PING 2>/dev/null | grep -q PONG; do
        sleep 1; elapsed=$((elapsed + 1))
        [[ $elapsed -ge $timeout ]] && { log_error "Redis on ${container} did not respond within ${timeout}s"; return 1; }
    done
    log_ok "Redis on ${container} is responding"
}

LOCUST_PID=""
start_locust() {
    local csv_prefix="${RUN_DIR}/locust" run_time="${1:-}"
    local locust_bin
    if command -v locust &>/dev/null; then
        locust_bin="locust"
    else
        local repo_root
        repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
        if [[ -x "${repo_root}/.venv/bin/locust" ]]; then
            locust_bin="${repo_root}/.venv/bin/locust"
        else
            log_error "locust not found — install with: pip install locust"
            return 1
        fi
    fi
    local cmd=("${locust_bin}" -f "${LOCUST_FILE}" --headless --host "${LOCUST_HOST}"
        -u "${LOCUST_USERS}" -r "${LOCUST_SPAWN_RATE}"
        --csv "${csv_prefix}" --csv-full-history)
    [[ -n "${WORKLOAD_PROFILE}" ]] && cmd+=(--config "${WORKLOAD_PROFILE}")
    [[ -n "${run_time}" ]] && cmd+=(-t "${run_time}")
    log_info "Starting Locust: users=${LOCUST_USERS}, spawn_rate=${LOCUST_SPAWN_RATE}"
    "${cmd[@]}" > "${RUN_DIR}/locust_stdout.log" 2>&1 &
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

# ── Canary writer helpers ─────────────────────────────────────────────────────
CANARY_PID=""
CANARY_RATE="${CANARY_RATE:-10}"

start_canary() {
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
    local canary_script="${repo_root}/tooling/canary_writer.py"
    if [[ ! -f "${canary_script}" ]]; then
        log_warn "Canary writer not found at ${canary_script} — skipping"
        return 0
    fi
    local canary_args=(--output-dir "${RUN_DIR}" --rate "${CANARY_RATE}"
        --host "${CANARY_HOST:-localhost}" --port "${CANARY_PORT:-6380}"
        --connection-mode "${CANARY_MODE:-standalone}")
    [[ -n "${CANARY_PASSWORD:-}" ]] && canary_args+=(--password "${CANARY_PASSWORD}")
    [[ "${CANARY_SSL:-false}" == "true" ]] && canary_args+=(--ssl)
    local python_bin="python3"
    if [[ -x "${repo_root}/.venv/bin/python3" ]]; then
        python_bin="${repo_root}/.venv/bin/python3"
    fi
    log_info "Starting canary writer (rate=${CANARY_RATE} Hz)"
    PYTHONPATH="${repo_root}" "${python_bin}" "${canary_script}" "${canary_args[@]}" \
        > "${RUN_DIR}/canary_stdout.log" 2>&1 &
    CANARY_PID=$!
    log_ok "Canary writer started (PID: ${CANARY_PID})"
}

stop_canary() {
    if [[ -n "${CANARY_PID}" ]] && kill -0 "${CANARY_PID}" 2>/dev/null; then
        log_info "Stopping canary writer (PID: ${CANARY_PID})..."
        kill "${CANARY_PID}" 2>/dev/null || true
        wait "${CANARY_PID}" 2>/dev/null || true
        log_ok "Canary writer stopped"
    fi
    CANARY_PID=""

    # Run consistency check if canary log exists
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
    local canary_log="${RUN_DIR}/canary_writes.jsonl"
    if [[ -f "${canary_log}" ]]; then
        local python_bin="python3"
        if [[ -x "${repo_root}/.venv/bin/python3" ]]; then
            python_bin="${repo_root}/.venv/bin/python3"
        fi
        log_info "Running consistency checker..."
        PYTHONPATH="${repo_root}" "${python_bin}" -m tooling.consistency_checker \
            --host "${CANARY_HOST:-localhost}" --port "${CANARY_PORT:-6380}" \
            --connection-mode "${CANARY_MODE:-standalone}" \
            --canary-log "${canary_log}" 2>&1 || log_warn "Consistency checker failed"
        log_info "Running RTO/RPO reporter..."
        PYTHONPATH="${repo_root}" "${python_bin}" -m tooling.rto_rpo_report "${RUN_DIR}" 2>&1 \
            || log_warn "RTO/RPO reporter failed"
    fi
}

EVENTS_FILE=""
init_events_log() { EVENTS_FILE="${RUN_DIR}/events.jsonl"; touch "${EVENTS_FILE}"; }

# ── Grafana annotation helper (non-blocking, best-effort) ────────────────────
# Pushes an annotation to Grafana via the EventAnnotator.
# Silently skips if Grafana is unreachable or python3 is unavailable.
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_ANNOTATE="${GRAFANA_ANNOTATE:-true}"

_grafana_annotate() {
    local text="$1" tags="${2:-}"
    [[ "${GRAFANA_ANNOTATE}" != "true" ]] && return 0
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
    python3 -c "
import sys, os
sys.path.insert(0, '${repo_root}')
os.environ.setdefault('GRAFANA_URL', '${GRAFANA_URL}')
from observability.annotator import EventAnnotator
a = EventAnnotator()
a.annotate('${text}', tags=[t for t in '${tags}'.split(',') if t])
" >/dev/null 2>&1 &
    # Fire-and-forget — don't wait for the background process
}

mark_event() {
    local event_name="$1" detail="${2:-}"
    echo "{\"timestamp\":\"$(ts_now)\",\"epoch\":$(ts_epoch),\"event\":\"${event_name}\",\"detail\":\"${detail}\"}" >> "${EVENTS_FILE}"
    log_info "Event marked: ${event_name} ${detail}"
    # Push annotation to Grafana (non-blocking)
    _grafana_annotate "${event_name}: ${detail}" "${event_name}"
}

capture_redis_info() {
    local container="$1" label="${2:-snapshot}"
    local outfile="${RUN_DIR}/redis_info_${label}_$(date '+%H%M%S').txt"
    docker exec "$container" redis-cli -p ${REDIS_CLI_PORT} INFO ALL > "${outfile}" 2>/dev/null || true
    log_info "Redis INFO captured: ${outfile}"
}

capture_topology() {
    local label="${1:-snapshot}"
    local outfile="${RUN_DIR}/topology_${label}.txt"
    case "${PLATFORM}" in
        oss-cluster)  docker exec "${PRIMARY_CONTAINER:-redis-node1}" redis-cli -p ${REDIS_CLI_PORT} CLUSTER NODES > "${outfile}" 2>/dev/null || true ;;
        oss-sentinel) docker exec "${SENTINEL_CONTAINER:-sentinel1}" redis-cli -p 26379 SENTINEL masters > "${outfile}" 2>/dev/null || true ;;
        re)           capture_re_topology "${label}" ;;
    esac
    log_info "Topology captured: ${outfile}"
}

# ── Redis Enterprise helpers ──────────────────────────────────────────────────
# These functions use rladmin CLI (inside the RE container) and the REST API
# to perform real verification of RE cluster state, failover, and recovery.
#
# Required env vars for RE platform:
#   RE_CLUSTER_CONTAINER - Container running the RE cluster node (default: re-node1)
#   RE_API_PORT          - REST API port (default: 9443)
#   RE_DB_NAME           - Database name in RE (default: db1)
#   RE_API_USER          - REST API username (default: admin@redis.io)
#   RE_API_PASS          - REST API password (default: redis123)

RE_CLUSTER_CONTAINER="${RE_CLUSTER_CONTAINER:-re-node1}"
RE_API_PORT="${RE_API_PORT:-9443}"
RE_DB_NAME="${RE_DB_NAME:-db1}"
RE_API_USER="${RE_API_USER:-admin@redis.io}"
RE_API_PASS="${RE_API_PASS:-redis123}"

# Run rladmin inside the RE cluster container
_re_rladmin() {
    docker exec "${RE_CLUSTER_CONTAINER}" rladmin "$@" 2>/dev/null
}

# Call the RE REST API (GET by default)
_re_api() {
    local method="${1:-GET}" endpoint="$2"
    shift 2
    docker exec "${RE_CLUSTER_CONTAINER}" \
        curl -sk -u "${RE_API_USER}:${RE_API_PASS}" \
        -X "${method}" \
        -H "Content-Type: application/json" \
        "https://localhost:${RE_API_PORT}${endpoint}" "$@" 2>/dev/null
}

# Get the RE database UID by name
_re_get_db_uid() {
    _re_api GET "/v1/bdbs" | python3 -c "
import sys, json
try:
    dbs = json.load(sys.stdin)
    for db in dbs:
        if db.get('name') == '${RE_DB_NAME}':
            print(db['uid']); break
    else:
        print('')
except: print('')
" 2>/dev/null
}

# Capture full RE topology: rladmin status + REST API shard/endpoint info
capture_re_topology() {
    local label="${1:-snapshot}"
    local outfile="${RUN_DIR}/topology_${label}.txt"
    {
        echo "=== rladmin status (${label}) ==="
        _re_rladmin status || echo "(rladmin status unavailable)"
        echo ""
        echo "=== rladmin status shards ==="
        _re_rladmin status shards || echo "(rladmin status shards unavailable)"
        echo ""
        echo "=== REST API /v1/shards ==="
        _re_api GET "/v1/shards" | python3 -c "
import sys, json
try:
    shards = json.load(sys.stdin)
    for s in shards:
        print(f\"  shard {s.get('uid')}: role={s.get('role','?')} status={s.get('status','?')} node={s.get('node_uid','?')}\")
except: print('  (unavailable)')
" 2>/dev/null || echo "  (unavailable)"
        echo ""
        echo "=== REST API /v1/bdbs ==="
        _re_api GET "/v1/bdbs" | python3 -c "
import sys, json
try:
    dbs = json.load(sys.stdin)
    for db in dbs:
        print(f\"  db {db.get('uid')}: name={db.get('name','?')} status={db.get('status','?')} shards={db.get('shards_count','?')}\")
except: print('  (unavailable)')
" 2>/dev/null || echo "  (unavailable)"
    } > "${outfile}" 2>/dev/null
}

# Wait for RE failover to complete by polling shard roles via REST API.
# Detects that a new master shard has appeared (role changed) compared to
# the pre-disruption state.
# Args: $1 = max wait seconds (default 120)
#        $2 = pre-disruption master node UID (optional, for comparison)
# Returns 0 on success, 1 on timeout
wait_for_re_failover() {
    local max_wait="${1:-120}" pre_master_node="${2:-}"
    local elapsed=0
    log_info "Waiting for RE failover (timeout: ${max_wait}s)..."

    while [[ $elapsed -lt $max_wait ]]; do
        sleep 2
        elapsed=$(( elapsed + 2 ))

        # Query shard status via REST API
        local shard_info
        shard_info=$(_re_api GET "/v1/shards" 2>/dev/null | python3 -c "
import sys, json
try:
    shards = json.load(sys.stdin)
    masters = [s for s in shards if s.get('role') == 'master' and s.get('status') == 'active']
    if masters:
        m = masters[0]
        print(f\"OK node={m.get('node_uid','')} shard={m.get('uid','')} status={m.get('status','')}\")
    else:
        print('WAITING')
except: print('ERROR')
" 2>/dev/null)

        if [[ "${shard_info}" == WAITING ]] || [[ "${shard_info}" == ERROR ]]; then
            log_info "RE failover in progress... (${elapsed}s / ${max_wait}s)"
            continue
        fi

        if [[ "${shard_info}" == OK* ]]; then
            local new_node
            new_node=$(echo "${shard_info}" | sed 's/.*node=\([^ ]*\).*/\1/')
            # If we know the pre-disruption master node, verify it changed
            if [[ -n "${pre_master_node}" ]] && [[ "${new_node}" == "${pre_master_node}" ]]; then
                log_info "RE master still on original node ${new_node}, waiting... (${elapsed}s)"
                continue
            fi
            log_ok "RE failover detected: ${shard_info} (elapsed: ${elapsed}s)"
            mark_event "failover_detected" "elapsed=${elapsed}s ${shard_info}"
            return 0
        fi

        log_info "RE failover check: ${shard_info} (${elapsed}s / ${max_wait}s)"
    done

    log_warn "RE failover not confirmed within ${max_wait}s"
    mark_event "failover_timeout" "max_wait=${max_wait}s"
    return 1
}

# Wait for RE recovery — all shards active and cluster healthy
# Args: $1 = max wait seconds (default 120)
# Returns 0 on success, 1 on timeout
wait_for_re_recovery() {
    local max_wait="${1:-120}"
    local elapsed=0
    log_info "Waiting for RE recovery (timeout: ${max_wait}s)..."

    while [[ $elapsed -lt $max_wait ]]; do
        sleep 2
        elapsed=$(( elapsed + 2 ))

        # Check cluster health via rladmin
        local cluster_ok
        cluster_ok=$(_re_rladmin status 2>/dev/null | grep -c "OK" || echo "0")

        # Check all shards are active via REST API
        local shard_status
        shard_status=$(_re_api GET "/v1/shards" 2>/dev/null | python3 -c "
import sys, json
try:
    shards = json.load(sys.stdin)
    total = len(shards)
    active = sum(1 for s in shards if s.get('status') == 'active')
    if total > 0 and active == total:
        print(f'OK active={active}/{total}')
    else:
        print(f'WAITING active={active}/{total}')
except: print('ERROR')
" 2>/dev/null)

        if [[ "${shard_status}" == OK* ]]; then
            log_ok "RE recovery confirmed: ${shard_status} (elapsed: ${elapsed}s)"
            mark_event "recovery_detected" "elapsed=${elapsed}s ${shard_status}"
            return 0
        fi

        log_info "RE recovery in progress: ${shard_status} (${elapsed}s / ${max_wait}s)"
    done

    log_warn "RE recovery not confirmed within ${max_wait}s"
    mark_event "recovery_timeout" "max_wait=${max_wait}s"
    return 1
}

# Get the node UID of the current RE master shard
# Prints the node UID or empty string
re_get_master_node() {
    _re_api GET "/v1/shards" 2>/dev/null | python3 -c "
import sys, json
try:
    shards = json.load(sys.stdin)
    masters = [s for s in shards if s.get('role') == 'master' and s.get('status') == 'active']
    if masters:
        print(masters[0].get('node_uid', ''))
    else:
        print('')
except: print('')
" 2>/dev/null
}

# Check RE cluster health — returns 0 if healthy, 1 otherwise
re_cluster_healthy() {
    local node_status
    node_status=$(_re_api GET "/v1/nodes" 2>/dev/null | python3 -c "
import sys, json
try:
    nodes = json.load(sys.stdin)
    total = len(nodes)
    active = sum(1 for n in nodes if n.get('status') == 'active')
    if total > 0 and active == total:
        print(f'OK active={active}/{total}')
    else:
        print(f'DEGRADED active={active}/{total}')
except: print('ERROR')
" 2>/dev/null)
    [[ "${node_status}" == OK* ]]
}

export_evidence() {
    log_step 9 "Export evidence and record operator actions"
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$(dirname "$0")/../..")"
    local exporter="${repo_root}/observability/exporters/run_summary_exporter.py"
    local python_bin="python3"
    if [[ -x "${repo_root}/.venv/bin/python3" ]]; then
        python_bin="${repo_root}/.venv/bin/python3"
    fi
    if [[ -f "${exporter}" ]]; then
        log_info "Running evidence exporter..."
        "${python_bin}" "${exporter}" "${RUN_DIR}" || log_warn "Evidence exporter failed — falling back to basic summary"
    else
        log_warn "Evidence exporter not found at ${exporter} — writing basic summary"
        local summary="${RUN_DIR}/run_summary.json"
        cat > "${summary}" <<SUMEOF
{
  "run_id": "${RUN_ID}",
  "platform": "${PLATFORM}",
  "completed_at": "$(ts_now)",
  "results_dir": "${RUN_DIR}",
  "files": $(ls -1 "${RUN_DIR}" | "${python_bin}" -c "import sys,json; print(json.dumps(sys.stdin.read().strip().split('\n')))" 2>/dev/null || echo '[]')
}
SUMEOF
    fi
    log_ok "Evidence exported to ${RUN_DIR}"
}

cleanup() { stop_canary; stop_locust; log_info "Cleanup complete"; }
trap cleanup EXIT

