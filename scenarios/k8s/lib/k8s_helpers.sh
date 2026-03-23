#!/usr/bin/env bash
# k8s_helpers.sh — Shared helpers for Kubernetes scenario scripts
# Source this file: source "$(dirname "$0")/lib/k8s_helpers.sh"
set -euo pipefail

# ── Source common helpers (logging, Locust, evidence) ─────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${REPO_ROOT}/scenarios/scripts/lib/common.sh"

# ── k8s Defaults ──────────────────────────────────────────────────────────────
K8S_NAMESPACE="${K8S_NAMESPACE:-redis-oss}"
K8S_REDIS_LABEL="${K8S_REDIS_LABEL:-app=redis}"
K8S_SENTINEL_LABEL="${K8S_SENTINEL_LABEL:-app=redis-sentinel}"
K8S_REDIS_SERVICE="${K8S_REDIS_SERVICE:-redis}"
K8S_SENTINEL_SERVICE="${K8S_SENTINEL_SERVICE:-redis-sentinel}"
K8S_REDIS_PORT="${K8S_REDIS_PORT:-6379}"
K8S_SENTINEL_PORT="${K8S_SENTINEL_PORT:-26379}"
K8S_LOCAL_REDIS_PORT="${K8S_LOCAL_REDIS_PORT:-16379}"
K8S_LOCAL_SENTINEL_PORT="${K8S_LOCAL_SENTINEL_PORT:-16380}"

# Override LOCUST_HOST to point at port-forwarded Redis
LOCUST_HOST="${LOCUST_HOST:-redis://localhost:${K8S_LOCAL_REDIS_PORT}}"

# Track port-forward PIDs for cleanup
_PF_PIDS=()

# ── Port-forward management ──────────────────────────────────────────────────

start_port_forward() {
    local service="$1" local_port="$2" remote_port="$3" label="${4:-}"
    log_info "Starting port-forward: ${service} ${local_port}:${remote_port} in ${K8S_NAMESPACE}"
    kubectl port-forward "svc/${service}" "${local_port}:${remote_port}" \
        -n "${K8S_NAMESPACE}" > /dev/null 2>&1 &
    local pf_pid=$!
    _PF_PIDS+=("${pf_pid}")
    sleep 2
    if ! kill -0 "${pf_pid}" 2>/dev/null; then
        log_error "Port-forward failed for ${service}"
        return 1
    fi
    log_ok "Port-forward active: localhost:${local_port} → ${service}:${remote_port} (PID: ${pf_pid})"
}

stop_port_forwards() {
    for pid in "${_PF_PIDS[@]:-}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
        fi
    done
    _PF_PIDS=()
    log_info "All port-forwards stopped"
}

# ── Pod selection ─────────────────────────────────────────────────────────────

# Get pod names matching a label selector
k8s_get_pods() {
    local label="${1:-${K8S_REDIS_LABEL}}"
    kubectl get pods -n "${K8S_NAMESPACE}" -l "${label}" \
        -o jsonpath='{.items[*].metadata.name}' 2>/dev/null
}

# Get the primary Redis pod (redis-0 by convention in our StatefulSet)
k8s_get_primary_pod() {
    echo "redis-0"
}

# Get the node a pod is running on
k8s_get_pod_node() {
    local pod="$1"
    kubectl get pod "${pod}" -n "${K8S_NAMESPACE}" \
        -o jsonpath='{.spec.nodeName}' 2>/dev/null
}

# ── Wait helpers ──────────────────────────────────────────────────────────────

wait_for_pod_ready() {
    local pod="$1" timeout="${2:-120}"
    log_info "Waiting for pod ${pod} to be ready (timeout: ${timeout}s)..."
    if kubectl wait --for=condition=Ready "pod/${pod}" \
        -n "${K8S_NAMESPACE}" --timeout="${timeout}s" 2>/dev/null; then
        log_ok "Pod ${pod} is ready"
        return 0
    else
        log_error "Pod ${pod} not ready within ${timeout}s"
        return 1
    fi
}

wait_for_all_pods_ready() {
    local label="${1:-${K8S_REDIS_LABEL}}" timeout="${2:-180}"
    log_info "Waiting for all pods with label ${label} to be ready..."
    kubectl wait --for=condition=Ready pods -l "${label}" \
        -n "${K8S_NAMESPACE}" --timeout="${timeout}s" 2>/dev/null
    log_ok "All pods with label ${label} are ready"
}

wait_for_k8s_redis() {
    local port="${1:-${K8S_LOCAL_REDIS_PORT}}" timeout="${2:-60}" elapsed=0
    log_info "Waiting for Redis PING on localhost:${port} (timeout: ${timeout}s)..."
    while ! redis-cli -p "${port}" PING 2>/dev/null | grep -q PONG; do
        sleep 1; elapsed=$((elapsed + 1))
        [[ $elapsed -ge $timeout ]] && { log_error "Redis not responding on port ${port} within ${timeout}s"; return 1; }
    done
    log_ok "Redis responding on localhost:${port}"
}

# ── k8s-specific environment check ───────────────────────────────────────────

