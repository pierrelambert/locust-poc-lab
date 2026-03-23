# SA Guided Lab — Motion A (90-Minute Internal Learning Lab)

**Purpose:** Onboard new SAs by walking through topology behavior, failure events, and the dashboard story.
**Output:** A completed guided lab run and one sample scorecard.
**Time budget:** 90 minutes total.
**Source:** [POC Lab Execution Blueprint](../POC_LAB_EXECUTION_BLUEPRINT.md), Motion A.

---

## Prerequisites

| Requirement | How to verify |
|---|---|
| Docker and Docker Compose installed | `docker compose version` |
| Python 3.10+ | `python3 --version` |
| Git clone of this repo | `git status` in repo root |
| ~8 GB free RAM (for all containers) | `docker info` |

---

## Phase 1 — Setup (15 minutes)

### 1.1 Install Python dependencies

```bash
make setup
```

### 1.2 Start the Redis Enterprise cluster

```bash
make re-up
make re-status          # Confirm 3 containers running
```

### 1.3 Start the OSS Redis Sentinel stack

```bash
make oss-sentinel-up
make oss-sentinel-status  # Confirm 1 primary + 2 replicas + 3 sentinels
```

### 1.4 Start the observability stack

```bash
make obs-up
make obs-status         # Confirm Prometheus, Grafana, exporters running
```

### 1.5 Verify dashboards

Open Grafana at **http://localhost:3000** (login: `admin` / `admin`).
Confirm the **Redis POC Overview** dashboard loads and shows live metrics.

Open Prometheus at **http://localhost:9090** and verify targets are UP.

---

## Phase 2 — Run a Steady-State Baseline (20 minutes)

The baseline establishes normal SLA behavior. All later comparisons reference this.

> 📖 **Runbook:** [Scenario 1 — Steady-State Baseline](../../scenarios/runbooks/01_baseline.md)

### 2.1 Run baseline on Redis Enterprise

```bash
PLATFORM=re \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=re-node1 \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
  ./scenarios/scripts/01_baseline.sh
```

The script follows the 10-step measurement methodology automatically:
1. Verifies environment parity and records metadata.
2. Checks the dataset is primed.
3. Runs a 60-second warmup (discarded from results).
4. Runs a 10-minute steady-state baseline.
5–8. No disruption for baseline — confirms stability.
9. Exports evidence (JSON + markdown) via `observability/exporters/run_summary_exporter.py`.
10. Reminds you to repeat at least 3 times.

**While the baseline runs**, watch the Grafana dashboard. Note:
- Throughput (ops/sec) — should be flat and stable.
- p50/p95/p99 latency — should be low and consistent.
- Error rate — should be zero.

### 2.2 Run baseline on OSS Sentinel

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=redis-primary \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
  ./scenarios/scripts/01_baseline.sh
```

### 2.3 Compare baseline results

Results are saved under `results/`. Each run creates a directory like:

```
results/01_baseline_re_20260322_140000/
├── environment.json       # Test metadata
├── events.jsonl           # Timeline markers
├── locust_stats.csv       # Aggregated Locust stats
├── locust_failures.csv    # Error breakdown
├── redis_info_*.txt       # Redis INFO snapshots
├── topology_*.txt         # Topology snapshots
├── run_summary.json       # Machine-readable summary
└── run_summary.md         # Human-readable report
```

Compare the two `run_summary.md` files side by side. Both platforms should show similar steady-state performance — this confirms a fair starting point.

---

## Phase 3 — Inject a Primary Failure (25 minutes)

This is the core HA proof. You will kill the primary Redis process and observe how each platform recovers.

> 📖 **Runbook:** [Scenario 2 — Primary Process Kill](../../scenarios/runbooks/02_primary_kill.md)

### 3.1 Primary kill on Redis Enterprise

```bash
PLATFORM=re \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=re-node1 \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
POST_RECOVERY_DURATION=300 \
  ./scenarios/scripts/02_primary_kill.sh
```

The script will:
1. Run a baseline to establish reference metrics.
2. Kill the primary container with `docker kill`.
3. Record the kill event timestamp for Grafana correlation.
4. Poll for a new primary to become available.
5. Observe recovery and post-recovery stability.
6. Export all evidence.

### 3.2 Primary kill on OSS Sentinel

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=redis-primary \
SENTINEL_CONTAINER=sentinel1 \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
POST_RECOVERY_DURATION=300 \
  ./scenarios/scripts/02_primary_kill.sh
```

### 3.3 What to watch in Grafana

During the kill event, switch to the Grafana dashboard and observe:

| Metric | Redis Enterprise (expected) | OSS Sentinel (expected) |
|---|---|---|
| Throughput drop | Brief dip, recovers in seconds | Longer dip during Sentinel election |
| Error burst | Minimal or zero client errors | Higher error count during failover window |
| p99 latency spike | Short spike, returns to baseline | Larger spike, slower return |
| Recovery time | Automatic, no operator action | Sentinel-triggered, may need client reconnect |

Record the **kill event epoch** printed by the script — use it to set the Grafana time range for screenshots.

### 3.4 Compare results

Open both `run_summary.md` files and answer the three scorecard questions:

1. **What happened?** — Describe the disruption and each platform's response.
2. **What did the application feel?** — Compare error counts, latency spikes, and downtime duration.
3. **Which platform made recovery faster or simpler?** — State the winner with evidence.

---

