#!/usr/bin/env bash
# cleanup_all.sh — Tear down all lab resources
#
# Stops and removes:
#   1. All Docker Compose stacks (RE cluster, OSS Sentinel, OSS Cluster, Observability)
#   2. Kubernetes resources (RE Operator, OSS on k8s)
#   3. k3d cluster
#   4. Results and temporary files
#
# Usage:
#   ./infra/scripts/cleanup_all.sh
#   make cleanup-all

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE="docker compose"

log()  { echo "[cleanup] $*"; }
warn() { echo "[cleanup] ⚠️  $*"; }
ok()   { echo "[cleanup] ✅ $*"; }

# ── 1. Docker Compose stacks ────────────────────────────────────────
log "Tearing down Docker Compose stacks..."

STACKS=(
    "re-cluster:infra/docker/re-cluster/docker-compose.yml"
    "oss-sentinel:infra/docker/oss-sentinel/docker-compose.yml"
    "oss-cluster:infra/docker/oss-cluster/docker-compose.yml"
    "obs-stack:observability/docker-compose.yml"
)

for entry in "${STACKS[@]}"; do
    project="${entry%%:*}"
    file="${entry#*:}"
    compose_file="$REPO_ROOT/$file"
    if [[ -f "$compose_file" ]]; then
        log "  Stopping $project..."
        $COMPOSE -f "$compose_file" -p "$project" down --volumes --remove-orphans 2>/dev/null || true
        ok "  $project stopped"
    else
        warn "  Compose file not found: $file"
    fi
done

# ── 2. Kubernetes resources ─────────────────────────────────────────
if command -v kubectl &>/dev/null; then
    log "Tearing down Kubernetes resources..."

    RE_NAMESPACE="${RE_NAMESPACE:-redis-enterprise}"
    OSS_NAMESPACE="${OSS_NAMESPACE:-redis-oss}"

    # OSS Redis on k8s
    for manifest in \
        "$REPO_ROOT/infra/k8s/oss-k8s/sentinel-deployment.yaml" \
        "$REPO_ROOT/infra/k8s/oss-k8s/redis-statefulset.yaml" \
        "$REPO_ROOT/infra/k8s/oss-k8s/configmap.yaml" \
        "$REPO_ROOT/infra/k8s/oss-k8s/namespace.yaml"; do
        if [[ -f "$manifest" ]]; then
            kubectl delete -f "$manifest" --ignore-not-found 2>/dev/null || true
        fi
    done
    ok "  OSS k8s resources removed"

    # Redis Enterprise on k8s
    for manifest in \
        "$REPO_ROOT/infra/k8s/re-operator/redb.yaml" \
        "$REPO_ROOT/infra/k8s/re-operator/rec.yaml" \
        "$REPO_ROOT/infra/k8s/re-operator/operator.yaml" \
        "$REPO_ROOT/infra/k8s/re-operator/namespace.yaml"; do
        if [[ -f "$manifest" ]]; then
            kubectl delete -f "$manifest" --ignore-not-found 2>/dev/null || true
        fi
    done
    ok "  RE k8s resources removed"
else
    warn "kubectl not found — skipping Kubernetes cleanup"
fi

# ── 3. k3d cluster ──────────────────────────────────────────────────
if command -v k3d &>/dev/null; then
    log "Deleting k3d cluster..."
    K3D_CLUSTER="${K3D_CLUSTER_NAME:-locust-poc-lab}"
    k3d cluster delete "$K3D_CLUSTER" 2>/dev/null || true
    ok "  k3d cluster '$K3D_CLUSTER' deleted"
else
    warn "k3d not found — skipping k3d cleanup"
fi

# ── 4. Results and temporary files ──────────────────────────────────
log "Cleaning results and caches..."
find "$REPO_ROOT" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT" -type f -name '*.pyc' -delete 2>/dev/null || true

if [[ -d "$REPO_ROOT/results" ]]; then
    # Only remove contents, keep the directory
    find "$REPO_ROOT/results" -mindepth 1 -delete 2>/dev/null || true
    ok "  Results directory cleaned"
fi

ok "Caches cleaned"

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Full cleanup complete"
echo "═══════════════════════════════════════"

