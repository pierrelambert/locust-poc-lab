# Operator Effort Checklist — Redis Enterprise vs OSS Redis

**Purpose:** Compare the manual steps, commands, and operator time required for each platform across all standard scenarios.  
**Usage:** Fill in the "Actual" columns during each POC run. Use the "Expected" columns as a reference.  
**Source:** [Scenario Matrix](../SCENARIO_MATRIX.md) and [POC Lab Execution Blueprint](../POC_LAB_EXECUTION_BLUEPRINT.md).

---

## How to Use This Checklist

1. Print or copy this document before each scenario run.
2. For each step, record whether it was needed (✅ = yes, ❌ = no, N/A = not applicable).
3. Record the actual commands executed and time spent.
4. At the end, total the operator interventions and time for each platform.
5. Attach the completed checklist to the evidence pack alongside the run summary.

---

## Scenario 1: Steady-State Baseline

No disruption — this scenario establishes the reference. Record any manual steps needed to reach steady state.

| Step | Redis Enterprise | OSS Sentinel | OSS Cluster |
|---|---|---|---|
| Start infrastructure | `make re-up` | `make oss-sentinel-up` | `make oss-cluster-up` |
| Verify cluster health | `make re-status` | `make oss-sentinel-status` | `make oss-cluster-status` |
| Manual config adjustments needed? | Expected: ❌ | Expected: ❌ | Expected: ❌ |
| Manual client tuning needed? | Expected: ❌ | Expected: ❌ | Expected: ❌ |
| Commands outside scripted path | Expected: 0 | Expected: 0 | Expected: 0 |
| **Total operator time** | ___ min | ___ min | ___ min |

---

## Scenario 2: Primary Process Kill

| Step | Redis Enterprise | OSS Sentinel | OSS Cluster |
|---|---|---|---|
| **Pre-disruption** | | | |
| Identify primary node | Automatic (cluster manages) | `redis-cli -p 26379 SENTINEL get-master-addr-by-name` | `redis-cli CLUSTER NODES \| grep master` |
| **During disruption** | | | |
| Kill primary | `docker kill re-node-1` | `docker kill redis-primary` | `docker kill redis-node-1` |
| Failover trigger | Automatic — no action needed | Sentinel detects + elects (automatic but slower) | Cluster protocol detects + elects |
| Manual failover command needed? | Expected: ❌ | Expected: ❌ (Sentinel handles) | Expected: ❌ (Cluster handles) |
| Client reconnection needed? | Expected: ❌ | Expected: possibly ✅ | Expected: possibly ✅ (MOVED redirects) |
| **Post-disruption** | | | |
| Verify new primary | Automatic | `SENTINEL get-master-addr-by-name` | `CLUSTER NODES` |
| Rejoin failed node | Automatic on container restart | May need `REPLICAOF` reconfiguration | May need `CLUSTER MEET` + slot rebalance |
| Reconfigure Sentinel/Cluster? | N/A | Expected: ❌ (Sentinel updates) | Expected: ❌ (Cluster updates) |
| Restart client application? | Expected: ❌ | Expected: possibly ✅ | Expected: ❌ (redirects handle) |
| **Totals** | | | |
| Manual commands executed | Expected: 0 | Expected: 0–2 | Expected: 0–2 |
| Operator interventions | Expected: 0 | Expected: 0–1 | Expected: 0–1 |
| **Total operator time** | ___ min | ___ min | ___ min |

---

## Scenario 3: Node Reboot / Node Loss