## Phase 4 — View Dashboards and Capture Evidence (15 minutes)

### 4.1 Grafana dashboard walkthrough

The **Redis POC Overview** dashboard (`observability/grafana/dashboards/redis-poc-overview.json`) includes:

- **Throughput (ops/sec)** — client-side request rate from Locust.
- **Latency percentiles** — p50, p95, p99 response times.
- **Error rate** — failures per second.
- **Redis memory usage** — server-side memory consumption.
- **Connected clients** — active client connections.
- **Replication lag** — replica sync state.

### 4.2 Set the time range

Use the event timestamps from `events.jsonl` in your run directory to set a precise Grafana time range that covers the disruption window. The `run_summary.json` file includes pre-built Grafana URLs with the correct time range.

### 4.3 Take screenshots

Capture dashboard screenshots for the evidence pack. Grafana render URLs are included in the run summary:

```bash
cat results/<run_id>/run_summary.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['grafana']['dashboard'])"
```

---

## Phase 5 — Export Evidence (10 minutes)

### 5.1 Run the evidence exporter

If the scenario scripts did not already export (they do by default), you can re-export manually:

```bash
make export-summary RUN_DIR=results/<run_id>
```

This runs `observability/exporters/run_summary_exporter.py` which produces:
- `run_summary.json` — machine-readable summary with latency percentiles, throughput, errors, timeline markers, and Grafana URLs.
- `run_summary.md` — human-readable report compatible with `docs/templates/POC_SCORECARD_TEMPLATE.md`.

### 5.2 Review the evidence pack

Each completed run directory should contain:

| File | Purpose |
|---|---|
| `environment.json` | Platform, versions, test parameters |
| `events.jsonl` | Timeline markers with epoch timestamps |
| `locust_stats.csv` | Aggregated Locust performance stats |
| `locust_stats_history.csv` | Time-series throughput data |
| `locust_failures.csv` | Error breakdown by type |
| `redis_info_*.txt` | Redis INFO snapshots (pre/post disruption) |
| `topology_*.txt` | Topology snapshots (pre/post disruption) |
| `run_summary.json` | Complete machine-readable summary |
| `run_summary.md` | Human-readable report |

### 5.3 Fill in the scorecard

Use `docs/templates/POC_SCORECARD_TEMPLATE.md` as the template. Copy the latency, throughput, and error data from the run summaries into the scorecard for each platform and scenario.

---

## Phase 6 — Interpret Results (5 minutes)

### Key metrics to compare

| Metric | Where to find it | What it tells you |
|---|---|---|
| Time to first error | `events.jsonl` — gap between `primary_kill_start` and first Locust failure | How quickly the client felt the disruption |
| Time to recover to 95% throughput | `locust_stats_history.csv` — compare post-kill throughput to baseline | How long the application was degraded |
| Peak latency during recovery | `run_summary.json` → `latency_percentiles_ms.p99` | Worst-case user experience during failover |
| Total error count | `run_summary.json` → `errors.total_failures` | Volume of failed requests |
| Operator interventions | Your notes — did you have to run any manual commands? | Operational simplicity |

### The story to tell

Redis Enterprise should demonstrate:
- **Faster failover** — automatic promotion in seconds vs. Sentinel election delay.
- **Fewer client errors** — built-in connection management vs. client-side reconnect burden.
- **Zero operator intervention** — no manual commands needed vs. potential manual recovery steps.
- **Simpler operations** — single `make re-up` vs. managing separate Sentinel and replica processes.

---

## Cleanup

```bash
make re-down
make oss-sentinel-down
make obs-down
```

Or tear down everything at once:

```bash
make vm-down
make obs-down
```

---

## Quick Reference: Available Workloads

| Workload | Locustfile | Profile | Read/Write |
|---|---|---|---|
| Cache read-heavy | `workloads/locustfiles/cache_read_heavy.py` | `workloads/profiles/cache_read_heavy.yaml` | 90/10 |
| Session mixed | `workloads/locustfiles/session_mixed.py` | `workloads/profiles/session_mixed.yaml` | 70/30 |

## Quick Reference: Makefile Targets

| Target | Description |
|---|---|
| `make setup` | Install Python dependencies |
| `make help` | Show all available targets |
| `make re-up` / `re-down` / `re-status` | Redis Enterprise 3-node cluster |
| `make oss-sentinel-up` / `down` / `status` | OSS Redis + Sentinel stack |
| `make oss-cluster-up` / `down` / `status` | OSS Redis Cluster (6 nodes) |
| `make vm-up` / `vm-down` / `vm-status` | All VM-path stacks at once |
| `make obs-up` / `obs-down` / `obs-status` | Observability stack (Prometheus + Grafana) |
| `make export-summary RUN_DIR=...` | Re-export run evidence |
| `make k3d-up` / `k3d-down` | k3d cluster for k8s paths |
| `make k8s-re-up` / `down` / `status` | Redis Enterprise on k8s |
| `make k8s-oss-up` / `down` / `status` | OSS Redis on k8s |
| `make clean` | Remove caches and temp files |

## Quick Reference: Scenario Scripts

| Script | Scenario | What it does |
|---|---|---|
| `scenarios/scripts/01_baseline.sh` | Steady-state baseline | Runs workload with no disruption; establishes reference metrics |
| `scenarios/scripts/02_primary_kill.sh` | Primary process kill | Kills primary container; measures failover and recovery |
