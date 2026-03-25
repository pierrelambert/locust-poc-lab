#!/usr/bin/env bash
set -euo pipefail

readonly RE_API_USER="${RE_API_USER:-admin@redis.io}"
readonly RE_API_PASS="${RE_API_PASS:-redis123}"
readonly RE_API_PORT="${RE_API_PORT:-9443}"
readonly RE_CLUSTER_NAME="${RE_CLUSTER_NAME:-locust-poc-lab.local}"
readonly RE_DB_NAME="${RE_DB_NAME:-db1}"
readonly RE_DB_PORT="${RE_DB_PORT:-12000}"
readonly RE_DB_MEMORY_SIZE="${RE_DB_MEMORY_SIZE:-1073741824}"
readonly NODE1_CONTAINER="${NODE1_CONTAINER:-re-node1}"
readonly NODE2_CONTAINER="${NODE2_CONTAINER:-re-node2}"
readonly NODE3_CONTAINER="${NODE3_CONTAINER:-re-node3}"
readonly NODE1_ADDR="${NODE1_ADDR:-172.28.0.11}"
readonly NODE2_ADDR="${NODE2_ADDR:-172.28.0.12}"
readonly NODE3_ADDR="${NODE3_ADDR:-172.28.0.13}"
readonly RETRY_INTERVAL=2

usage() {
    cat <<'EOF'
Usage: bash infra/docker/re-cluster/bootstrap.sh [--help]

Bootstraps the Redis Enterprise cluster after `make re-up`:
  1. Create the cluster on re-node1
  2. Join re-node2 and re-node3
  3. Create the db1 database on port 12000
  4. Verify redis-cli -p 12000 PING returns PONG

Safe to re-run: existing cluster nodes and db1 are detected and reused.
EOF
}

info() { echo "[re-bootstrap] $*"; }
ok() { echo "[re-bootstrap] OK: $*"; }
warn() { echo "[re-bootstrap] WARN: $*" >&2; }
fail() { echo "[re-bootstrap] ERROR: $*" >&2; exit 1; }

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

ensure_container_running() {
    local container="$1"
    docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q '^true$' \
        || fail "Container ${container} is not running. Start the RE stack first (make re-up)."
}

container_bootstrap_get() {
    local container="$1"
    docker exec "$container" curl -sk "https://localhost:${RE_API_PORT}/v1/bootstrap" 2>/dev/null || true
}

container_bootstrap_post() {
    local container="$1" endpoint="$2" payload="$3"
    docker exec "$container" curl -sk \
        -X POST \
        -H 'Content-Type: application/json' \
        -d "$payload" \
        -w $'\n%{http_code}' \
        "https://localhost:${RE_API_PORT}${endpoint}" 2>/dev/null || true
}

container_auth_api() {
    local container="$1" method="$2" endpoint="$3" payload="${4:-}"
    if [[ -n "$payload" ]]; then
        docker exec "$container" curl -sk \
            -u "${RE_API_USER}:${RE_API_PASS}" \
            -X "$method" \
            -H 'Content-Type: application/json' \
            -d "$payload" \
            "https://localhost:${RE_API_PORT}${endpoint}" 2>/dev/null || true
    else
        docker exec "$container" curl -sk \
            -u "${RE_API_USER}:${RE_API_PASS}" \
            -X "$method" \
            -H 'Content-Type: application/json' \
            "https://localhost:${RE_API_PORT}${endpoint}" 2>/dev/null || true
    fi
}

http_code_from_response() {
    printf '%s\n' "$1" | tail -n1
}

body_from_response() {
    printf '%s\n' "$1" | sed '$d'
}

json_is_valid() {
    printf '%s' "$1" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
}

container_api_ready() {
    local container="$1" body=''
    body="$(container_bootstrap_get "$container")"
    if [[ -n "$body" ]] && json_is_valid "$body"; then
        return 0
    fi
    body="$(container_auth_api "$container" GET /v1/nodes)"
    [[ -n "$body" ]] && json_is_valid "$body"
}

