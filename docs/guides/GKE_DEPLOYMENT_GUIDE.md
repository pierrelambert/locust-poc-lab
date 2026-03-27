# GKE Deployment Guide — Quick Deploy + Step-by-Step Lab

**Purpose:** Run the Kubernetes comparison path on Google Kubernetes Engine (GKE), then execute the baseline and primary-kill scenarios against OSS Redis on k8s.
**Output:** A working GKE cluster, deployed Redis stacks, baseline + failover evidence packs, and a clean teardown.
**Time budget:** 75–90 minutes for a first run.
**Cost:** Roughly **$0.45-$0.75/hour** for the default cluster (`3 x e2-standard-4`, `100 GB pd-balanced` per node). Billing continues until you run `make gke-down`.
**Source:** [POC Lab Execution Blueprint](../POC_LAB_EXECUTION_BLUEPRINT.md), Motion A (k8s path), [Kubernetes Comparison Lab](K8S_COMPARISON_LAB.md).

> ⚠️ **Billing warning:** `make k8s-down` removes Redis resources, but the GKE cluster still bills until `make gke-down` completes.

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────┐
│ GKE cluster: locust-poc-lab (default: 3 x e2-standard-4)    │
│                                                              │
│  ┌─────────────────────┐  ┌───────────────────────────────┐  │
│  │ ns: redis-enterprise│  │ ns: redis-oss                │  │
│  │ RE Operator         │  │ redis-0, redis-1, redis-2    │  │
│  │ REC (3 pods)        │  │ redis-sentinel (3 pods)      │  │
│  │ REDB                │  │ baseline + primary-kill lab  │  │
│  └─────────────────────┘  └───────────────────────────────┘  │
│                                                              │
│ Locust runs from the host and reaches Redis via port-forward.│
└──────────────────────────────────────────────────────────────┘
```

---

## Section A — Quick Deploy

Before your first run:
- Copy `infra/gke/environment.example` to `infra/gke/environment` and adjust zone/size settings.
- If you want the short scenario targets to work as written, export a workload once per shell: `export LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml`

```bash
# Prereqs
gcloud auth list && gcloud config get project

# Create cluster (~5 min)
make gke-up

# Deploy Redis + run scenarios
make k8s-up && make k8s-status
make k8s-scenario-baseline
make k8s-scenario-primary-kill

