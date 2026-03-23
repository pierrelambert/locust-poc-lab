#!/usr/bin/env bash
# Locust POC Lab — VM Teardown Script
# Stops services, removes application files.  Does NOT remove system packages.
set -euo pipefail

APP_NAME="locust-poc"
APP_USER="locust-poc"
APP_DIR="/opt/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

if [[ "$EUID" -ne 0 ]]; then
    error "Please run as root or with sudo"
    exit 1
fi

# ── Stop and disable services ───────────────────────────────────────
info "Stopping services ..."
systemctl stop locust-poc.service redis-exporter.service 2>/dev/null || true
systemctl disable locust-poc.service redis-exporter.service 2>/dev/null || true

info "Removing service unit files ..."
rm -f /etc/systemd/system/locust-poc.service
rm -f /etc/systemd/system/redis-exporter.service
systemctl daemon-reload

# ── Remove application files ────────────────────────────────────────
info "Removing application directory ${APP_DIR} ..."
rm -rf "${APP_DIR}"

info "Removing log directory ${LOG_DIR} ..."
rm -rf "${LOG_DIR}"

# ── Optionally remove config ────────────────────────────────────────
if [[ "${1:-}" == "--purge" ]]; then
    info "Purging configuration directory ${CONFIG_DIR} ..."
    rm -rf "${CONFIG_DIR}"
    info "Removing user ${APP_USER} ..."
    userdel -r "${APP_USER}" 2>/dev/null || true
    info "Removing redis_exporter binary ..."
    rm -f /usr/local/bin/redis_exporter
else
    warn "Config preserved at ${CONFIG_DIR} (use --purge to remove)"
    warn "User ${APP_USER} preserved (use --purge to remove)"
fi

info "Teardown complete."

