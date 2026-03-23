# Kubernetes Comparison Lab — Redis Enterprise Operator vs OSS Redis on k8s

**Purpose:** Run a side-by-side Redis Enterprise vs OSS comparison on Kubernetes using k3d, measuring failover quality and recovery time.
**Output:** Baseline and failover evidence packs, completed scorecard.
**Time budget:** 90 minutes.
**Source:** [POC Lab Execution Blueprint](../POC_LAB_EXECUTION_BLUEPRINT.md), Motion A (k8s path).

---

## Prerequisites

| Requirement | How to verify |
|---|---|
| Docker installed and running | `docker info` |
| k3d installed | `k3d version` |
| kubectl installed | `kubectl version --client` |
| Helm installed (optional, for advanced RE configs) | `helm version` |
| Python 3.10+ | `python3 --version` |
| Git clone of this repo | `git status` in repo root |
| Docker Desktop allocated ≥16 GB RAM | Docker Desktop → Settings → Resources (see [Troubleshooting](TROUBLESHOOTING.md#1-docker-resource-issues)) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  k3d cluster: locust-poc-lab (1 server + 3 agents)      │
│                                                         │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │ ns: redis-enterprise │  │ ns: redis-oss            │  │
│  │                     │  │                          │  │
│  │ RE Operator         │  │ redis-0 (primary)        │  │
│  │ REC (3 pods)        │  │ redis-1, redis-2         │  │
│  │ REDB                │  │ redis-sentinel (3 pods)  │  │
│  └─────────────────────┘  └──────────────────────────┘  │
│                                                         │
│  Locust load generator runs on the host via             │
│  kubectl port-forward to reach Redis in the cluster.    │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Setup k3d Cluster (15 minutes)

### 1.1 Install Python dependencies

```bash
make setup
```

### 1.2 Create the k3d cluster

```bash
make k3d-up
```

This runs `infra/scripts/k3d-setup.sh` which creates a k3d cluster named `locust-poc-lab` with 1 server node and 3 agent nodes. It also creates the `redis-enterprise` and `redis-oss` namespaces.

**Expected output:**

```
[k3d-setup] Creating k3d cluster 'locust-poc-lab' with 3 agent nodes...
[k3d-setup] Cluster created. Setting kubectl context...
[k3d-setup] Waiting for nodes to be ready...
[k3d-setup] Cluster is ready.
[k3d-setup]   Nodes:      4
[k3d-setup]   Namespaces: redis-enterprise, redis-oss
[k3d-setup]   Context:    k3d-locust-poc-lab
```

### 1.3 Verify the cluster

```bash
kubectl get nodes
```

You should see 4 nodes (1 server + 3 agents), all in `Ready` status.

> **Troubleshooting:** If `k3d-up` fails with "cluster already exists", run `make k3d-down` first, then retry.

---

## Phase 2 — Deploy Redis Enterprise Operator + OSS Redis (20 minutes)

### 2.1 Deploy Redis Enterprise Operator

```bash
make k8s-re-up
```

This deploys the Redis Enterprise Operator (v7.8.2-6), creates a 3-node Redis Enterprise Cluster (REC), and provisions a Redis Enterprise Database (REDB).

**Expected output (final lines):**

```
Installing Redis Enterprise Operator bundle v7.8.2-6...
Waiting for operator to be ready...
Creating Redis Enterprise Cluster...
Waiting for REC pods (this may take several minutes)...
Creating Redis Enterprise Database...
Redis Enterprise deployed. Run 'make k8s-re-status' to check.
```

### 2.2 Verify Redis Enterprise deployment

```bash
make k8s-re-status
```

**Expected output:**

```
=== Redis Enterprise Cluster ===
NAME          NODES   VERSION   STATE     ...
rec-poc-lab   3       ...       Running   ...

=== Redis Enterprise Database ===
NAME          ...   STATUS   ...
redb-poc-lab  ...   active   ...

=== Pods ===
NAME              READY   STATUS    ...
rec-poc-lab-0     2/2     Running   ...
rec-poc-lab-1     2/2     Running   ...
rec-poc-lab-2     2/2     Running   ...
```

> **Note:** REC pods may take 3–5 minutes to reach `Running` state. If pods are in `Pending` or `ContainerCreating`, wait and re-check.

### 2.3 Deploy OSS Redis with Sentinel

```bash
make k8s-oss-up
```

This deploys a Redis StatefulSet (1 primary + 2 replicas) and a Sentinel Deployment (3 pods) in the `redis-oss` namespace.

**Expected output (final lines):**

```
Waiting for Redis pods...
statefulset.apps/redis condition met
Waiting for Sentinel pods...
deployment.apps/redis-sentinel condition met
OSS Redis with Sentinel deployed. Run 'make k8s-oss-status' to check.
```

### 2.4 Verify OSS Redis deployment

```bash
make k8s-oss-status
```

**Expected output:**

```
=== Redis Pods ===
NAME      READY   STATUS    ...
redis-0   1/1     Running   ...
redis-1   1/1     Running   ...
redis-2   1/1     Running   ...

=== Sentinel Pods ===
NAME                              READY   STATUS    ...
redis-sentinel-...                1/1     Running   ...
redis-sentinel-...                1/1     Running   ...
redis-sentinel-...                1/1     Running   ...

=== Services ===
NAME             TYPE        CLUSTER-IP   ...
redis            ClusterIP   ...
redis-sentinel   ClusterIP   ...
```

> **Troubleshooting:** If Sentinel pods are in `CrashLoopBackOff`, the Redis primary may not be ready yet. Wait 30 seconds and check again.

---

## Phase 3 — Run Baseline Scenario (20 minutes)

The baseline establishes normal SLA behavior. All later comparisons reference this.

### 3.1 Run baseline on OSS Redis (k8s)

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  make k8s-scenario-baseline
```

Or run the script directly with custom parameters:

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
K8S_NAMESPACE=redis-oss \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
  ./scenarios/k8s/01_baseline.sh
```

The script will:
1. Verify the k8s environment (namespace, running pods).
2. Start a `kubectl port-forward` to reach Redis from the host.
3. Check the dataset is primed.
4. Run a 60-second warmup (discarded from results).
5. Run a 10-minute steady-state baseline.
6. Export evidence (JSON + markdown).

**While the baseline runs**, note:
- Throughput (ops/sec) — should be flat and stable.
- p50/p95/p99 latency — should be low and consistent.
- Error rate — should be zero.

### 3.2 Compare baseline results

Results are saved under `results/`. Each run creates a directory like:

```
results/01_baseline_k8s-oss_20260323_140000/
├── environment.json       # Test metadata (namespace, pod, node)
├── events.jsonl           # Timeline markers
├── locust_stats.csv       # Aggregated Locust stats
├── locust_failures.csv    # Error breakdown
├── redis_info_*.txt       # Redis INFO snapshots
├── topology_*.txt         # Topology snapshots (pods, services, sentinel)
├── run_summary.json       # Machine-readable summary
└── run_summary.md         # Human-readable report
```

> **Tip:** Run the baseline at least 3 times and compare results for consistency before proceeding.

---

## Phase 4 — Run Primary Kill Scenario (25 minutes)

This is the core HA proof. You will delete the primary Redis pod and observe how the platform recovers.

### 4.1 Primary kill on OSS Redis (k8s)

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  make k8s-scenario-primary-kill
```

Or run directly with custom parameters:

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
K8S_NAMESPACE=redis-oss \
K8S_PRIMARY_POD=redis-0 \
BASELINE_DURATION=600 \
WARMUP_DURATION=60 \
POST_RECOVERY_DURATION=300 \
  ./scenarios/k8s/02_primary_kill.sh
```

The script will:
1. Run a baseline to establish reference metrics.
2. Start a continuous workload.
3. Delete the primary pod with `kubectl delete pod redis-0 --grace-period=0 --force`.
4. Record the kill event timestamp.
5. Wait for the StatefulSet to recreate the pod.
6. Monitor Sentinel for failover detection.
7. Observe post-recovery stability (5 minutes).
8. Export all evidence.

### 4.2 What to watch

| Metric | k8s OSS Sentinel (expected) |
|---|---|
| Throughput drop | Dip during pod recreation + Sentinel election |
| Error burst | Errors while port-forward reconnects and Sentinel elects new primary |
| p99 latency spike | Spike during failover, gradual return to baseline |
| Recovery time | StatefulSet recreates pod; Sentinel triggers failover (10–30s typical) |

Record the **kill event epoch** printed by the script — use it to correlate with any observability dashboards.

### 4.3 Review results

Open the `run_summary.md` file and answer the three scorecard questions:

1. **What happened?** — Describe the disruption and the platform's response.
2. **What did the application feel?** — Compare error counts, latency spikes, and downtime duration.
3. **How does this compare to Docker-based results?** — If you ran the [SA Guided Lab](SA_GUIDED_LAB.md), compare k8s failover behavior to Docker-based failover.

---

## Phase 5 — Compare Results + Teardown (10 minutes)

### 5.1 Export evidence (if not already done)

```bash
make export-summary RUN_DIR=results/<run_id>
```

### 5.2 Key metrics to compare

| Metric | Where to find it | What it tells you |
|---|---|---|
| Time to first error | `events.jsonl` — gap between `primary_kill_start` and first Locust failure | How quickly the client felt the disruption |
| Time to recover to 95% throughput | `locust_stats_history.csv` — compare post-kill throughput to baseline | How long the application was degraded |
| Peak latency during recovery | `run_summary.json` → `latency_percentiles_ms.p99` | Worst-case user experience during failover |
| Total error count | `run_summary.json` → `errors.total_failures` | Volume of failed requests |
| Operator interventions | Your notes — did you have to run any manual commands? | Operational simplicity |

### 5.3 Fill in the scorecard

Use `docs/templates/POC_SCORECARD_TEMPLATE.md` as the template. Copy the latency, throughput, and error data from the run summaries into the scorecard.

### 5.4 Teardown

Tear down the k8s stacks:

```bash
make k8s-oss-down       # Remove OSS Redis from k8s
make k8s-re-down        # Remove Redis Enterprise from k8s
make k3d-down           # Delete the k3d cluster
```

Or tear down everything at once:

```bash
make k8s-down           # Remove all k8s stacks
make k3d-down           # Delete the k3d cluster
```

---

## Quick Reference: Makefile Targets

| Target | Description |
|---|---|
| `make setup` | Install Python dependencies |
| `make help` | Show all available targets |
| `make k3d-up` / `k3d-down` | Create / delete k3d cluster |
| `make k8s-re-up` / `k8s-re-down` / `k8s-re-status` | Redis Enterprise Operator on k8s |
| `make k8s-oss-up` / `k8s-oss-down` / `k8s-oss-status` | OSS Redis with Sentinel on k8s |
| `make k8s-up` / `k8s-down` / `k8s-status` | All k8s stacks at once |
| `make k8s-scenario-baseline` | Run k8s baseline scenario |
| `make k8s-scenario-primary-kill` | Run k8s primary kill scenario |
| `make export-summary RUN_DIR=...` | Re-export run evidence |
| `make clean` | Remove caches and temp files |

## Quick Reference: k8s Scenario Scripts

| Script | Scenario | What it does |
|---|---|---|
| `scenarios/k8s/01_baseline.sh` | Steady-state baseline | Runs workload with no disruption; establishes reference metrics |
| `scenarios/k8s/02_primary_kill.sh` | Primary process kill | Deletes primary pod; measures failover and recovery |
| `scenarios/k8s/03_node_loss.sh` | Node loss | Drains/cordons a node; measures pod rescheduling and recovery |
| `scenarios/k8s/05_network_partition.sh` | Network partition | Isolates a pod via NetworkPolicy; measures split-brain behavior |

## Quick Reference: k8s Infrastructure

| Path | Purpose |
|---|---|
| `infra/scripts/k3d-setup.sh` | k3d cluster creation/deletion script |
| `infra/k8s/re-operator/` | Redis Enterprise Operator manifests (namespace, operator, REC, REDB) |
| `infra/k8s/oss-k8s/` | OSS Redis manifests (namespace, configmap, StatefulSet, Sentinel) |
| `scenarios/k8s/lib/k8s_helpers.sh` | Shared helpers for k8s scenario scripts |