wait_for_bootstrap_api() {
    local container="$1" timeout="${2:-180}" elapsed=0
    info "Waiting for ${container} bootstrap API on port ${RE_API_PORT}..."
    while true; do
        if container_api_ready "$container"; then
            ok "${container} bootstrap API is responding"
            return 0
        fi
        sleep "${RETRY_INTERVAL}"
        elapsed=$((elapsed + RETRY_INTERVAL))
        if [[ $elapsed -ge $timeout ]]; then
            fail "${container} bootstrap API did not become ready after ${timeout}s"
        fi
    done
}

create_cluster_payload() {
    python3 - <<PY
import json
print(json.dumps({
    "action": "create_cluster",
    "cluster": {"name": "${RE_CLUSTER_NAME}", "nodes": []},
    "credentials": {"username": "${RE_API_USER}", "password": "${RE_API_PASS}"},
    "node": {"paths": {"persistent_path": "/var/opt/redislabs/persist", "ephemeral_path": "/var/opt/redislabs/tmp"}},
    "license": "",
}))
PY
}

join_cluster_payload() {
    python3 - <<PY
import json
print(json.dumps({
    "action": "join_cluster",
    "cluster": {"nodes": ["${NODE1_ADDR}"]},
    "credentials": {"username": "${RE_API_USER}", "password": "${RE_API_PASS}"},
    "node": {"paths": {"persistent_path": "/var/opt/redislabs/persist", "ephemeral_path": "/var/opt/redislabs/tmp"}},
}))
PY
}

create_database_payload() {
    python3 - <<PY
import json
print(json.dumps({
    "name": "${RE_DB_NAME}",
    "type": "redis",
    "memory_size": int("${RE_DB_MEMORY_SIZE}"),
    "port": int("${RE_DB_PORT}"),
    "proxy_policy": "all-nodes",
    "replication": True,
    "shards_count": 1,
    "shard_key_regex": [
        {"regex": r".*\\{(?<tag>.*)\\}.*"},
        {"regex": r"(?<tag>.*)"},
    ],
    "data_persistence": "aof",
    "aof_policy": "appendfsync-every-sec",
}))
PY
}

extract_nodes_json() {
    python3 -c 'import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("[]")
    raise SystemExit(0)
if isinstance(data, list):
    nodes = data
elif isinstance(data, dict) and isinstance(data.get("nodes"), list):
    nodes = data["nodes"]
elif isinstance(data, dict) and isinstance(data.get("data"), list):
    nodes = data["data"]
else:
    nodes = []
print(json.dumps(nodes))'
}

nodes_json() {
    container_auth_api "$NODE1_CONTAINER" GET /v1/nodes | extract_nodes_json
}

cluster_bootstrapped() {
    local nodes
    nodes="$(nodes_json)"
    printf '%s' "$nodes" | python3 -c 'import json, sys
try:
    nodes = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if len(nodes) >= 1 else 1)'
}

node_present() {
    local addr="$1" nodes
    nodes="$(nodes_json)"
    printf '%s' "$nodes" | python3 -c 'import json, sys
target = sys.argv[1]
try:
    nodes = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for node in nodes:
    if target in json.dumps(node, sort_keys=True):
        raise SystemExit(0)
raise SystemExit(1)' "$addr"
}

active_node_count() {
    local nodes
    nodes="$(nodes_json)"
    printf '%s' "$nodes" | python3 -c 'import json, sys
try:
    nodes = json.load(sys.stdin)
except Exception:
    print(0)
    raise SystemExit(0)
count = 0
for node in nodes:
    status = str(node.get("status", "")).lower()
    if status == "active":
        count += 1
print(count)'
}

