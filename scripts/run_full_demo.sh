#!/usr/bin/env bash
# run_full_demo.sh — End-to-end orchestrator for the Locust POC Lab demo
#
# Starts all required stacks, runs baseline + primary-kill scenarios on both
# RE and OSS Sentinel, exports evidence, runs cross-run comparisons, computes
# RTO/RPO, and assembles results into a timestamped directory.
#
# Usage:
#   bash scripts/run_full_demo.sh
#   BASELINE_DURATION=60 WARMUP_DURATION=30 bash scripts/run_full_demo.sh
#
# Environment variables (all optional — sensible demo defaults provided):
#   BASELINE_DURATION       — Baseline run duration in seconds (default: 120)
#   WARMUP_DURATION         — Warmup duration in seconds (default: 60)
#   POST_RECOVERY_DURATION  — Post-recovery observation in seconds (default: 60)
#   LOCUST_USERS            — Number of simulated users (default: 10)
#   LOCUST_SPAWN_RATE       — User spawn rate (default: 2)
#   SKIP_RE                 — Set to "true" to skip RE scenarios
#   SKIP_OSS                — Set to "true" to skip OSS Sentinel scenarios

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

# ── Demo defaults (shorter than production) ────────────────────────────────
export BASELINE_DURATION="${BASELINE_DURATION:-120}"
export WARMUP_DURATION="${WARMUP_DURATION:-60}"
export POST_RECOVERY_DURATION="${POST_RECOVERY_DURATION:-60}"
export LOCUST_USERS="${LOCUST_USERS:-10}"
export LOCUST_SPAWN_RATE="${LOCUST_SPAWN_RATE:-2}"
export LOCUST_FILE="${LOCUST_FILE:-workloads/locustfiles/cache_read_heavy.py}"
SKIP_RE="${SKIP_RE:-false}"
SKIP_OSS="${SKIP_OSS:-false}"

DEMO_TS="$(date '+%Y%m%d_%H%M%S')"
DEMO_DIR="${REPO_ROOT}/results/demo_${DEMO_TS}"
mkdir -p "${DEMO_DIR}"
LOG_FILE="${DEMO_DIR}/orchestrator.log"

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[DEMO]${NC} $(date '+%H:%M:%S') $*" | tee -a "${LOG_FILE}"; }
ok()    { echo -e "${GREEN}[DEMO]${NC} $(date '+%H:%M:%S') $*" | tee -a "${LOG_FILE}"; }
warn()  { echo -e "${YELLOW}[DEMO]${NC} $(date '+%H:%M:%S') $*" | tee -a "${LOG_FILE}"; }
fail()  { echo -e "${RED}[DEMO]${NC} $(date '+%H:%M:%S') $*" | tee -a "${LOG_FILE}"; }

STACKS_STARTED=""
ALL_OK=true

# ── Teardown trap ──────────────────────────────────────────────────────────
cleanup() {
    info "Cleaning up..."
    if [[ "${STACKS_STARTED}" == *"obs"* ]]; then
        make obs-down 2>/dev/null || true
    fi
    if [[ "${STACKS_STARTED}" == *"oss"* ]]; then
        make oss-sentinel-down 2>/dev/null || true
    fi
    if [[ "${STACKS_STARTED}" == *"re"* ]]; then
        make re-down 2>/dev/null || true
    fi
    info "Teardown complete."
}
trap cleanup EXIT

# ── Helpers ────────────────────────────────────────────────────────────────
stack_running() {
    local compose_file="$1" project="$2"
    docker compose -f "${compose_file}" -p "${project}" ps --status running 2>/dev/null | grep -q .
}

wait_for_healthy_redis() {
    local container="$1" timeout="${2:-60}" elapsed=0
    info "Waiting for Redis PING on ${container}..."
    while ! docker exec "$container" redis-cli PING 2>/dev/null | grep -q PONG; do
        sleep 2; elapsed=$((elapsed + 2))
        if [[ $elapsed -ge $timeout ]]; then
            warn "Redis on ${container} not ready after ${timeout}s"
            return 1
        fi
    done
    ok "Redis on ${container} is responding"
}