| Step | Redis Enterprise | OSS Sentinel | OSS Cluster |
|---|---|---|---|
| **Pre-disruption** | | | |
| Record topology snapshot | `capture_topology` (scripted) | `capture_topology` (scripted) | `capture_topology` (scripted) |
| **During disruption** | | | |
| Stop node | `docker stop re-node-2` | `docker stop redis-replica-1` | `docker stop redis-node-3` |
| Wait for detection | Automatic | Sentinel timeout (~30s default) | Cluster timeout (~15s default) |
| Manual intervention during outage? | Expected: ❌ | Expected: possibly ✅ | Expected: possibly ✅ |
| **Recovery** | | | |
| Restart node | `docker start re-node-2` | `docker start redis-replica-1` | `docker start redis-node-3` |
| Node auto-rejoins cluster? | Expected: ✅ | Expected: ✅ (if config intact) | Expected: ✅ (if cluster-config intact) |
| Manual rejoin commands needed? | Expected: ❌ | Expected: possibly `REPLICAOF` | Expected: possibly `CLUSTER MEET` |
| Slot/shard rebalancing needed? | Expected: ❌ (automatic) | N/A (no slots) | Expected: possibly `CLUSTER REBALANCE` |
| Data resync automatic? | Expected: ✅ | Expected: ✅ (partial sync) | Expected: ✅ (partial sync) |
| Verify cluster health post-recovery | `make re-status` | `SENTINEL masters` + `INFO replication` | `CLUSTER INFO` + `CLUSTER NODES` |
| **Totals** | | | |
| Manual commands executed | Expected: 0 | Expected: 0–3 | Expected: 0–4 |
| Operator interventions | Expected: 0 | Expected: 0–2 | Expected: 0–2 |
| **Total operator time** | ___ min | ___ min | ___ min |

---

## Scenario 4: Rolling Upgrade Under Load

| Step | Redis Enterprise | OSS Sentinel | OSS Cluster |
|---|---|---|---|
| **Preparation** | | | |
| Document rollback plan | 1 step: `rladmin upgrade rollback` | Per-node rollback procedure | Per-node rollback procedure |
| Stage new binary/image | Pull new RE image | Pull new Redis image per node | Pull new Redis image per node |
| **Execution** | | | |
| Initiate upgrade | Single command or Operator-managed | Manual per-node: stop → upgrade → start | Manual per-node: stop → upgrade → start |
| Nodes upgraded simultaneously? | Automatic rolling (one at a time) | Manual sequencing required | Manual sequencing required |
| Health check between nodes? | Automatic | Operator must verify: `INFO replication`, `SENTINEL masters` | Operator must verify: `CLUSTER INFO`, `CLUSTER NODES` |
| Client impact per node? | Expected: zero downtime | Expected: brief disconnect per node | Expected: brief disconnect + MOVED redirects |
| **Per-node operator steps (OSS)** | | | |
| 1. Identify next node | N/A (automatic) | Manual | Manual |
| 2. Graceful shutdown | N/A | `redis-cli SHUTDOWN NOSAVE` | `redis-cli SHUTDOWN NOSAVE` |
| 3. Replace binary | N/A | Manual file/image swap | Manual file/image swap |
| 4. Start new process | N/A | `redis-server /path/to/conf` | `redis-server /path/to/conf` |
| 5. Verify rejoined | N/A | `INFO replication` | `CLUSTER NODES` |
| 6. Wait for sync | N/A | Monitor `master_sync_in_progress` | Monitor `cluster_state` |
| **Totals** | | | |
| Commands per node | 0 (automatic) | ~4–6 | ~4–6 |
| Total commands (3-node cluster) | 1 (initiate) | ~12–18 | ~18–24 (more nodes) |
| Operator interventions | 1 | 3+ (one per node minimum) | 6+ (one per node minimum) |
| Risk of misconfiguration | Low | Medium — wrong config path, missed node | Medium — slot ownership errors |
| **Total operator time** | ___ min | ___ min | ___ min |

---

## Summary Comparison

| Metric | Redis Enterprise | OSS Sentinel | OSS Cluster |
|---|---|---|---|
| **Scenario 1** — Manual commands | 0 | 0 | 0 |
| **Scenario 2** — Manual commands | 0 | 0–2 | 0–2 |
| **Scenario 2** — Operator interventions | 0 | 0–1 | 0–1 |
| **Scenario 3** — Manual commands | 0 | 0–3 | 0–4 |
| **Scenario 3** — Operator interventions | 0 | 0–2 | 0–2 |
| **Scenario 4** — Commands per upgrade | 1 | 12–18 | 18–24 |
| **Scenario 4** — Operator interventions | 1 | 3+ | 6+ |
| **Scenario 4** — Misconfiguration risk | Low | Medium | Medium |
| **Total expected interventions** | 1–2 | 3–8 | 6–13 |

---

## Recording Template

Copy this block for each run and fill in actuals:

```
Run ID:        _______________
Scenario:      _______________
Platform:      _______________
Date/Time:     _______________

Manual commands executed (list each):
1. _______________
2. _______________
3. _______________

Total operator interventions: ___
Total operator time: ___ minutes
Commands outside scripted path: ___

Notes:
_______________________________________________
```