bootstrap_cluster_if_needed() {
    local response http_code body payload elapsed=0
    if cluster_bootstrapped; then
        info "Cluster already bootstrapped — skipping create_cluster"
        return 0
    fi
    info "Bootstrapping Redis Enterprise cluster on ${NODE1_CONTAINER}..."
    payload="$(create_cluster_payload)"
    while true; do
        response="$(container_bootstrap_post "$NODE1_CONTAINER" /v1/bootstrap/create_cluster "$payload")"
        http_code="$(http_code_from_response "$response")"
        body="$(body_from_response "$response")"
        if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
            ok "create_cluster accepted (${http_code})"
            return 0
        fi
        if printf '%s' "$body" | grep -Eqi 'already|cluster.*exist|bootstrapped'; then
            info "Cluster create call reports existing cluster — continuing"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        if [[ $elapsed -ge 120 ]]; then
            fail "create_cluster failed after retries (last HTTP ${http_code:-unknown})"
        fi
    done
}

join_node_if_needed() {
    local container="$1" addr="$2" response http_code body payload elapsed=0
    if node_present "$addr"; then
        info "${container} (${addr}) already part of cluster — skipping join"
        return 0
    fi
    wait_for_bootstrap_api "$container" 180
    info "Joining ${container} (${addr}) to the cluster..."
    payload="$(join_cluster_payload)"
    while true; do
        response="$(container_bootstrap_post "$container" /v1/bootstrap/join_cluster "$payload")"
        http_code="$(http_code_from_response "$response")"
        body="$(body_from_response "$response")"
        if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
            ok "join_cluster accepted for ${container} (${http_code})"
            return 0
        fi
        if printf '%s' "$body" | grep -Eqi 'already|member|join.*progress'; then
            info "${container} reports join already in progress/existing — continuing"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        if [[ $elapsed -ge 120 ]]; then
            fail "join_cluster failed for ${container} after retries (last HTTP ${http_code:-unknown})"
        fi
    done
}

wait_for_active_nodes() {
    local expected="${1:-3}" timeout="${2:-240}" elapsed=0 active
    info "Waiting for ${expected} active RE nodes..."
    while true; do
        active="$(active_node_count)"
        if [[ "$active" -ge "$expected" ]]; then
            ok "Detected ${active} active RE nodes"
            return 0
        fi
        sleep "${RETRY_INTERVAL}"
        elapsed=$((elapsed + RETRY_INTERVAL))
        if [[ $elapsed -ge $timeout ]]; then
            fail "Only ${active} active RE nodes after ${timeout}s"
        fi
    done
}

database_list() {
    container_auth_api "$NODE1_CONTAINER" GET /v1/bdbs
}

database_exists() {
    local dbs
    dbs="$(database_list)"
    printf '%s' "$dbs" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    dbs = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
items = dbs if isinstance(dbs, list) else dbs.get("bdbs", [])
for db in items:
    if db.get("name") == name:
        raise SystemExit(0)
raise SystemExit(1)' "${RE_DB_NAME}"
}

database_status() {
    local dbs
    dbs="$(database_list)"
    printf '%s' "$dbs" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    dbs = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
items = dbs if isinstance(dbs, list) else dbs.get("bdbs", [])
for db in items:
    if db.get("name") == name:
        print(db.get("status", ""))
        raise SystemExit(0)
print("")' "${RE_DB_NAME}"
}

database_uid() {
    local dbs
    dbs="$(database_list)"
    printf '%s' "$dbs" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    dbs = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
items = dbs if isinstance(dbs, list) else dbs.get("bdbs", [])
for db in items:
    if db.get("name") == name:
        print(db.get("uid", ""))
        raise SystemExit(0)
print("")' "${RE_DB_NAME}"
}

database_endpoint_uid() {
    local dbs
    dbs="$(database_list)"
    printf '%s' "$dbs" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    dbs = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
items = dbs if isinstance(dbs, list) else dbs.get("bdbs", [])
for db in items:
    if db.get("name") == name:
        endpoints = db.get("endpoints") or []
        if endpoints:
            print(endpoints[0].get("uid", ""))
        else:
            print("")
        raise SystemExit(0)
print("")' "${RE_DB_NAME}"
}