# Teardown ⚠️
make k8s-down && make gke-down
```

> **If the Redis Enterprise operator install fails with RBAC/forbidden on GKE:** jump to Phase 2.1 for the exact `kubectl create clusterrolebinding ...` fix.

---

## Section B — Step-by-Step Learning Lab

## Phase 0 — Prerequisites (10 minutes)

### 0.1 Verify required CLIs and repo access

```bash
gcloud version
kubectl version --client
python3 --version
git status -sb
```

**Expected output:** Version information prints for `gcloud`, `kubectl`, and `python3`; `git status -sb` confirms you are in this repo.

> **Troubleshooting:** If `gcloud` or `kubectl` is missing, install it before continuing; `make gke-up` exits early when prerequisites are missing.

### 0.2 Verify Google Cloud auth and active project

```bash
gcloud auth list
gcloud config get project
```

**Expected output:** One account is marked `ACTIVE`, and `gcloud config get project` prints a non-empty project ID.

> **Troubleshooting:** If no account is active, run `gcloud auth login`. If the project is `(unset)`, run `gcloud config set project <PROJECT_ID>`.

### 0.3 Seed the GKE configuration file

```bash
cp infra/gke/environment.example infra/gke/environment
grep -E '^(GKE_|# Rough cost)' infra/gke/environment
```

**Expected output:** You see `GKE_CLUSTER_NAME`, location, node count, machine type, disk settings, and the rough hourly cost note.

> **Troubleshooting:** If `infra/gke/environment` already exists, keep it and review it instead of overwriting local settings.

### 0.4 Review cost-sensitive settings

```bash
grep -E '^GKE_(ZONE|REGION|NODE_COUNT|MACHINE_TYPE|DISK_SIZE_GB|DISK_TYPE)' infra/gke/environment
```

**Expected output:** A small block showing the cluster location and sizing you are about to pay for.

> **Troubleshooting:** Set **either** `GKE_ZONE` **or** `GKE_REGION`, not both; `gke-setup.sh` exits with an error if both are set.

---

## Phase 1 — Create GKE Cluster (10 minutes)

### 1.1 Create the GKE practice cluster

```bash
make gke-up
```

**Expected output (final lines):**

```text
[gke-setup] Creating GKE cluster 'locust-poc-lab' ...
[gke-setup] Waiting for nodes to be ready...
[gke-setup] Cluster is ready.
[gke-setup]   Nodes:      3
[gke-setup]   Context:    gke_<project>_<zone>_locust-poc-lab
[gke-setup]   Namespaces: redis-enterprise, redis-oss
```

> **Troubleshooting:** If the script says the cluster already exists, either run `make gke-down` first or change `GKE_CLUSTER_NAME` in `infra/gke/environment`.

### 1.2 Verify cluster status from GKE

```bash
make gke-status
```

**Expected output:** A table showing the cluster name, `RUNNING` status, versions, and location.

> **Troubleshooting:** If the cluster is reported missing, confirm the same `infra/gke/environment` file is being used for both `gke-up` and `gke-status`.

### 1.3 Verify nodes and namespaces from kubectl

```bash
kubectl get nodes -o wide
kubectl get ns redis-enterprise redis-oss
```

**Expected output:** Three nodes in `Ready` state and two namespaces in `Active` state.

> **Troubleshooting:** If nodes are not `Ready` yet, wait 1–2 minutes and rerun the command; `kubectl wait` may complete before every status line has refreshed.

---

## Phase 2 — Deploy Redis (20 minutes)

### 2.1 Deploy Redis Enterprise Operator + cluster + database

```bash
make k8s-re-up
```

**Expected output (final lines):**

```text
Installing Redis Enterprise Operator bundle v7.8.2-6...
Waiting for operator to be ready...
Creating Redis Enterprise Cluster...
Waiting for REC pods (this may take several minutes)...
Creating Redis Enterprise Database...
Redis Enterprise deployed. Run 'make k8s-re-status' to check.
```

> **Troubleshooting:** If you get RBAC or `forbidden` errors on GKE, run `kubectl create clusterrolebinding gke-cluster-admin-binding --clusterrole=cluster-admin --user="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)"` once, then retry.

### 2.2 Verify Redis Enterprise status

```bash
make k8s-re-status
```

**Expected output:** A `rec-poc-lab` cluster in `Running` state, an active `redb-poc-lab`, and three REC pods in `Running` status.

> **Troubleshooting:** REC pods can take several minutes to settle. If pods stay `Pending`, inspect node capacity and project quotas before retrying.

### 2.3 Deploy OSS Redis with Sentinel

```bash
make k8s-oss-up
```

**Expected output (final lines):**

```text
Waiting for Redis pods...
statefulset.apps/redis condition met
Waiting for Sentinel pods...
deployment.apps/redis-sentinel condition met
OSS Redis with Sentinel deployed. Run 'make k8s-oss-status' to check.
```

> **Troubleshooting:** If Sentinel pods enter `CrashLoopBackOff`, wait for the Redis StatefulSet to stabilize, then rerun `make k8s-oss-status`.

### 2.4 Verify OSS Redis status

```bash
make k8s-oss-status
```

**Expected output:** Three `redis-*` pods, three `redis-sentinel-*` pods, and the `redis` / `redis-sentinel` services.

> **Troubleshooting:** If you see "No Redis pods found" or "No services found", rerun `make k8s-oss-up` and confirm the `redis-oss` namespace is still `Active`.

### 2.5 Check both stacks together

```bash
make k8s-status
```

**Expected output:** The Redis Enterprise and OSS status sections print back-to-back with running pods in both namespaces.

> **Troubleshooting:** If one half is healthy and the other is not, fix the failing namespace first instead of tearing the whole cluster down.

---

## Phase 3 — Run Scenarios (25 minutes)

### 3.1 Run the k8s baseline scenario

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  make k8s-scenario-baseline
```

**Expected output:** The scenario banner prints, the script verifies the k8s environment, warms up, runs the baseline, then saves results under `results/01_baseline_k8s-oss_<timestamp>/`.

> **Troubleshooting:** If you see `LOCUST_FILE must be set`, make sure you included the two environment variables above. If the script warns that the database is empty, seed data with workload traffic before trusting the results.

### 3.2 Verify the baseline run directory

```bash
ls -1dt results/01_baseline_k8s-oss_* | head -n 1
```

**Expected output:** A single results directory path such as `results/01_baseline_k8s-oss_20260327_141500`.

> **Troubleshooting:** If no directory appears, rerun the baseline and watch for earlier script failures around namespace checks, port-forwarding, or Locust startup.

### 3.3 Run the primary-kill scenario

```bash
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml \
  make k8s-scenario-primary-kill
```

**Expected output:** The script records a baseline, deletes `redis-0`, logs the kill event epoch, waits for failover, then saves results under `results/02_primary_kill_k8s-oss_<timestamp>/`.

> **Troubleshooting:** If failover times out, run `kubectl get pods -n redis-oss -o wide` and `kubectl get svc -n redis-oss` to confirm the StatefulSet and Sentinel pods recovered.

### 3.4 Verify failover evidence markers

```bash
tail -n 5 "$(ls -1dt results/02_primary_kill_k8s-oss_* | head -n 1)/events.jsonl"
```

**Expected output:** Recent event lines include markers such as `primary_kill_start`, `primary_kill_done`, `failover_detected` or `failover_complete`, and post-recovery observation events.

> **Troubleshooting:** If `events.jsonl` is missing, the scenario likely exited early; rerun it and confirm the `redis-oss` namespace is healthy before retrying.

### 3.5 What to watch while the primary dies

