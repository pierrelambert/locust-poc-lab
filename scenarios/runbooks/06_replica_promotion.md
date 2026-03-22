# Runbook: Scenario 6 — Scale-Out / Replica Promotion Under Load

**Category:** Operations  
**Script:** `scenarios/scripts/06_replica_promotion.sh`  
**Minimum runs:** 3 per platform

## Purpose

Demonstrate whether the platform can expand capacity or promote replicas without disrupting running workloads. Tests rebalancing behavior, slot migration impact, MOVED/ASK redirections, and operator effort required for topology changes under load.

## Prerequisites

- [ ] Steady-state baseline (Scenario 1) completed and results saved
- [ ] Workload running at target rate
- [ ] All nodes healthy and replication in sync
- [ ] Additional node or pod capacity available (for add_node mode)
- [ ] Current slot/shard distribution documented
- [ ] Dashboard confirmed receiving metrics

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM` | Yes | — | `re`, `oss-sentinel`, or `oss-cluster` |
| `LOCUST_FILE` | Yes | — | Path to the Locustfile |
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name |
| `SCALE_MODE` | No | `promote_replica` | `promote_replica` or `add_node` |
| `REPLICA_CONTAINER` | Conditional | — | Replica to promote (required for `promote_replica`) |
| `NEW_NODE_CONTAINER` | Conditional | — | New node to add (required for `add_node`) |
| `POST_RECOVERY_DURATION` | No | `300` | Post-scale observation window (seconds) |
| `BASELINE_DURATION` | No | `600` | Pre-disruption baseline duration (seconds) |
| `WARMUP_DURATION` | No | `60` | Warmup duration (seconds) |
| `SENTINEL_CONTAINER` | No | `sentinel-1` | Sentinel container (oss-sentinel only) |

## Execution

### Quick start — Replica promotion

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-primary \
REPLICA_CONTAINER=redis-replica-1 \
SCALE_MODE=promote_replica \
./scenarios/scripts/06_replica_promotion.sh
```

### Quick start — Scale-out (add node)

```bash
PLATFORM=oss-cluster \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-node-1 \
NEW_NODE_CONTAINER=redis-node-4 \
SCALE_MODE=add_node \
./scenarios/scripts/06_replica_promotion.sh
```

### What the script does

1. Verifies environment parity and dataset
2. Runs warmup (discards data)
3. Captures steady-state baseline
4. Starts continuous workload
5. **Executes the scale operation:**
   - `promote_replica`: Triggers failover via Sentinel or CLUSTER FAILOVER
   - `add_node`: Starts new container, adds to cluster, triggers rebalance
6. Monitors recovery and stable state
7. Runs post-scale observation
8. Exports evidence and operator effort summary

### Injection method

- **Enterprise:** `rladmin node add` + `rladmin shard migrate` or Operator replica count increase
- **OSS Sentinel:** `SENTINEL failover mymaster` for promotion; `docker start` + `REPLICAOF` for add
- **OSS Cluster:** `CLUSTER FAILOVER` for promotion; `CLUSTER MEET` + `--cluster rebalance` for add

## Expected Behavior

### Redis Enterprise

- Smooth shard migration with minimal latency impact
- Automatic rebalancing, no client-visible errors
- Single operational workflow

### OSS Redis (Sentinel)

- Failover promotion triggers reconnection
- New replica requires manual `REPLICAOF` configuration
- Sentinel must discover new topology

### OSS Redis (Cluster)

- Manual slot migration with potential latency spikes
- Client may see MOVED/ASK redirections during rebalance
- Operator must monitor and verify slot distribution
- Higher risk of uneven distribution

## Evidence Checklist

- [ ] `events.jsonl` — timeline of scale operation and recovery
- [ ] `topology_pre_scale.txt` — topology before scale operation
- [ ] `topology_post_scale.txt` — topology after scale operation
- [ ] `topology_final.txt` — topology after stability observation
- [ ] `operator_effort.json` — total steps, duration, mode
- [ ] Locust CSV files — throughput, latency, errors during scale
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_*.txt` — Redis INFO snapshots at key moments

## Operator Actions to Record

Document every manual step taken during the scenario:

- [ ] Node addition commands executed
- [ ] Rebalance or slot migration commands
- [ ] Health verification steps between operations
- [ ] Client-side adjustments needed
- [ ] Total operator time
- [ ] Commands executed outside the scripted path

## Key Metrics to Compare

| Metric | What it shows |
|---|---|
| Latency during topology change | Impact of scale operation |
| Rebalance duration | Time to reach stable distribution |
| Throughput impact during migration | Service continuity |
| Error rate during scale event | Client-visible disruption |
| Final slot/shard distribution | Balance quality |
| Operator time and effort | Operational complexity |

## Scorecard Questions

1. **What happened?** — Scale operation under load; describe the topology change
2. **What did the application feel?** — MOVED/ASK redirections, latency spikes, error bursts
3. **Which platform made it faster or simpler?** — Compare operator steps, duration, automation

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Rebalance not completing | Slot migration stuck | Check `CLUSTER INFO` for migrating slots |
| MOVED errors persist | Client cache stale | Restart client or refresh slot map |
| New node not joining cluster | Network or auth issue | Verify connectivity and `requirepass` |
| Uneven slot distribution | Rebalance incomplete | Run `--cluster rebalance` again |
| Sentinel not discovering new topology | Sentinel config stale | Check `SENTINEL masters` output |