k8s_check_environment() {
    log_step 1 "Verify k8s environment"
    [[ -z "${LOCUST_FILE}" ]] && { log_error "LOCUST_FILE must be set"; exit 1; }
    [[ ! -f "${LOCUST_FILE}" ]] && { log_error "Locustfile not found: ${LOCUST_FILE}"; exit 1; }

    # Verify namespace exists
    if ! kubectl get namespace "${K8S_NAMESPACE}" &>/dev/null; then
        log_error "Namespace ${K8S_NAMESPACE} not found. Run 'make k8s-oss-up' first."
        exit 1
    fi

    # Verify Redis pods are running
    local pod_count
    pod_count=$(kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_REDIS_LABEL}" \
        --field-selector=status.phase=Running -o name 2>/dev/null | wc -l | tr -d ' ')
    if [[ "${pod_count}" -eq 0 ]]; then
        log_error "No running Redis pods found in ${K8S_NAMESPACE}"
        exit 1
    fi
    log_ok "Found ${pod_count} running Redis pod(s) in ${K8S_NAMESPACE}"

    # Save environment metadata
    local env_file="${RUN_DIR}/environment.json"
    local primary_pod
    primary_pod=$(k8s_get_primary_pod)
    local primary_node
    primary_node=$(k8s_get_pod_node "${primary_pod}")
    cat > "${env_file}" <<ENVEOF
{
  "platform": "k8s-oss",
  "timestamp": "$(ts_now)",
  "locust_file": "${LOCUST_FILE}",
  "workload_profile": "${WORKLOAD_PROFILE}",
  "locust_users": ${LOCUST_USERS},
  "locust_spawn_rate": ${LOCUST_SPAWN_RATE},
  "locust_host": "${LOCUST_HOST}",
  "k8s_namespace": "${K8S_NAMESPACE}",
  "pod_name": "${primary_pod}",
  "node_name": "${primary_node}",
  "redis_version": "$(kubectl exec "${primary_pod}" -n "${K8S_NAMESPACE}" -- redis-cli INFO server 2>/dev/null | grep redis_version | tr -d '\r' || echo 'unavailable')"
}
ENVEOF
    log_ok "Environment metadata saved to ${env_file}"
}

# ── k8s-specific Redis INFO capture ──────────────────────────────────────────

k8s_capture_redis_info() {
    local pod="${1:-redis-0}" label="${2:-snapshot}"
    local outfile="${RUN_DIR}/redis_info_${label}_$(date '+%H%M%S').txt"
    kubectl exec "${pod}" -n "${K8S_NAMESPACE}" -- redis-cli INFO ALL > "${outfile}" 2>/dev/null || true
    log_info "Redis INFO captured from pod ${pod}: ${outfile}"
}

k8s_capture_topology() {
    local label="${1:-snapshot}"
    local outfile="${RUN_DIR}/topology_${label}.txt"
    {
        echo "=== Redis Pods (${label}) ==="
        kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_REDIS_LABEL}" -o wide 2>/dev/null || echo "(unavailable)"
        echo ""
        echo "=== Sentinel Pods ==="
        kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_SENTINEL_LABEL}" -o wide 2>/dev/null || echo "(unavailable)"
        echo ""
        echo "=== Services ==="
        kubectl get svc -n "${K8S_NAMESPACE}" -o wide 2>/dev/null || echo "(unavailable)"
        echo ""
        echo "=== Sentinel Master Info ==="
        local sentinel_pod
        sentinel_pod=$(kubectl get pods -n "${K8S_NAMESPACE}" -l "${K8S_SENTINEL_LABEL}" \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "${sentinel_pod}" ]]; then
            kubectl exec "${sentinel_pod}" -n "${K8S_NAMESPACE}" -- \
                redis-cli -p 26379 SENTINEL masters 2>/dev/null || echo "(unavailable)"
        fi
    } > "${outfile}" 2>/dev/null
    log_info "Topology captured: ${outfile}"
}

# ── k8s event marking ────────────────────────────────────────────────────────

k8s_mark_event() {
    local event_name="$1" detail="${2:-}"
    local pod_name="${3:-}" node_name="${4:-}"
    local extra=""
    [[ -n "${pod_name}" ]] && extra="${extra},\"pod_name\":\"${pod_name}\""
    [[ -n "${node_name}" ]] && extra="${extra},\"node_name\":\"${node_name}\""
    echo "{\"timestamp\":\"$(ts_now)\",\"epoch\":$(ts_epoch),\"event\":\"${event_name}\",\"detail\":\"${detail}\",\"namespace\":\"${K8S_NAMESPACE}\"${extra}}" >> "${EVENTS_FILE}"
    log_info "Event marked: ${event_name} ${detail}"
}

# ── k8s dataset check ────────────────────────────────────────────────────────

k8s_check_dataset() {
    local port="${1:-${K8S_LOCAL_REDIS_PORT}}"
    log_step 2 "Verify dataset is primed"
    local key_count
    key_count=$(redis-cli -p "${port}" DBSIZE 2>/dev/null | grep -o '[0-9]*' || echo "0")
    log_info "Current key count: ${key_count}"
    if [[ "${key_count}" -eq 0 ]]; then
        log_warn "Database is empty — ensure dataset is primed before running scenario"
    fi
    k8s_mark_event "dataset_check" "key_count=${key_count}"
}

# ── Cleanup override ─────────────────────────────────────────────────────────

k8s_cleanup() {
    stop_locust
    stop_port_forwards
    log_info "k8s cleanup complete"
}
trap k8s_cleanup EXIT

