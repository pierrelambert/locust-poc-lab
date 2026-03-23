#!/usr/bin/env bash
# run-k8s-comparison.sh — Deploy all OSS k8s variants, run failover tests, collect results
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results/k8s-comparison}"
mkdir -p "${RESULTS_DIR}"

VARIANTS=(
    "oss-sentinel-bitnami"
    "oss-sentinel-opstree"
    "oss-cluster-bitnami"
    "oss-cluster-opstree"
)

echo "══════════════════════════════════════════"
echo "  K8s OSS Redis — Full Comparison Run"
echo "══════════════════════════════════════════"
echo ""
echo "Variants: ${VARIANTS[*]}"
echo "Results:  ${RESULTS_DIR}"
echo ""

PASS=0; FAIL=0

for variant in "${VARIANTS[@]}"; do
    VARIANT_DIR="${SCRIPT_DIR}/${variant}"
    echo "────────────────────────────────────────"
    echo "  ▶ ${variant}"
    echo "────────────────────────────────────────"

    # Deploy
    if bash "${VARIANT_DIR}/deploy.sh"; then
        echo ""
        # Failover test
        if bash "${VARIANT_DIR}/test-failover.sh"; then
            PASS=$((PASS + 1))
        else
            echo "⚠️  test-failover failed for ${variant}"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "⚠️  deploy failed for ${variant}"
        FAIL=$((FAIL + 1))
    fi

    echo ""
done

echo "══════════════════════════════════════════"
echo "  Summary"
echo "══════════════════════════════════════════"
echo "  Passed: ${PASS} / ${#VARIANTS[@]}"
echo "  Failed: ${FAIL} / ${#VARIANTS[@]}"
echo "  Results directory: ${RESULTS_DIR}"
echo ""

# Print collected JSON results
echo "  Failover times:"
for f in "${RESULTS_DIR}"/*-failover.json; do
    [[ -f "$f" ]] || continue
    name=$(basename "$f" -failover.json)
    secs=$(grep failover_seconds "$f" | grep -o '[0-9]*' | head -1)
    printf "    %-25s %ss\n" "${name}" "${secs}"
done
echo ""
echo "To tear down everything:  bash ${SCRIPT_DIR}/cleanup-all.sh"

