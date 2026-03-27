# Start Here — Locust POC Lab Guides

Choose the lab guide that matches your deployment path.

---

## Lab Guides by Deployment Path

### Docker (Local Development)

**[SA Guided Lab](SA_GUIDED_LAB.md)** — 90-minute internal learning lab using Docker Compose.
Walk through topology behavior, failure events, and the dashboard story on your laptop.

- **Prerequisites:** Docker, Docker Compose, Python 3.10+
- **Platforms:** Redis Enterprise (3-node cluster) vs OSS Redis + Sentinel
- **Scenarios:** Steady-state baseline, primary process kill

### Kubernetes (k8s)

**[Kubernetes Comparison Lab](K8S_COMPARISON_LAB.md)** — 90-minute k8s comparison lab using k3d.
Deploy Redis Enterprise Operator and OSS Redis on a local k3d cluster, then run failover scenarios.

- **Prerequisites:** Docker, k3d, kubectl, Python 3.10+
- **Platforms:** Redis Enterprise Operator vs OSS Redis + Sentinel on k8s
- **Scenarios:** Steady-state baseline, primary pod kill

**[GKE Deployment Guide](GKE_DEPLOYMENT_GUIDE.md)** — Quick deploy plus step-by-step walkthrough for running the same k8s path on Google Kubernetes Engine.

- **Prerequisites:** `gcloud`, `kubectl`, Python 3.10+, active Google Cloud project
- **Platforms:** Redis Enterprise Operator vs OSS Redis + Sentinel on GKE
- **Scenarios:** Steady-state baseline, primary pod kill

### Bare-Metal / VMs

**[VM Comparison Lab](VM_COMPARISON_LAB.md)** — 90-minute comparison lab on dedicated VMs.
Install Redis natively on VMs and run the POC tooling via systemd services.

- **Prerequisites:** Two VMs (Ubuntu 20.04+ or RHEL/Rocky 8+), ≥4 CPUs, ≥16 GB RAM each
- **Platforms:** Redis Enterprise vs OSS Redis + Sentinel
- **Scenarios:** Steady-state baseline, primary process kill

---

## Supporting Guides

| Guide | Description |
|---|---|
| [Troubleshooting](TROUBLESHOOTING.md) | Common issues and fixes across all deployment paths |
| [Operator Effort Checklist](OPERATOR_EFFORT_CHECKLIST.md) | Operational complexity comparison checklist |
| [Offline Field Kit](OFFLINE_FIELD_KIT.md) | Running the lab in air-gapped environments |

## Templates

| Template | Description |
|---|---|
| [POC Charter](../templates/POC_CHARTER_TEMPLATE.md) | Define scope, success criteria, and timeline |
| [POC Scorecard](../templates/POC_SCORECARD_TEMPLATE.md) | Record and compare results across platforms |

## Reference Docs

| Document | Description |
|---|---|
| [POC Lab Execution Blueprint](../POC_LAB_EXECUTION_BLUEPRINT.md) | Full methodology and measurement framework |
| [Scenario Matrix](../SCENARIO_MATRIX.md) | All available failure scenarios |
| [Topology Matrix](../TOPOLOGY_MATRIX.md) | Supported Redis topologies |
| [Workload Catalog](../WORKLOAD_CATALOG.md) | Available Locust workload profiles |

