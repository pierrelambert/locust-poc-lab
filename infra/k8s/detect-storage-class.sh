#!/usr/bin/env bash
# detect-storage-class.sh — Detect the appropriate StorageClass for the k8s cluster
#
# Prints the StorageClass name to stdout.  Used by variant deploy scripts.
set -euo pipefail

# Try the annotated default first
DEFAULT_SC=$(kubectl get storageclass \
    -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}' 2>/dev/null || true)

if [[ -n "${DEFAULT_SC}" ]]; then
    echo "${DEFAULT_SC}"
    exit 0
fi

# Fallback: well-known names
for sc in standard-rwo standard local-path; do
    if kubectl get storageclass "${sc}" &>/dev/null; then
        echo "${sc}"
        exit 0
    fi
done

# Last resort: first available
FIRST_SC=$(kubectl get storageclass -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "${FIRST_SC}" ]]; then
    echo "${FIRST_SC}"
    exit 0
fi

echo >&2 "ERROR: No StorageClass found in the cluster"
exit 1