re_image_available() {
    docker image inspect redislabs/redis:latest >/dev/null 2>&1
}

run_scenario() {
    local script="$1" label="$2"
    info "━━━ Running: ${label} ━━━"
    if bash "${script}" >> "${LOG_FILE}" 2>&1; then
        ok "${label} completed successfully"
        return 0
    else
        fail "${label} FAILED (exit $?)"
        ALL_OK=false
        return 1
    fi
}

find_run_dir() {
    local pattern="$1"
    # shellcheck disable=SC2012
    ls -dt "${REPO_ROOT}/results/"${pattern}* 2>/dev/null | head -1
}

export_summary() {
    local run_dir="$1"
    if [[ -n "${run_dir}" ]] && [[ -d "${run_dir}" ]]; then
        info "Exporting summary for $(basename "${run_dir}")..."
        python3 observability/exporters/run_summary_exporter.py "${run_dir}" \
            >> "${LOG_FILE}" 2>&1 || warn "Summary export failed for ${run_dir}"
    fi
}

# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║          Locust POC Lab — Full Demo Orchestrator            ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
info "Demo output directory: ${DEMO_DIR}"
info "Baseline: ${BASELINE_DURATION}s | Warmup: ${WARMUP_DURATION}s | Recovery: ${POST_RECOVERY_DURATION}s"

# ── Step 1: Start infrastructure stacks ────────────────────────────────────
info "Step 1: Starting infrastructure stacks..."

# Observability stack
if stack_running "observability/docker-compose.yml" "obs-stack"; then
    info "Observability stack already running — skipping startup"
else
    info "Starting observability stack..."
    make obs-up >> "${LOG_FILE}" 2>&1 || warn "Observability stack failed to start"
    STACKS_STARTED="${STACKS_STARTED} obs"
fi

# OSS Sentinel stack
if [[ "${SKIP_OSS}" != "true" ]]; then
    if stack_running "infra/docker/oss-sentinel/docker-compose.yml" "oss-sentinel"; then
        info "OSS Sentinel stack already running — skipping startup"
    else
        info "Starting OSS Sentinel stack..."
        make oss-sentinel-up >> "${LOG_FILE}" 2>&1
        STACKS_STARTED="${STACKS_STARTED} oss"
    fi
    wait_for_healthy_redis "redis-primary" 90 || { fail "OSS primary not healthy"; SKIP_OSS="true"; }
fi

# RE stack
if [[ "${SKIP_RE}" != "true" ]]; then
    if stack_running "infra/docker/re-cluster/docker-compose.yml" "re-cluster"; then
        info "RE cluster already running — skipping startup"
    else
        info "Starting Redis Enterprise cluster..."
        make re-up >> "${LOG_FILE}" 2>&1
        STACKS_STARTED="${STACKS_STARTED} re"
        info "Waiting for RE nodes to boot (30s)..."
        sleep 30
    fi
    wait_for_healthy_redis "re-node1" 120 || { warn "RE node1 not responding — skipping RE"; SKIP_RE="true"; }
fi

if [[ "${SKIP_RE}" == "true" ]] && [[ "${SKIP_OSS}" == "true" ]]; then
    fail "Both RE and OSS stacks unavailable — nothing to do."
    exit 1
fi

ok "Infrastructure stacks ready"

# ── Step 2: Run baseline scenarios ─────────────────────────────────────────
info "Step 2: Running baseline scenarios..."

BASELINE_RE_DIR=""
BASELINE_OSS_DIR=""

if [[ "${SKIP_RE}" != "true" ]]; then
    PLATFORM="re" \
    PRIMARY_CONTAINER="re-node1" \
    LOCUST_HOST="redis://localhost:12000" \
        run_scenario "scenarios/scripts/01_baseline.sh" "Baseline (RE)" || true
    BASELINE_RE_DIR="$(find_run_dir "01_baseline_re_")"
fi

