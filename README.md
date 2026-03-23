# Locust POC Lab

<!-- CI badge placeholder — will be added by CI pipeline setup -->

A portable, repeatable lab environment for running Redis Proof-of-Concept resilience and performance tests using [Locust](https://locust.io/).

Compare Redis Enterprise vs. OSS Redis (Sentinel / Cluster) across failover speed, client impact, and operational complexity — with automated evidence collection for POC scorecards.

---

## Getting Started

**New here?** → **[START_HERE.md](START_HERE.md)** picks the right path for you.

**Want to see it work in 30 minutes?** → **[FIRST_30_MINUTES.md](FIRST_30_MINUTES.md)** walks you through a complete demo.

### Quick setup

```bash
git clone https://github.com/pierrelambert/locust-poc-lab.git
cd locust-poc-lab
make setup          # Install Python dependencies
make help           # Show all available Makefile targets
```

### Prerequisites

| Requirement | Minimum |
|---|---|
| Docker Desktop | Installed and running |
| Docker memory allocation | ≥16 GB |
| Python | 3.10+ |
| Git | Any recent version |

For Kubernetes paths, you also need `k3d` and `kubectl`.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Locust POC Lab                           │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  Workloads   │  Scenarios   │    Infra     │   Observability    │
│              │              │              │                    │
│  Locust      │  Baseline    │  Docker:     │  Prometheus        │
│  load tests  │  Primary     │   RE Cluster │  Grafana           │
│  (cache,     │   kill       │   OSS Sent.  │  Redis Exporter    │
│   session)   │  (more TBD)  │   OSS Clust. │  Locust Exporter   │
│              │              │              │                    │
│              │              │  k8s:        │  Evidence export   │
│              │              │   RE Operator│  (JSON + Markdown) │
│              │              │   OSS on k8s │                    │
└──────────────┴──────────────┴──────────────┴────────────────────┘
```

**How it works:**
1. **Start infrastructure** — spin up Redis stacks via Docker Compose or k8s manifests.
2. **Run workloads** — Locust generates realistic traffic patterns (cache reads, session writes).
3. **Inject failures** — scripted scenarios kill primaries, partition networks, etc.
4. **Observe** — Grafana dashboards show throughput, latency, errors, and recovery in real time.
5. **Export evidence** — automated summaries feed directly into POC scorecards.

---

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `docs/` | Principles, blueprint, guides |
| `docs/templates/` | Charter and scorecard templates |
| `docs/guides/` | SA-facing guided labs and runbooks |
| `infra/docker/` | Docker Compose stacks (RE cluster, OSS Sentinel, OSS Cluster) |
| `infra/k8s/` | Kubernetes manifests (RE Operator, OSS on k8s) |
| `infra/scripts/` | Shared setup/teardown helpers |
| `workloads/locustfiles/` | Locust test files |
| `workloads/lib/` | Shared Python helpers (connections, data seeding) |
| `workloads/profiles/` | Workload profile configs (YAML/JSON) |
| `scenarios/scripts/` | Failure injection scripts (kill, partition, upgrade) |
| `scenarios/runbooks/` | Step-by-step scenario runbooks |
| `observability/grafana/` | Grafana dashboard JSON exports |
| `observability/prometheus/` | Prometheus config and rules |
| `observability/exporters/` | Evidence export scripts |
| `results/` | Run results (gitignored) |

---

## Key Documentation

| Document | Description |
|---|---|
| [START_HERE.md](START_HERE.md) | Decision tree — pick your path |
| [FIRST_30_MINUTES.md](FIRST_30_MINUTES.md) | Hands-on quickstart (30 min) |
| [docs/guides/SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md) | Full 90-minute guided lab |
| [docs/guides/TROUBLESHOOTING.md](docs/guides/TROUBLESHOOTING.md) | Common issues and fixes |
| [docs/templates/POC_SCORECARD_TEMPLATE.md](docs/templates/POC_SCORECARD_TEMPLATE.md) | Scorecard template |
| [docs/templates/POC_CHARTER_TEMPLATE.md](docs/templates/POC_CHARTER_TEMPLATE.md) | POC charter template |
