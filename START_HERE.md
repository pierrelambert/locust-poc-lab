# Start Here

Welcome to the **Locust POC Lab** — a portable environment for running Redis resilience and performance comparisons.

Pick the path that matches your situation, then follow the linked guide.

---

## Which path is right for you?

```
┌─────────────────────────────────────────────────────────────┐
│                What are you trying to do?                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
      ┌─────────────────┼───────────────┬────────────────┐
      ▼                 ▼               ▼                ▼
 Quick demo         K8s demo        Customer POC      K8s demo
 on laptop          on laptop       on dedicated VM   on GKE
      │                 │               │                │
      ▼                 ▼               ▼                ▼
 FIRST_30_MIN       K8s path        Full guided       GKE practice
 (Docker)           (k3d)           lab on VM         environment
```

### Path A — Quick Demo on Your Laptop (Docker)

**Best for:** First look, internal demos, learning the lab.
**Time:** ~30 minutes.
**What you'll do:** Spin up OSS Redis + Sentinel in Docker, run a workload, kill the primary, watch failover on Grafana.

| Prerequisite | How to verify |
|---|---|
| Docker Desktop installed and running | `docker compose version` |
| Docker Desktop allocated ≥16 GB RAM | Docker Desktop → Settings → Resources |
| Python 3.10+ | `python3 --version` |
| Git clone of this repo | `ls Makefile` in repo root |

👉 **Go to [FIRST_30_MINUTES.md](FIRST_30_MINUTES.md)**

---

### Path B — Kubernetes Demo on Your Laptop (k3d)

**Best for:** Showing Redis Enterprise Operator vs. OSS on k8s, internal enablement.
**Time:** ~60 minutes.
**What you'll do:** Create a k3d cluster, deploy Redis Enterprise Operator and OSS Redis, run workloads, compare failover.

| Prerequisite | How to verify |
|---|---|
| Everything from Path A | See above |
| k3d installed | `k3d version` |
| kubectl installed | `kubectl version --client` |
| ≥16 GB RAM allocated to Docker | Docker Desktop → Settings → Resources |

👉 **Go to [docs/guides/SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md)** (start at Phase 1, use `make k3d-up` / `make k8s-re-up` / `make k8s-oss-up`)

---

### Path C — Customer VM POC (Full Guided Lab)

**Best for:** Running a real POC on a customer-provided or dedicated VM.
**Time:** 90 minutes (guided) or self-paced.
**What you'll do:** Run the complete 6-phase guided lab — baseline, primary kill, dashboard review, evidence export, scorecard.

| Prerequisite | How to verify |
|---|---|
| Everything from Path A | See above |
| VM with ≥16 GB RAM and ≥4 CPUs | `free -h` / `nproc` (Linux) or Docker Desktop settings (macOS) |
| Network access to pull Docker images | `docker pull redis:7` |

👉 **Go to [docs/guides/SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md)**

---

> **Note:** For GCE VM-based demos, Path C already works — just provision a GCE VM that meets the same sizing requirements and follow the same guided lab.

### Path D — GKE Practice Environment

**Best for:** Practicing the Kubernetes comparison flow on managed GKE instead of k3d or a customer cluster.**Time:** ~60–90 minutes plus cluster provisioning.**What you'll do:** Create a GKE practice cluster, configure `kubectl`, deploy the Redis Enterprise Operator and OSS Redis paths, then run the guided comparison flow.

| Prerequisite | How to verify |
| --- | --- |
| Everything from Path A | See above |
| gcloud CLI installed | gcloud version |
| GCP project with billing enabled | gcloud config get-value project, then confirm billing is enabled for that project in GCP |
| kubectl installed | kubectl version --client |

👉 **Go to **[**docs/guides/GKE_DEPLOYMENT_GUIDE.md**](docs/guides/GKE_DEPLOYMENT_GUIDE.md) (use `make gke-up` to create the cluster, `make gke-status` to verify it, and `make gke-down` when finished)

## Quick Setup (all paths)

```bash
git clone https://github.com/pierrelambert/locust-poc-lab.git
cd locust-poc-lab
make setup          # Install Python dependencies
make help           # Show all available Makefile targets
```

## What's in the box?

| Component | Description |
|---|---|
| **Infrastructure** | Docker Compose stacks for Redis Enterprise, OSS Sentinel, OSS Cluster; k8s manifests for RE Operator and OSS |
| **Workloads** | Locust load-test files simulating cache-read-heavy and session-mixed patterns |
| **Scenarios** | Scripted failure injection (primary kill, network partition) with automated measurement |
| **Observability** | Pre-configured Prometheus + Grafana with Redis and Locust dashboards |
| **Evidence export** | Automated JSON + Markdown run summaries for scorecard reporting |

## Key links

- [FIRST_30_MINUTES.md](FIRST_30_MINUTES.md) — Hands-on quickstart (30 min)
- [docs/guides/SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md) — Full 90-minute guided lab
- [docs/guides/GKE_DEPLOYMENT_GUIDE.md](docs/guides/GKE_DEPLOYMENT_GUIDE.md) — GKE practice environment setup and deployment flow
- [docs/guides/TROUBLESHOOTING.md](docs/guides/TROUBLESHOOTING.md) — Common issues and fixes
- [docs/templates/POC_SCORECARD_TEMPLATE.md](docs/templates/POC_SCORECARD_TEMPLATE.md) — Scorecard template
- [docs/templates/POC_CHARTER_TEMPLATE.md](docs/templates/POC_CHARTER_TEMPLATE.md) — POC charter template

