#!/usr/bin/env bash
# gke-setup.sh — Create or delete a practice GKE cluster for the Locust POC Lab
#
# Requirements:
#   - gcloud installed
#   - kubectl installed
#   - authenticated gcloud user account
#   - active gcloud project configured
#
# Usage:
#   ./infra/scripts/gke-setup.sh create
#   ./infra/scripts/gke-setup.sh delete
#   ./infra/scripts/gke-setup.sh status

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

log() { echo "[gke-setup] $*"; }
error() { echo "[gke-setup] ERROR: $*" >&2; }

resolve_path() {
    local path="$1"
    if [[ "$path" == /* ]]; then
        echo "$path"
    else
        echo "${REPO_ROOT}/${path}"
    fi
}

ENV_FILE="$(resolve_path "${GKE_ENV_FILE:-infra/gke/environment}")"

load_environment() {
    if [[ -f "${ENV_FILE}" ]]; then
        log "Loading configuration from ${ENV_FILE}"
        set -a
        # shellcheck source=/dev/null
        source "${ENV_FILE}"
        set +a
    fi
}

configure_defaults() {
    CLUSTER_NAME="${GKE_CLUSTER_NAME:-locust-poc-lab}"
    GKE_REGION="${GKE_REGION:-}"
    if [[ -n "${GKE_REGION}" ]]; then
        GKE_ZONE="${GKE_ZONE:-}"
    else
        GKE_ZONE="${GKE_ZONE:-us-central1-a}"
    fi
    GKE_NODE_COUNT="${GKE_NODE_COUNT:-3}"
    GKE_MACHINE_TYPE="${GKE_MACHINE_TYPE:-e2-standard-4}"
    GKE_DISK_SIZE_GB="${GKE_DISK_SIZE_GB:-100}"
    GKE_DISK_TYPE="${GKE_DISK_TYPE:-pd-balanced}"
    GKE_RELEASE_CHANNEL="${GKE_RELEASE_CHANNEL:-regular}"
    GKE_NETWORK="${GKE_NETWORK:-default}"
    GKE_SUBNETWORK="${GKE_SUBNETWORK:-default}"
}

configure_location() {
    if [[ -n "${GKE_ZONE}" && -n "${GKE_REGION}" ]]; then
        error "Set only one of GKE_ZONE or GKE_REGION, not both."
        exit 1
    fi

    if [[ -n "${GKE_REGION}" ]]; then
        GKE_LOCATION_ARGS=(--region "${GKE_REGION}")
        LOCATION_DESC="region ${GKE_REGION}"
    else
        GKE_LOCATION_ARGS=(--zone "${GKE_ZONE}")
        LOCATION_DESC="zone ${GKE_ZONE}"
    fi
}

check_prerequisites() {
    local missing=0
    for cmd in gcloud kubectl; do
        if ! command -v "$cmd" &>/dev/null; then
            error "$cmd is not installed"
            missing=1
        fi
    done

    ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1 || true)"
    if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
        error "No active gcloud account found. Run 'gcloud auth login' and try again."
        missing=1
    fi

    PROJECT_ID="$(gcloud config get-value project 2>/dev/null | tr -d '\r' || true)"
    if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
        error "No active gcloud project is set. Run 'gcloud config set project <PROJECT_ID>' and try again."
        missing=1
    fi

    if [[ ${missing} -ne 0 ]]; then
        log "Please install the missing prerequisites and ensure gcloud auth/project are configured."
        exit 1
    fi
}

cluster_exists() {
    gcloud container clusters describe "${CLUSTER_NAME}" \
        "${GKE_LOCATION_ARGS[@]}" \
        --project "${PROJECT_ID}" \
        --format='value(name)' >/dev/null 2>&1
}

configure_kubectl() {
    log "Fetching kubectl credentials for '${CLUSTER_NAME}'..."
    gcloud container clusters get-credentials "${CLUSTER_NAME}" \
        "${GKE_LOCATION_ARGS[@]}" \
        --project "${PROJECT_ID}"
}

create_namespaces() {
    log "Creating namespaces for lab workloads..."
    kubectl create namespace redis-enterprise --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace redis-oss --dry-run=client -o yaml | kubectl apply -f -
}

create_cluster() {
    if cluster_exists; then
        log "Cluster '${CLUSTER_NAME}' already exists in ${LOCATION_DESC}."
        log "Use '$0 delete' to remove it first, or set GKE_CLUSTER_NAME to use a different name."
        exit 1
    fi

    log "Creating GKE cluster '${CLUSTER_NAME}' in ${LOCATION_DESC} for project '${PROJECT_ID}'..."
    gcloud container clusters create "${CLUSTER_NAME}" \
        "${GKE_LOCATION_ARGS[@]}" \
        --project "${PROJECT_ID}" \
        --machine-type "${GKE_MACHINE_TYPE}" \
        --num-nodes "${GKE_NODE_COUNT}" \
        --disk-type "${GKE_DISK_TYPE}" \
        --disk-size "${GKE_DISK_SIZE_GB}" \
        --release-channel "${GKE_RELEASE_CHANNEL}" \
        --network "${GKE_NETWORK}" \
        --subnetwork "${GKE_SUBNETWORK}" \
        --enable-ip-alias \
        --enable-autorepair \
        --enable-autoupgrade \
        --quiet

    configure_kubectl
    log "Waiting for nodes to be ready..."
    kubectl wait --for=condition=Ready nodes --all --timeout=300s
    create_namespaces

    log ""
    log "Cluster is ready."
    log "  Project:    ${PROJECT_ID}"
    log "  Location:   ${LOCATION_DESC}"
    log "  Nodes:      $(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
    log "  Context:    $(kubectl config current-context)"
    log "  Namespaces: redis-enterprise, redis-oss"
    log ""
    log "Next steps:"
    log "  make k8s-re-up    # Deploy Redis Enterprise Operator"
    log "  make k8s-oss-up   # Deploy OSS Redis with Sentinel"
}

delete_cluster() {
    if ! cluster_exists; then
        log "Cluster '${CLUSTER_NAME}' does not exist in ${LOCATION_DESC}."
        exit 0
    fi

    log "Deleting GKE cluster '${CLUSTER_NAME}' from ${LOCATION_DESC}..."
    gcloud container clusters delete "${CLUSTER_NAME}" \
        "${GKE_LOCATION_ARGS[@]}" \
        --project "${PROJECT_ID}" \
        --quiet
    log "Cluster deleted."
}

status_cluster() {
    if ! cluster_exists; then
        log "Cluster '${CLUSTER_NAME}' does not exist in ${LOCATION_DESC}."
        exit 0
    fi

    gcloud container clusters describe "${CLUSTER_NAME}" \
        "${GKE_LOCATION_ARGS[@]}" \
        --project "${PROJECT_ID}" \
        --format='table(name,status,currentMasterVersion,currentNodeVersion,location,resourceLabels)'
}

load_environment
configure_defaults
configure_location
check_prerequisites

case "${1:-create}" in
    create)
        create_cluster
        ;;
    delete|destroy|down)
        delete_cluster
        ;;
    status)
        status_cluster
        ;;
    *)
        echo "Usage: $0 [create|delete|status]"
        exit 1
        ;;
esac