#!/usr/bin/env bash
# validate_all.sh — Validate all project artifacts
#
# Checks:
#   1. Docker Compose files parse correctly
#   2. Python files import cleanly
#   3. Bash scripts pass syntax check
#   4. YAML files are valid
#   5. Makefile targets exist
#
# Usage:
#   ./infra/scripts/validate_all.sh
#   make validate

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0
FAIL=0
ERRORS=()

pass() { ((PASS++)); echo "  ✅ $1"; }
fail() { ((FAIL++)); ERRORS+=("$1"); echo "  ❌ $1"; }

# ── 1. Docker Compose files ──────────────────────────────────────────
echo ""
echo "═══ Checking Docker Compose files ═══"
while IFS= read -r -d '' f; do
    if docker compose -f "$f" config --quiet 2>/dev/null; then
        pass "$f"
    else
        fail "Docker Compose parse error: $f"
    fi
done < <(find "$REPO_ROOT" -name 'docker-compose.yml' -print0)

# ── 2. Python files import cleanly ───────────────────────────────────
echo ""
echo "═══ Checking Python files (syntax) ═══"
while IFS= read -r -d '' f; do
    if python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
        pass "$f"
    else
        fail "Python syntax error: $f"
    fi
done < <(find "$REPO_ROOT" -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.venv/*' -print0)

# ── 3. Bash scripts pass syntax check ───────────────────────────────
echo ""
echo "═══ Checking Bash scripts (syntax) ═══"
while IFS= read -r -d '' f; do
    if bash -n "$f" 2>/dev/null; then
        pass "$f"
    else
        fail "Bash syntax error: $f"
    fi
done < <(find "$REPO_ROOT" -name '*.sh' -print0)

# ── 4. YAML files are valid ─────────────────────────────────────────
echo ""
echo "═══ Checking YAML files ═══"
if command -v python3 &>/dev/null; then
    while IFS= read -r -d '' f; do
        if python3 -c "
import yaml, sys
try:
    with open('$f') as fh:
        yaml.safe_load(fh)
except Exception as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
            pass "$f"
        else
            fail "YAML parse error: $f"
        fi
    done < <(find "$REPO_ROOT" \( -name '*.yml' -o -name '*.yaml' \) \
        -not -path '*/__pycache__/*' -not -path '*/.venv/*' -print0)
else
    echo "  ⚠️  python3 not found — skipping YAML validation"
fi

# ── 5. Makefile targets exist ────────────────────────────────────────
echo ""
echo "═══ Checking Makefile targets ═══"
MAKEFILE="$REPO_ROOT/Makefile"
if [[ -f "$MAKEFILE" ]]; then
    # Verify key targets are defined
    EXPECTED_TARGETS=(
        help setup lint clean export-summary
        re-up re-down re-status
        oss-sentinel-up oss-sentinel-down oss-sentinel-status
        oss-cluster-up oss-cluster-down oss-cluster-status
        vm-up vm-down vm-status
        k3d-up k3d-down
        k8s-re-up k8s-re-down k8s-re-status
        k8s-oss-up k8s-oss-down k8s-oss-status
        k8s-up k8s-down k8s-status
        obs-up obs-down obs-status
        validate cleanup-all
    )
    for target in "${EXPECTED_TARGETS[@]}"; do
        if grep -qE "^${target}:" "$MAKEFILE"; then
            pass "Makefile target: $target"
        else
            fail "Missing Makefile target: $target"
        fi
    done
else
    fail "Makefile not found at $MAKEFILE"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "  Failures:"
    for err in "${ERRORS[@]}"; do
        echo "    • $err"
    done
    echo ""
    echo "  ❌ VALIDATION FAILED"
    echo "═══════════════════════════════════════"
    exit 1
else
    echo ""
    echo "  ✅ ALL CHECKS PASSED"
    echo "═══════════════════════════════════════"
    exit 0
fi

