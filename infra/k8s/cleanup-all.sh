#!/usr/bin/env bash
# cleanup-all.sh — Tear down all k8s OSS comparison variants
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VARIANTS=(
    "oss-sentinel-bitnami"
    "oss-sentinel-opstree"
    "oss-cluster-bitnami"
    "oss-cluster-opstree"
)

echo "══════════════════════════════════════════"
echo "  K8s OSS — Cleanup All Variants"
echo "══════════════════════════════════════════"
echo ""

for variant in "${VARIANTS[@]}"; do
    TEARDOWN="${SCRIPT_DIR}/${variant}/teardown.sh"
    if [[ -x "${TEARDOWN}" ]] || [[ -f "${TEARDOWN}" ]]; then
        echo "→ ${variant}"
        bash "${TEARDOWN}" || true
    fi
done

echo ""
echo "✅ All variants cleaned up"

