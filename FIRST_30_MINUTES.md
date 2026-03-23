# First 30 Minutes — Hands-On Quickstart

Get a working demo running on your laptop in 30 minutes using Docker.
You'll start OSS Redis with Sentinel, run a cache workload, kill the primary, and watch failover on Grafana.

> **Prerequisites:** Docker Desktop (≥16 GB RAM allocated), Python 3.10+, this repo cloned.
> See [START_HERE.md](START_HERE.md) for full prerequisite details.

---

## Step 1 — Install dependencies (2 min)

```bash
cd locust-poc-lab
make setup
```

This installs the Python packages listed in `requirements.txt` (Locust, redis-py, PyYAML, etc.).

---

## Step 2 — Start the Redis stack (3 min)

```bash
make oss-sentinel-up
```

This launches 6 containers: 1 Redis primary, 2 replicas, and 3 Sentinel instances.

**Verify everything is running:**

```bash
make oss-sentinel-status
```

You should see all 6 containers in a `running` state.

**Quick smoke test:**

```bash
docker exec redis-primary redis-cli PING
# → PONG
```

---

## Step 3 — Start the observability stack (2 min)

```bash
make obs-up
make obs-status    # Confirm Prometheus, Grafana, exporters are running
```

Open **http://localhost:3000** in your browser (Grafana — login: `admin` / `admin`).
Confirm the **Redis POC Overview** dashboard loads.

---

## Step 4 — Run a baseline workload (10 min)

Run a 5-minute steady-state baseline to establish normal performance:

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=redis-primary \
BASELINE_DURATION=300 \
WARMUP_DURATION=30 \
  ./scenarios/scripts/01_baseline.sh
```

The script will:
1. Verify the environment and check the dataset.
2. Run a 30-second warmup (discarded from results).
3. Run a 5-minute baseline measuring throughput, latency, and errors.
4. Export results to `results/01_baseline_oss-sentinel_<timestamp>/`.

**While it runs**, watch the Grafana dashboard:
- **Throughput** — should be flat and stable.
- **p50/p95/p99 latency** — should be low and consistent.
- **Error rate** — should be zero.

---

## Step 5 — Kill the primary and watch failover (10 min)

This is the core demo. You'll kill the Redis primary and observe how Sentinel handles failover.

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
PRIMARY_CONTAINER=redis-primary \
SENTINEL_CONTAINER=sentinel1 \
BASELINE_DURATION=120 \
WARMUP_DURATION=30 \
POST_RECOVERY_DURATION=120 \
  ./scenarios/scripts/02_primary_kill.sh
```

**What to watch in Grafana:**

| Metric | What you'll see |
|---|---|
| Throughput (ops/sec) | Drops during failover, then recovers |
| Error burst | Spike of client errors during the failover window |
| p99 latency | Sharp spike, then returns toward baseline |
| Recovery time | Sentinel election + promotion (typically 10–30 seconds) |

The script prints the **kill event epoch** — use it to set the Grafana time range for a precise view.

---

## Step 6 — Review results (3 min)

Results are saved under `results/`. Open the human-readable report:

```bash
cat results/02_primary_kill_oss-sentinel_*/run_summary.md
```

Key things to look for:
- **Time to first error** — how quickly the client felt the disruption.
- **Total error count** — volume of failed requests during failover.
- **Peak p99 latency** — worst-case user experience.
- **Recovery time** — how long until throughput returned to 95% of baseline.

---

## Step 7 — Clean up

```bash
make oss-sentinel-down
make obs-down
```

---

## What's next?

| Goal | Next step |
|---|---|
| Compare with Redis Enterprise | Run the same scenarios with `make re-up` — see [SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md) |
| Try Kubernetes paths | `make k3d-up` then `make k8s-re-up` / `make k8s-oss-up` |
| Run the full 90-minute guided lab | [docs/guides/SA_GUIDED_LAB.md](docs/guides/SA_GUIDED_LAB.md) |
| Fill in a POC scorecard | [docs/templates/POC_SCORECARD_TEMPLATE.md](docs/templates/POC_SCORECARD_TEMPLATE.md) |
| Hit a problem? | [docs/guides/TROUBLESHOOTING.md](docs/guides/TROUBLESHOOTING.md) |

