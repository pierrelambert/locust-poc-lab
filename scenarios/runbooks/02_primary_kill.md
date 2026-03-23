# Runbook: Scenario 2 — Primary Process Kill

**Category:** Failure  
**Script:** `scenarios/scripts/02_primary_kill.sh`  
**Minimum runs:** 3 per platform

## Purpose

Simple HA proof — kills the primary Redis container and measures failover quality, recovery time, and client impact. This is the core scenario for demonstrating the difference in high-availability behavior between Redis Enterprise and OSS Redis.

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
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name to kill |
| `LOCUST_USERS` | No | `10` | Number of simulated users |
| `LOCUST_SPAWN_RATE` | No | `2` | User spawn rate |
| `LOCUST_HOST` | No | `redis://localhost:6379` | Redis host URL |
| `WORKLOAD_PROFILE` | No | — | Path to workload profile YAML |
| `BASELINE_DURATION` | No | `600` | Pre-disruption baseline in seconds |
| `WARMUP_DURATION` | No | `60` | Warmup duration in seconds |
| `POST_RECOVERY_DURATION` | No | `300` | Post-recovery observation in seconds |
| `SENTINEL_CONTAINER` | No | `sentinel1` | Sentinel container (oss-sentinel only) |
| `REPLICA_CONTAINER` | No | `redis-node2` | Fallback container for cluster state checks |

## Execution

### Quick start

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-primary \
SENTINEL_CONTAINER=sentinel1 \
POST_RECOVERY_DURATION=300 \
./scenarios/scripts/02_primary_kill.sh
```

### What the script does

1. Verifies environment parity and dataset
2. Checks the dataset is primed
3. Runs warmup (discards data)
4. Captures steady-state baseline
5. Starts continuous workload
6. **Kills the primary container** (`docker kill`)
7. Records kill event timestamp for Grafana correlation
8. Polls for failover completion (platform-specific detection)
9. Captures post-failover topology
10. Runs post-recovery observation (default 5 minutes)
11. Stops workload and captures final topology
12. Exports evidence

### Injection method

- **Docker:** `docker kill <primary_container>`
- **Kubernetes:** `kubectl delete pod <primary_pod>` and let the operator/scheduler handle recovery

## Expected Behavior

### Redis Enterprise

- Automatic detection and failover in seconds
- Minimal or zero client errors during transition
- Short p99 latency spike, quick return to baseline
- No operator intervention required
- Replication re-sync handled automatically

### OSS Redis (Sentinel)

- Sentinel detects primary loss after `down-after-milliseconds` timeout (typically 30s)
- Sentinel election and replica promotion triggered
- Higher error count during failover window
- Larger latency spike, slower return to baseline
- Client reconnection may be required
- Operator may need to verify topology post-failover

### OSS Redis (Cluster)

- Cluster protocol detects loss after `cluster-node-timeout`
- Replica promotion for affected slots
- MOVED/ASK redirections during transition
- Longer recovery window expected
- Operator may need to verify slot ownership

## Evidence Checklist

- [ ] `events.jsonl` — timeline of kill, failover detection, recovery
- [ ] `topology_pre_kill.txt` — topology before disruption
- [ ] `topology_post_failover.txt` — topology after failover
- [ ] `topology_final.txt` — topology after stability observation
- [ ] Locust CSV files — throughput, latency, errors during disruption
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_pre_kill.txt` — Redis INFO before kill
- [ ] `run_summary.json` — machine-readable summary
- [ ] `run_summary.md` — human-readable report

## Operator Actions to Record

Document every manual step taken during the scenario:

- [ ] Was any manual failover intervention required?
- [ ] Were client-side recovery actions needed?
- [ ] Were configuration changes required post-failover?
- [ ] How long did diagnosis take?
- [ ] How many commands were executed outside the scripted path?
- [ ] Was the killed container restarted manually?

## Scorecard Questions

1. **What happened?** — Primary container was killed; describe each platform's automatic response and failover timeline
2. **What did the application feel?** — Error burst duration, latency spike magnitude, throughput drop, time to recover to 95% baseline throughput
3. **Which platform made recovery faster or simpler?** — Compare failover duration, error count, operator steps, and total recovery time

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Failover not detected within timeout | Sentinel/Cluster timeout too high | Check `down-after-milliseconds` or `cluster-node-timeout` |
| Sentinel quorum not met | Too few sentinels running | Verify sentinel count with `SENTINEL ckquorum mymaster` |
| Locust errors persist after failover | Client connection pool pointing to old primary | Check client reconnect behavior and host configuration |
| Cluster state not OK after kill | Insufficient replicas for slot coverage | Ensure replicas exist for all primary shards |
| RE failover not detected by script | Script polling heuristic too simple | Check `rladmin status` manually for actual failover state |

