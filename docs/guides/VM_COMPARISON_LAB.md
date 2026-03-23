# VM Comparison Lab — Redis Enterprise vs OSS on Bare-Metal / VMs

**Purpose:** Run a side-by-side Redis Enterprise vs OSS comparison on dedicated VMs (or bare-metal servers) without Docker.
**Output:** Baseline and failover evidence packs, completed scorecard.
**Time budget:** 90 minutes.
**Prerequisites:** Two VMs (one for RE, one for OSS) with Ubuntu 20.04+ or RHEL/Rocky 8+, ≥4 CPUs, ≥16 GB RAM each.

---

## Architecture Overview

```
┌──────────────────────────┐    ┌──────────────────────────┐
│  VM 1 — Redis Enterprise │    │  VM 2 — OSS Redis        │
│                          │    │  (Sentinel or Cluster)   │
│  Redis Enterprise node   │    │  redis-server             │
│  Locust load generator   │    │  Locust load generator   │
│  Redis Exporter          │    │  Redis Exporter          │
└──────────────────────────┘    └──────────────────────────┘
         │                                │
         └────────── Prometheus ──────────┘
                   + Grafana
```

Each VM runs the Locust POC Lab tooling via systemd services.  Redis itself is installed separately (Redis Enterprise via its installer, OSS via package manager).

---

## Phase 1 — Prepare the VMs (20 minutes)

### 1.1 Install Redis on each VM

**VM 1 — Redis Enterprise:**
Follow the [Redis Enterprise Software installation guide](https://docs.redis.com/latest/rs/installing-upgrading/) for your OS.  Create a single-node cluster and a database.

**VM 2 — OSS Redis with Sentinel:**

```bash
# Ubuntu
sudo apt-get update && sudo apt-get install -y redis-server redis-sentinel

# RHEL / Rocky
sudo dnf install -y redis
```

Configure a primary + replica + sentinel topology per your requirements.

### 1.2 Clone the repo and deploy the POC tooling

On **each VM**:

```bash
git clone https://github.com/pierrelambert/locust-poc-lab.git
cd locust-poc-lab
sudo bash infra/vm/deploy.sh
```

The deploy script:
- Detects your package manager (apt / dnf / yum)
- Creates a `locust-poc` system user
- Copies workloads, scenarios, and observability code to `/opt/locust-poc`
- Creates a Python venv and installs dependencies
- Installs `redis_exporter` for Prometheus metrics
- Installs and enables systemd services (`locust-poc`, `redis-exporter`)

### 1.3 Configure the environment

Edit `/etc/locust-poc/environment` on each VM:

```bash
sudo vi /etc/locust-poc/environment
```

Set `REDIS_HOST` to point to the local Redis instance.  For Redis Enterprise, use the database endpoint.  For OSS, use `redis://localhost:6379`.

Restart services after editing:

```bash
sudo systemctl restart locust-poc redis-exporter
```

### 1.4 Verify the deployment

```bash
sudo bash /opt/locust-poc/../locust-poc-lab/infra/vm/verify.sh
# Or from the repo checkout:
sudo bash infra/vm/verify.sh
```

All checks should pass: services active, Redis PING, Locust UI reachable, exporter metrics available.

---

## Phase 2 — Run a Steady-State Baseline (20 minutes)

### 2.1 Baseline on Redis Enterprise (VM 1)

```bash
cd /opt/locust-poc
sudo -u locust-poc \
  PLATFORM=re \
  LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
  WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  LOCUST_HOST=redis://<RE_ENDPOINT>:6379 \
  BASELINE_DURATION=600 \
  WARMUP_DURATION=60 \
  ./scenarios/scripts/01_baseline.sh
```

### 2.2 Baseline on OSS Redis (VM 2)

```bash
cd /opt/locust-poc
sudo -u locust-poc \
  PLATFORM=oss-sentinel \
  LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
  WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  LOCUST_HOST=redis://localhost:6379 \
  BASELINE_DURATION=600 \
  WARMUP_DURATION=60 \
  ./scenarios/scripts/01_baseline.sh
```

### 2.3 Compare baselines

Both platforms should show similar steady-state performance.  Compare the `run_summary.md` files from each run to confirm a fair starting point.

---

## Phase 3 — Inject a Primary Failure (25 minutes)

On VMs, instead of `docker kill`, you kill the Redis process directly.

### 3.1 Primary kill on Redis Enterprise (VM 1)

Redis Enterprise handles process restarts automatically.  Kill the Redis shard process:

```bash
# Find the shard PID
sudo pkill -f "redis-server.*:<DB_PORT>"
```

The scenario script records the event and measures recovery.

### 3.2 Primary kill on OSS Redis (VM 2)

```bash
sudo systemctl stop redis-server
# Wait for Sentinel to promote a replica, then restart:
sudo systemctl start redis-server
```

### 3.3 What to watch

| Metric | Redis Enterprise (expected) | OSS Sentinel (expected) |
|---|---|---|
| Throughput drop | Brief dip, recovers in seconds | Longer dip during Sentinel election |
| Error burst | Minimal or zero | Higher error count during failover |
| p99 latency spike | Short spike | Larger spike, slower return |
| Recovery time | Automatic, no operator action | Sentinel-triggered, may need reconnect |

---

## Phase 4 — Capture Evidence (15 minutes)

### 4.1 Export run summaries

```bash
make export-summary RUN_DIR=results/<run_id>
```

### 4.2 Collect from both VMs

Copy the `results/` directories from each VM for side-by-side comparison.  Each run directory contains `run_summary.json`, `run_summary.md`, Locust CSVs, and Redis INFO snapshots.

---

## Phase 5 — Fill the Scorecard (10 minutes)

Use `docs/templates/POC_SCORECARD_TEMPLATE.md`.  Key metrics to compare:

| Metric | Where to find it |
|---|---|
| Time to first error | `events.jsonl` — gap between kill and first failure |
| Recovery to 95% throughput | `locust_stats_history.csv` |
| Peak p99 latency | `run_summary.json` → `latency_percentiles_ms.p99` |
| Total error count | `run_summary.json` → `errors.total_failures` |
| Operator interventions | Your notes |

---

## Cleanup

```bash
# On each VM:
sudo bash infra/vm/teardown.sh          # Keeps config
sudo bash infra/vm/teardown.sh --purge   # Removes everything
```

---

## Quick Reference

| File | Purpose |
|---|---|
| `infra/vm/deploy.sh` | Install POC tooling on a VM |
| `infra/vm/teardown.sh` | Remove POC tooling from a VM |
| `infra/vm/verify.sh` | Check all services and endpoints |
| `infra/vm/environment.example` | Template for `/etc/locust-poc/environment` |
| `infra/vm/systemd/locust-poc.service` | Locust systemd unit |
| `infra/vm/systemd/redis-exporter.service` | Redis Exporter systemd unit |

