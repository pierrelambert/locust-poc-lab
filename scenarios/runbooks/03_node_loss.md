# Runbook: Scenario 3 — Node Reboot or Node Loss

**Category:** Failure  
**Script:** `scenarios/scripts/03_node_loss.sh`  
**Minimum runs:** 3 per platform

## Purpose

Demonstrate recovery behavior when a full Redis node disappears and returns. This tests automatic detection, failover (if the lost node is a primary), replica re-sync, and operator effort required to restore the cluster to a healthy state.

## Prerequisites

- [ ] Steady-state baseline (Scenario 1) completed and results saved
- [ ] Workload running at target rate
- [ ] Topology snapshot taken (the script captures this automatically)
- [ ] All nodes healthy and replication in sync
- [ ] Dashboard confirmed receiving metrics

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM` | Yes | — | `re`, `oss-sentinel`, or `oss-cluster` |
| `LOCUST_FILE` | Yes | — | Path to the Locustfile |
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name |
| `NODE_CONTAINER` | Yes | — | Container to stop/start (can be primary or replica) |
| `NODE_DOWN_DURATION` | No | `30` | Seconds the node stays down |
| `POST_RECOVERY_DURATION` | No | `300` | Post-recovery observation window (seconds) |
| `BASELINE_DURATION` | No | `600` | Pre-disruption baseline duration (seconds) |
| `WARMUP_DURATION` | No | `60` | Warmup duration (seconds) |
| `SENTINEL_CONTAINER` | No | `sentinel1` | Sentinel container (oss-sentinel only) |
| `REPLICA_CONTAINER` | No | `redis-node2` | Fallback container for cluster state checks |

## Execution

### Quick start

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-primary \
NODE_CONTAINER=redis-primary \
NODE_DOWN_DURATION=30 \
./scenarios/scripts/03_node_loss.sh
```

### What the script does

1. Verifies environment parity and dataset
2. Runs warmup (discards data)
3. Captures steady-state baseline
4. Starts continuous workload
5. **Stops the target node** (`docker stop`)
6. Waits for the configured down duration
7. **Restarts the node** (`docker start`)
8. Monitors recovery (failover detection, replication re-sync)
9. Runs post-recovery observation
10. Exports evidence

### Injection method

- **Docker:** `docker stop <node_container> && sleep <duration> && docker start <node_container>`
- **Kubernetes:** `kubectl delete pod <node_pod>` and let the scheduler reschedule

## Expected Behavior

### Redis Enterprise

- Automatic detection and recovery
- Cluster resharding or replica promotion handled internally
- Operator notified but not required to act
- Replication re-sync happens automatically

### OSS Redis (Sentinel)

- Sentinel detects loss after timeout (typically 30s default `down-after-milliseconds`)
- Failover triggered if the lost node is the primary
- Returning node must re-sync; may require manual `REPLICAOF` if topology changed
- Operator may need to verify and rejoin the node

### OSS Redis (Cluster)

- Cluster protocol detects loss after `cluster-node-timeout`
- Replica promotion for affected slots
- Returning node may need manual slot migration or `CLUSTER MEET`
- Longer recovery window expected

## Evidence Checklist

- [ ] `events.jsonl` — timeline of stop, down window, restart, recovery
- [ ] `topology_pre_node_loss.txt` — topology before disruption
- [ ] `topology_post_recovery.txt` — topology after node returns
- [ ] `topology_final.txt` — topology after stability observation
- [ ] `replication_sync_post_recovery.txt` — replication state after recovery
- [ ] Locust CSV files — throughput, latency, errors during disruption
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_*.txt` — Redis INFO snapshots at key moments

## Operator Actions to Record

Document every manual step taken during the scenario:

- [ ] Was any manual node rejoin required?
- [ ] Were slot rebalancing commands needed? (oss-cluster)
- [ ] Were configuration file edits required?
- [ ] Were client-side recovery actions needed?
- [ ] How long did diagnosis take?
- [ ] How many commands were executed outside the scripted path?

## Scorecard Questions

1. **What happened?** — Node was stopped for N seconds then restarted; describe the system's automatic response
2. **What did the application feel?** — Error burst duration, latency spike magnitude, throughput drop
3. **Which platform made recovery faster or simpler?** — Compare automatic vs manual recovery steps and total time

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Recovery not detected within timeout | Sentinel/Cluster timeout too high | Check `down-after-milliseconds` or `cluster-node-timeout` |
| Node won't rejoin after restart | Stale configuration | Clear node data dir and re-add to cluster |
| Replication not syncing | Full resync needed | Check `redis_info` for `master_sync_in_progress` |
| Locust errors persist after recovery | Client connection pool stale | Check client reconnect behavior |