| Metric | GKE OSS Sentinel (expected) |
|---|---|
| Throughput drop | Dip during pod recreation + Sentinel election |
| Error burst | Errors while port-forward reconnects and Sentinel elects a primary |
| p99 latency spike | Spike during failover, gradual return toward baseline |
| Recovery time | Usually tens of seconds, depending on pod restart + Sentinel detection |

---

## Phase 4 — Compare & Export (10 minutes)

### 4.1 Re-export the latest primary-kill summary

```bash
make export-summary RUN_DIR="$(ls -1dt results/02_primary_kill_k8s-oss_* | head -n 1)"
```

**Expected output:** The exporter prints `[OK] JSON summary:` and `[OK] Markdown report:` for the selected run directory.

> **Troubleshooting:** If the shell expands to nothing, verify that the primary-kill run completed and created a `results/02_primary_kill_k8s-oss_*` directory.

### 4.2 Review the human-readable report

```bash
sed -n '1,80p' "$(ls -1dt results/02_primary_kill_k8s-oss_* | head -n 1)/run_summary.md"
```

**Expected output:** A markdown report showing latency, throughput, errors, timeline markers, and evidence file links.

> **Troubleshooting:** If `run_summary.md` is missing, rerun the export command above or inspect the scenario output for earlier exporter errors.

### 4.3 Metrics to compare in your scorecard

| Metric | Where to find it | What it tells you |
|---|---|---|
| Time to first error | `events.jsonl` around `primary_kill_start` | How quickly the client noticed the outage |
| Time to recover to 95% throughput | `locust_stats_history.csv` | How long the app stayed degraded |
| Peak p99 latency | `run_summary.json` | Worst-case user experience during failover |
| Total errors | `run_summary.json` → `errors.total_failures` | Overall client impact |
| Operator effort | Your notes | How much manual intervention GKE + Sentinel required |

---

## Phase 5 — Cleanup (5 minutes)

### 5.1 Remove the Redis resources from the cluster

```bash
make k8s-down
```

**Expected output:** `kubectl delete` lines remove the OSS and Redis Enterprise resources and namespaces.

> **Troubleshooting:** If deletions hang, rerun `make k8s-down` once; Kubernetes resource deletion is usually idempotent here.

### 5.2 Delete the GKE cluster ⚠️ critical

```bash
make gke-down
```

**Expected output:** `gke-setup` logs that the cluster is being deleted, followed by `Cluster deleted.`

> **Troubleshooting:** If the command says the cluster does not exist, verify that your current `infra/gke/environment` location matches the one used during creation.

### 5.3 Verify the cluster is gone

```bash
make gke-status
```

**Expected output:** `Cluster 'locust-poc-lab' does not exist ...` (or the custom name from your environment file).

> **Troubleshooting:** GKE deletion can take a few minutes to propagate. If you still see the cluster immediately after deletion, wait briefly and rerun the status check.

---

## Quick Reference: Makefile Targets

| Target | Description |
|---|---|
| `make gke-up` / `gke-down` / `gke-status` | Create, delete, or inspect the GKE practice cluster |
| `make k8s-re-up` / `k8s-re-down` / `k8s-re-status` | Redis Enterprise Operator on k8s |
| `make k8s-oss-up` / `k8s-oss-down` / `k8s-oss-status` | OSS Redis with Sentinel on k8s |
| `make k8s-up` / `k8s-down` / `k8s-status` | Both k8s stacks together |
| `make k8s-scenario-baseline` | Run the k8s baseline scenario |
| `make k8s-scenario-primary-kill` | Run the k8s primary-kill scenario |
| `make export-summary RUN_DIR=...` | Re-export a run summary |

## Quick Reference: Results Artifacts

| Artifact | Why it matters |
|---|---|
| `environment.json` | Captures namespace, workload, pod, node, and Redis version |
| `events.jsonl` | Timeline of warmup, baseline, kill, failover, and recovery markers |
| `locust_stats.csv` / `locust_stats_history.csv` | Throughput and latency over time |
| `locust_failures.csv` | Error breakdown during disruption |
| `topology_*.txt` | Pod, service, and Sentinel snapshots before/after failure |
| `run_summary.json` / `run_summary.md` | Final machine-readable + human-readable evidence pack |

## Quick Reference: GKE Configuration Knobs

| Variable | Default | Purpose |
|---|---|---|
| `GKE_CLUSTER_NAME` | `locust-poc-lab` | Cluster name used by `make gke-*` |
| `GKE_ZONE` | `us-central1-a` | Zonal deployment target |
| `GKE_REGION` | unset | Regional deployment target (use instead of zone) |
| `GKE_NODE_COUNT` | `3` | Worker node count |
| `GKE_MACHINE_TYPE` | `e2-standard-4` | Per-node CPU/RAM profile |
| `GKE_DISK_SIZE_GB` | `100` | Per-node persistent disk size |
| `GKE_DISK_TYPE` | `pd-balanced` | Per-node disk type |
