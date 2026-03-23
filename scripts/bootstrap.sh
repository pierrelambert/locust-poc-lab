#!/usr/bin/env bash
# bootstrap.sh — Hermetic bootstrap for the Locust POC Lab
#
# Detects OS, installs prerequisites, creates a pinned virtualenv,
# and validates the setup. Idempotent — safe to re-run.
#
# Supported: macOS (Homebrew), Ubuntu/Debian (apt), RHEL/CentOS (yum/dnf)
#
# Usage:
#   bash scripts/bootstrap.sh          # full bootstrap
#   bash scripts/bootstrap.sh --check  # validate only (no installs)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
PYTHON_MIN="3.10"
CHECK_ONLY=false

# ── Colours ───────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { printf "${GREEN}✔${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()  { printf "${RED}✘${NC} %s\n" "$*"; }
log()  { printf "  %s\n" "$*"; }

# ── OS Detection ──────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin) OS=macos; PKG=brew ;;
        Linux)
            if [ -f /etc/debian_version ]; then
                OS=debian; PKG=apt
            elif [ -f /etc/redhat-release ]; then
                OS=rhel
                if command -v dnf &>/dev/null; then PKG=dnf; else PKG=yum; fi
            else
                OS=linux; PKG=unknown
            fi ;;
        *) OS=unknown; PKG=unknown ;;
    esac
}

# ── Helpers ───────────────────────────────────────────────────────
has_cmd() { command -v "$1" &>/dev/null; }

python_version_ok() {
    local ver
    ver="$("$1" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)" || return 1
    printf '%s\n%s' "$PYTHON_MIN" "$ver" | sort -V -C
}

find_python() {
    for py in python3.12 python3.11 python3.10 python3; do
        if has_cmd "$py" && python_version_ok "$py"; then
            echo "$py"; return 0
        fi
    done
    return 1
}

install_pkg() {
    local name="$1"
    if $CHECK_ONLY; then err "$name not found (--check mode, skipping install)"; return 1; fi
    log "Installing $name via $PKG..."
    case "$PKG" in
        brew) brew install "$name" ;;
        apt)  sudo apt-get update -qq && sudo apt-get install -y -qq "$name" ;;
        dnf)  sudo dnf install -y -q "$name" ;;
        yum)  sudo yum install -y -q "$name" ;;
        *)    err "Cannot auto-install on this OS. Please install $name manually."; return 1 ;;
    esac
}

# ── Prerequisite Checks / Installs ───────────────────────────────
ensure_python() {
    if find_python &>/dev/null; then
        ok "Python $(find_python) found"
    else
        case "$PKG" in
            brew) install_pkg python@3.12 ;;
            apt)  install_pkg python3 && install_pkg python3-venv ;;
            dnf|yum) install_pkg python3 ;;
        esac
        find_python &>/dev/null || { err "Python ${PYTHON_MIN}+ required but not found"; exit 1; }
        ok "Python installed"
    fi
}

ensure_tool() {
    local cmd="$1" pkg="${2:-$1}"
    if has_cmd "$cmd"; then
        ok "$cmd found ($(command -v "$cmd"))"
    else
        install_pkg "$pkg" || { err "$cmd is required"; exit 1; }
        ok "$cmd installed"
    fi
}

ensure_k3d() {
    if has_cmd k3d; then
        ok "k3d found ($(k3d version 2>/dev/null | head -1))"
    else
        if $CHECK_ONLY; then err "k3d not found"; return 1; fi
        log "Installing k3d..."
        curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
        ok "k3d installed"
    fi
}

ensure_helm() {
    if has_cmd helm; then
        ok "helm found ($(helm version --short 2>/dev/null))"
    else
        if $CHECK_ONLY; then err "helm not found"; return 1; fi
        case "$PKG" in
            brew) brew install helm ;;
            *)    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash ;;
        esac
        ok "helm installed"
    fi
}

# ── Virtual Environment ──────────────────────────────────────────
setup_venv() {
    local py
    py="$(find_python)"
    if [ -f "${VENV_DIR}/bin/activate" ]; then
        ok "Virtual environment exists at ${VENV_DIR}"
    else
        log "Creating virtual environment..."
        "$py" -m venv "$VENV_DIR"
        ok "Virtual environment created"
    fi
    log "Installing pinned dependencies..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -r "${REPO_ROOT}/requirements.txt"
    ok "Python dependencies installed"
}

# ── Validation Summary ───────────────────────────────────────────
print_summary() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  Locust POC Lab — Bootstrap Summary"
    echo "═══════════════════════════════════════════"
    local py; py="$(find_python)"
    printf "  %-12s %s\n" "Python:" "$($py --version 2>&1)"
    printf "  %-12s %s\n" "Docker:" "$(docker --version 2>/dev/null || echo 'NOT FOUND')"
    printf "  %-12s %s\n" "kubectl:" "$(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null | head -1 || echo 'NOT FOUND')"
    printf "  %-12s %s\n" "k3d:" "$(k3d version 2>/dev/null | head -1 || echo 'NOT FOUND')"
    printf "  %-12s %s\n" "helm:" "$(helm version --short 2>/dev/null || echo 'NOT FOUND')"
    printf "  %-12s %s\n" "venv:" "${VENV_DIR}"
    echo "═══════════════════════════════════════════"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

detect_os
echo "Detected OS: ${OS} (package manager: ${PKG})"
echo ""

ensure_python
ensure_tool docker
ensure_tool kubectl
ensure_k3d
ensure_helm

if ! $CHECK_ONLY; then
    setup_venv
fi

print_summary
ok "Bootstrap complete."

