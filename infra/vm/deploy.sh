#!/usr/bin/env bash
# Locust POC Lab — VM Deployment Script
# Supports Ubuntu 20.04+ and RHEL/Rocky 8+.  Idempotent — safe to re-run.
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
APP_NAME="locust-poc"
APP_USER="locust-poc"
APP_DIR="/opt/${APP_NAME}"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="/var/log/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Pre-flight ───────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
    error "Please run as root or with sudo"
    exit 1
fi

# ── Detect package manager ───────────────────────────────────────────
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    else
        error "Unsupported OS — need apt-get, dnf, or yum"
        exit 1
    fi
    info "Detected package manager: ${PKG_MGR}"
}

install_system_deps() {
    local pkgs=(python3 python3-pip curl git)
    case "${PKG_MGR}" in
        apt)
            pkgs+=(python3-venv)
            apt-get update -qq
            apt-get install -y -qq "${pkgs[@]}"
            ;;
        dnf|yum)
            "${PKG_MGR}" install -y -q "${pkgs[@]}"
            ;;
    esac
    info "System dependencies installed"
}

# ── Create application user ─────────────────────────────────────────
create_user() {
    if id "${APP_USER}" &>/dev/null; then
        info "User ${APP_USER} already exists"
    else
        useradd -r -s /usr/sbin/nologin -d "${APP_DIR}" -m "${APP_USER}"
        info "Created user ${APP_USER}"
    fi
}

# ── Create directories ──────────────────────────────────────────────
create_dirs() {
    mkdir -p "${APP_DIR}" "${LOG_DIR}" "${CONFIG_DIR}" "${APP_DIR}/certs"
    info "Directories created"
}

# ── Copy application files ──────────────────────────────────────────
copy_files() {
    info "Copying application files from ${REPO_ROOT} ..."
    for dir in workloads observability scenarios; do
        if [[ -d "${REPO_ROOT}/${dir}" ]]; then
            cp -a "${REPO_ROOT}/${dir}" "${APP_DIR}/"
        fi
    done
    cp -f "${REPO_ROOT}/requirements.txt" "${APP_DIR}/"
    # Copy environment template if config not yet present
    if [[ ! -f "${CONFIG_DIR}/environment" ]]; then
        cp "${REPO_ROOT}/infra/vm/environment.example" "${CONFIG_DIR}/environment"
        info "Installed default environment file — edit ${CONFIG_DIR}/environment"
    else
        info "Environment file already exists — skipping"
    fi
}

# ── Python virtual environment ──────────────────────────────────────
setup_venv() {
    if [[ ! -d "${VENV_DIR}" ]]; then
        python3 -m venv "${VENV_DIR}"
        info "Virtual environment created"
    else
        info "Virtual environment already exists"
    fi
    "${VENV_DIR}/bin/pip" install --upgrade -q pip
    "${VENV_DIR}/bin/pip" install -q -r "${APP_DIR}/requirements.txt"
    info "Python dependencies installed"
}

# ── Install redis_exporter binary ───────────────────────────────────
install_redis_exporter() {
    if command -v redis_exporter &>/dev/null; then
        info "redis_exporter already installed"
        return
    fi
    local version="1.62.0"
    local arch
    arch=$(uname -m)
    case "${arch}" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
    esac
    local url="https://github.com/oliver006/redis_exporter/releases/download/v${version}/redis_exporter-v${version}.linux-${arch}.tar.gz"
    info "Downloading redis_exporter v${version} ..."
    curl -sL "${url}" | tar xz -C /tmp
    install -m 0755 "/tmp/redis_exporter-v${version}.linux-${arch}/redis_exporter" /usr/local/bin/redis_exporter
    rm -rf "/tmp/redis_exporter-v${version}.linux-${arch}"
    info "redis_exporter installed to /usr/local/bin/redis_exporter"
}

# ── Install systemd services ────────────────────────────────────────
install_services() {
    cp "${REPO_ROOT}/infra/vm/systemd/"*.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable locust-poc.service redis-exporter.service
    info "Systemd services installed and enabled"
}

# ── Set ownership ───────────────────────────────────────────────────
fix_permissions() {
    chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" "${LOG_DIR}" "${CONFIG_DIR}"
}

# ── Start services ──────────────────────────────────────────────────
start_services() {
    systemctl restart locust-poc.service
    systemctl restart redis-exporter.service
    info "Services started"
}

# ── Main ─────────────────────────────────────────────────────────────
main() {
    info "Starting ${APP_NAME} deployment ..."
    detect_pkg_manager
    install_system_deps
    create_user
    create_dirs
    copy_files
    setup_venv
    install_redis_exporter
    install_services
    fix_permissions
    start_services
    echo ""
    info "Deployment complete!"
    info "Locust UI:        http://$(hostname -I | awk '{print $1}'):8089"
    info "Redis Exporter:   http://$(hostname -I | awk '{print $1}'):9121/metrics"
    info "Logs:             ${LOG_DIR}/"
    info "Config:           ${CONFIG_DIR}/environment"
    info ""
    info "Next steps:"
    info "  1. Edit ${CONFIG_DIR}/environment with your Redis connection details"
    info "  2. sudo systemctl restart locust-poc redis-exporter"
    info "  3. sudo bash ${REPO_ROOT}/infra/vm/verify.sh"
}

main "$@"