database_proxy_policy() {
    local dbs
    dbs="$(database_list)"
    printf '%s' "$dbs" | python3 -c 'import json, sys
name = sys.argv[1]
try:
    dbs = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
items = dbs if isinstance(dbs, list) else dbs.get("bdbs", [])
for db in items:
    if db.get("name") == name:
        print(db.get("proxy_policy", ""))
        raise SystemExit(0)
print("")' "${RE_DB_NAME}"
}

ensure_database_proxy_policy() {
    local policy uid endpoint payload
    policy="$(database_proxy_policy)"
    if [[ "$policy" == "all-nodes" ]]; then
        info "Database ${RE_DB_NAME} proxy policy already set to all-nodes"
        return 0
    fi
    uid="$(database_uid)"
    endpoint="$(database_endpoint_uid)"
    [[ -n "$uid" ]] || fail "Could not determine UID for database ${RE_DB_NAME}"
    [[ -n "$endpoint" ]] || fail "Could not determine endpoint UID for database ${RE_DB_NAME}"
    payload="$(python3 - <<PY
import json
print(json.dumps({"proxy_policy": "all-nodes", "endpoint": "${endpoint}"}))
PY
)"
    info "Updating database ${RE_DB_NAME} proxy policy to all-nodes..."
    container_auth_api "$NODE1_CONTAINER" PUT "/v1/bdbs/${uid}" "$payload" >/dev/null
}

create_database_if_needed() {
    local payload
    if database_exists; then
        info "Database ${RE_DB_NAME} already exists — skipping create"
        return 0
    fi
    info "Creating Redis Enterprise database ${RE_DB_NAME} on port ${RE_DB_PORT}..."
    payload="$(create_database_payload)"
    container_auth_api "$NODE1_CONTAINER" POST /v1/bdbs "$payload" >/dev/null
    ok "Database create request submitted"
}

wait_for_database_active() {
    local timeout="${1:-180}" elapsed=0 status=''
    info "Waiting for database ${RE_DB_NAME} to become active..."
    while true; do
        status="$(database_status)"
        if [[ "$status" == "active" ]]; then
            ok "Database ${RE_DB_NAME} is active"
            return 0
        fi
        sleep "${RETRY_INTERVAL}"
        elapsed=$((elapsed + RETRY_INTERVAL))
        if [[ $elapsed -ge $timeout ]]; then
            fail "Database ${RE_DB_NAME} did not become active after ${timeout}s (last status: ${status:-unknown})"
        fi
    done
}

verify_database_ping() {
    local timeout="${1:-120}" elapsed=0
    info "Verifying redis-cli -p ${RE_DB_PORT} PING on ${NODE1_CONTAINER}..."
    while ! docker exec "$NODE1_CONTAINER" redis-cli -p "$RE_DB_PORT" PING 2>/dev/null | grep -q PONG; do
        sleep "${RETRY_INTERVAL}"
        elapsed=$((elapsed + RETRY_INTERVAL))
        if [[ $elapsed -ge $timeout ]]; then
            fail "Database on ${NODE1_CONTAINER}:${RE_DB_PORT} did not respond to PING after ${timeout}s"
        fi
    done
    ok "Database on ${NODE1_CONTAINER}:${RE_DB_PORT} is responding to PING"
}

main() {
    if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
        usage
        exit 0
    fi

    require_command docker
    require_command python3
    ensure_container_running "$NODE1_CONTAINER"
    ensure_container_running "$NODE2_CONTAINER"
    ensure_container_running "$NODE3_CONTAINER"

    wait_for_bootstrap_api "$NODE1_CONTAINER" 180
    bootstrap_cluster_if_needed
    join_node_if_needed "$NODE2_CONTAINER" "$NODE2_ADDR"
    join_node_if_needed "$NODE3_CONTAINER" "$NODE3_ADDR"
    wait_for_active_nodes 3 240
    create_database_if_needed
    ensure_database_proxy_policy
    wait_for_database_active 180
    verify_database_ping 120
    ok "Redis Enterprise bootstrap complete"
}

main "$@"