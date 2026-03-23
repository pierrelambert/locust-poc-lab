#!/usr/bin/env bash
# k3d-setup.sh — Create a k3d cluster for the Locust POC Lab
#
# This cluster is sized to run both Redis Enterprise Operator (#2)
# and OSS Redis on k8s (#5) comparison paths.
#
# Requirements:
#   - Docker running
#   - k3d installed (https://k3d.io)
#   - kubectl installed
#
# Usage:
#   ./infra/scripts/k3d-setup.sh          # create cluster
#   ./infra/scripts/k3d-setup.sh delete    # tear down cluster

set -euo pipefail

CLUSTER_NAME="${K3D_CLUSTER_NAME:-locust-poc-lab}"
K3S_IMAGE="${K3S_IMAGE:-rancher/k3s:v1.29.4-k3s1}"
AGENTS="${K3D_AGENTS:-3}"
API_PORT="${K3D_API_PORT:-6550}"
REDIS_NODEPORT_START="${K3D_REDIS_NODEPORT_START:-30000}"
REDIS_NODEPORT_END="${K3D_REDIS_NODEPORT_END:-30100}"

log() { echo "[k3d-setup] $*"; }

check_prerequisites() {
    local missing=0
    for cmd in docker k3d kubectl; do
        if ! command -v "$cmd" &>/dev/null; then
            log "ERROR: $cmd is not installed"
            missing=1
        fi
    done
    if ! docker info &>/dev/null; then
        log "ERROR: Docker daemon is not running"
        missing=1
    fi
    if [[ $missing -ne 0 ]]; then
        log "Please install missing prerequisites and try again."
        exit 1
    fi
}

create_cluster() {
    if k3d cluster list 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        log "Cluster '$CLUSTER_NAME' already exists."
        log "Use '$0 delete' to remove it first, or set K3D_CLUSTER_NAME to use a different name."
        exit 1
    fi

    log "Creating k3d cluster '$CLUSTER_NAME' with $AGENTS agent nodes..."
    k3d cluster create "$CLUSTER_NAME" \
        --image "$K3S_IMAGE" \
        --agents "$AGENTS" \
        --api-port "$API_PORT" \
        -p "${REDIS_NODEPORT_START}-${REDIS_NODEPORT_END}:${REDIS_NODEPORT_START}-${REDIS_NODEPORT_END}@server:0" \
        --k3s-arg "--disable=traefik@server:0" \
        --wait

    log "Cluster created. Setting kubectl context..."
    kubectl config use-context "k3d-${CLUSTER_NAME}"

    log "Waiting for nodes to be ready..."
    kubectl wait --for=condition=Ready nodes --all --timeout=120s

    log "Creating namespaces for lab workloads..."
    kubectl create namespace redis-enterprise --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace redis-oss --dry-run=client -o yaml | kubectl apply -f -

    log ""
    log "Cluster is ready."
    log "  Nodes:      $(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
    log "  Namespaces: redis-enterprise, redis-oss"
    log "  Context:    k3d-${CLUSTER_NAME}"
    log ""
    log "Next steps:"
    log "  make k8s-re-up    # Deploy Redis Enterprise Operator"
    log "  make k8s-oss-up   # Deploy OSS Redis with Sentinel"
}

delete_cluster() {
    if ! k3d cluster list 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        log "Cluster '$CLUSTER_NAME' does not exist."
        exit 0
    fi

    log "Deleting k3d cluster '$CLUSTER_NAME'..."
    k3d cluster delete "$CLUSTER_NAME"
    log "Cluster deleted."
}

# --- Main ---
check_prerequisites

case "${1:-create}" in
    create)
        create_cluster
        ;;
    delete|destroy|down)
        delete_cluster
        ;;
    *)
        echo "Usage: $0 [create|delete]"
        exit 1
        ;;
esac