if [[ "${SKIP_OSS}" != "true" ]]; then
    PLATFORM="oss-sentinel" \
    PRIMARY_CONTAINER="redis-primary" \
    LOCUST_HOST="redis://localhost:6379" \
        run_scenario "scenarios/scripts/01_baseline.sh" "Baseline (OSS Sentinel)" || true
    BASELINE_OSS_DIR="$(find_run_dir "01_baseline_oss-sentinel_")"
fi

# ── Step 3: Run primary kill scenarios ─────────────────────────────────────
info "Step 3: Running primary kill scenarios..."

KILL_RE_DIR=""
KILL_OSS_DIR=""

if [[ "${SKIP_RE}" != "true" ]]; then
    PLATFORM="re" \
    PRIMARY_CONTAINER="re-node1" \
    LOCUST_HOST="redis://localhost:12000" \
    CANARY_HOST="localhost" \
    CANARY_PORT="12000" \
    CANARY_MODE="standalone" \
        run_scenario "scenarios/scripts/02_primary_kill.sh" "Primary Kill (RE)" || true
    KILL_RE_DIR="$(find_run_dir "02_primary_kill_re_")"
fi

if [[ "${SKIP_OSS}" != "true" ]]; then
    PLATFORM="oss-sentinel" \
    PRIMARY_CONTAINER="redis-primary" \
    LOCUST_HOST="redis://localhost:6379" \
    CANARY_HOST="localhost" \
    CANARY_PORT="6379" \
    CANARY_MODE="standalone" \
        run_scenario "scenarios/scripts/02_primary_kill.sh" "Primary Kill (OSS Sentinel)" || true
    KILL_OSS_DIR="$(find_run_dir "02_primary_kill_oss-sentinel_")"
fi

# ── Step 4: Export run summaries ───────────────────────────────────────────
info "Step 4: Exporting run summaries..."

export_summary "${BASELINE_RE_DIR}"
export_summary "${BASELINE_OSS_DIR}"
export_summary "${KILL_RE_DIR}"
export_summary "${KILL_OSS_DIR}"

# ── Step 5: Cross-run comparisons ──────────────────────────────────────────
info "Step 5: Running cross-run comparisons..."

# Baseline comparison: RE vs OSS
if [[ -n "${BASELINE_RE_DIR}" ]] && [[ -n "${BASELINE_OSS_DIR}" ]] \
   && [[ -f "${BASELINE_RE_DIR}/run_summary.json" ]] \
   && [[ -f "${BASELINE_OSS_DIR}/run_summary.json" ]]; then
    info "Comparing baselines: RE vs OSS Sentinel..."
    python3 -m tooling.compare_runs \
        "${BASELINE_RE_DIR}/run_summary.json" \
        "${BASELINE_OSS_DIR}/run_summary.json" \
        --format both \
        --output-dir "${DEMO_DIR}/comparison_baseline" \
        >> "${LOG_FILE}" 2>&1 || warn "Baseline comparison failed"
else
    warn "Skipping baseline comparison — summaries not available for both platforms"
fi

# Primary kill comparison: RE vs OSS
if [[ -n "${KILL_RE_DIR}" ]] && [[ -n "${KILL_OSS_DIR}" ]] \
   && [[ -f "${KILL_RE_DIR}/run_summary.json" ]] \
   && [[ -f "${KILL_OSS_DIR}/run_summary.json" ]]; then
    info "Comparing primary kill: RE vs OSS Sentinel..."
    python3 -m tooling.compare_runs \
        "${KILL_RE_DIR}/run_summary.json" \
        "${KILL_OSS_DIR}/run_summary.json" \
        --format both \
        --output-dir "${DEMO_DIR}/comparison_primary_kill" \
        >> "${LOG_FILE}" 2>&1 || warn "Primary kill comparison failed"
else
    warn "Skipping primary kill comparison — summaries not available for both platforms"
fi

# ── Step 6: RTO/RPO reports ───────────────────────────────────────────────
info "Step 6: Computing RTO/RPO from primary kill runs..."

