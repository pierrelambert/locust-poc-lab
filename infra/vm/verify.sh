#!/usr/bin/env bash
# Locust POC Lab — VM Verification Script
# Checks that all services are running and endpoints are reachable.
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
PASS=0; FAIL=0

check() {
    local label="$1"; shift
    if "$@" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${label}"
        ((PASS++))
    else
        echo -e "  ${RED}✗${NC} ${label}"
        ((FAIL++))
    fi
}

echo "Locust POC Lab — VM Verification"
echo "================================"
echo ""

# ── Systemd services ────────────────────────────────────────────────
echo "Systemd services:"
check "locust-poc.service is active"    systemctl is-active --quiet locust-poc.service
check "redis-exporter.service is active" systemctl is-active --quiet redis-exporter.service

# ── Redis connectivity ──────────────────────────────────────────────
echo ""
echo "Redis connectivity:"
# Source environment for REDIS_HOST if available
REDIS_CLI_HOST="localhost"
REDIS_CLI_PORT="6379"
if [[ -f /etc/locust-poc/environment ]]; then
    # shellcheck source=/dev/null
    source /etc/locust-poc/environment 2>/dev/null || true
    # Extract host/port from REDIS_HOST url if set
    if [[ "${REDIS_HOST:-}" =~ ://([^:]+):([0-9]+) ]]; then
        REDIS_CLI_HOST="${BASH_REMATCH[1]}"
        REDIS_CLI_PORT="${BASH_REMATCH[2]}"
    fi
fi
check "Redis PING responds PONG" redis-cli -h "${REDIS_CLI_HOST}" -p "${REDIS_CLI_PORT}" ping

# ── HTTP endpoints ──────────────────────────────────────────────────
echo ""
echo "HTTP endpoints:"
LOCUST_PORT="${LOCUST_WEB_PORT:-8089}"
EXPORTER_PORT="${REDIS_EXPORTER_PORT:-9121}"
check "Locust web UI (port ${LOCUST_PORT})"       curl -sf "http://localhost:${LOCUST_PORT}/"
check "Redis Exporter metrics (port ${EXPORTER_PORT})" curl -sf "http://localhost:${EXPORTER_PORT}/metrics"

# ── Virtual environment ─────────────────────────────────────────────
echo ""
echo "Application:"
check "Python venv exists"          test -x /opt/locust-poc/venv/bin/python
check "Locust binary in venv"       test -x /opt/locust-poc/venv/bin/locust
check "Workloads directory exists"  test -d /opt/locust-poc/workloads

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "================================"
echo -e "Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
if [[ "${FAIL}" -gt 0 ]]; then
    echo "Some checks failed — review output above."
    exit 1
fi
echo "All checks passed."