if [[ -n "${KILL_RE_DIR}" ]] && [[ -d "${KILL_RE_DIR}" ]]; then
    info "RTO/RPO for RE primary kill..."
    python3 -m tooling.rto_rpo_report "${KILL_RE_DIR}" \
        --output "${DEMO_DIR}/rto_rpo_re.json" \
        >> "${LOG_FILE}" 2>&1 || warn "RTO/RPO report failed for RE"
fi

if [[ -n "${KILL_OSS_DIR}" ]] && [[ -d "${KILL_OSS_DIR}" ]]; then
    info "RTO/RPO for OSS Sentinel primary kill..."
    python3 -m tooling.rto_rpo_report "${KILL_OSS_DIR}" \
        --output "${DEMO_DIR}/rto_rpo_oss.json" \
        >> "${LOG_FILE}" 2>&1 || warn "RTO/RPO report failed for OSS"
fi

# ── Step 7: Assemble results ──────────────────────────────────────────────
info "Step 7: Assembling results into ${DEMO_DIR}..."

# Copy run summaries into the demo directory for easy access
for dir_var in BASELINE_RE_DIR BASELINE_OSS_DIR KILL_RE_DIR KILL_OSS_DIR; do
    dir_val="${!dir_var}"
    if [[ -n "${dir_val}" ]] && [[ -d "${dir_val}" ]]; then
        label="$(basename "${dir_val}")"
        cp -f "${dir_val}/run_summary.json" "${DEMO_DIR}/${label}_summary.json" 2>/dev/null || true
        cp -f "${dir_val}/run_summary.md" "${DEMO_DIR}/${label}_summary.md" 2>/dev/null || true
    fi
done

# Write a manifest of all run directories
cat > "${DEMO_DIR}/manifest.json" <<EOF
{
  "demo_timestamp": "${DEMO_TS}",
  "baseline_re": "${BASELINE_RE_DIR}",
  "baseline_oss": "${BASELINE_OSS_DIR}",
  "primary_kill_re": "${KILL_RE_DIR}",
  "primary_kill_oss": "${KILL_OSS_DIR}",
  "skip_re": "${SKIP_RE}",
  "skip_oss": "${SKIP_OSS}",
  "settings": {
    "baseline_duration": ${BASELINE_DURATION},
    "warmup_duration": ${WARMUP_DURATION},
    "post_recovery_duration": ${POST_RECOVERY_DURATION},
    "locust_users": ${LOCUST_USERS},
    "locust_spawn_rate": ${LOCUST_SPAWN_RATE}
  }
}
EOF

ok "Results assembled in ${DEMO_DIR}"

# ── Step 8: Assemble polished result pack ────────────────────────────────
info "Step 8: Assembling polished result pack..."
PYTHONPATH="${REPO_ROOT}" python3 "${REPO_ROOT}/tooling/assemble_result_pack.py" "${DEMO_DIR}" \
    >> "${LOG_FILE}" 2>&1 || warn "Result pack assembly failed (non-fatal)"

# ── Final summary ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║                    Demo Complete                            ║${NC}"
echo -e "${BOLD}╠══════════════════════════════════════════════════════════════╣${NC}"
if [[ -n "${BASELINE_RE_DIR}" ]]; then
    echo -e "║  Baseline (RE):           $(basename "${BASELINE_RE_DIR}")"
fi
if [[ -n "${BASELINE_OSS_DIR}" ]]; then
    echo -e "║  Baseline (OSS):          $(basename "${BASELINE_OSS_DIR}")"
fi
if [[ -n "${KILL_RE_DIR}" ]]; then
    echo -e "║  Primary Kill (RE):       $(basename "${KILL_RE_DIR}")"
fi
if [[ -n "${KILL_OSS_DIR}" ]]; then
    echo -e "║  Primary Kill (OSS):      $(basename "${KILL_OSS_DIR}")"
fi
echo -e "║"
echo -e "║  Demo results:            ${DEMO_DIR}"
echo -e "║  Orchestrator log:        ${LOG_FILE}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"

if [[ "${ALL_OK}" == "true" ]]; then
    ok "All scenarios completed successfully."
    exit 0
else
    fail "One or more scenarios failed — check ${LOG_FILE} for details."
    exit 1
fi

