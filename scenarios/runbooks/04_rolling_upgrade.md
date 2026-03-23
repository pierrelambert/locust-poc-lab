# Runbook: Scenario 4 — Rolling Upgrade Under Load

**Category:** Operations  
**Script:** `scenarios/scripts/04_rolling_upgrade.sh`  
**Minimum runs:** 3 per platform

## Purpose

Demonstrate whether maintenance can happen without service disruption. This scenario performs a sequential node-by-node restart under continuous workload, measuring service continuity, latency impact per node, total upgrade duration, and operator effort.

## Prerequisites

- [ ] Steady-state baseline (Scenario 1) completed and results saved
- [ ] Workload running at target rate
- [ ] All nodes healthy and replication in sync
- [ ] Upgrade target version available (or simulated via restart)
- [ ] Rollback plan documented
- [ ] Dashboard confirmed receiving metrics

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM` | Yes | — | `re`, `oss-sentinel`, or `oss-cluster` |
| `LOCUST_FILE` | Yes | — | Path to the Locustfile |
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name |
| `NODE_CONTAINERS` | Yes | — | Space-separated list of containers to restart in order |
| `NODE_RESTART_PAUSE` | No | `15` | Pause between node restarts (seconds) |
| `POST_RECOVERY_DURATION` | No | `300` | Post-upgrade observation window (seconds) |
| `BASELINE_DURATION` | No | `600` | Pre-disruption baseline duration (seconds) |
| `WARMUP_DURATION` | No | `60` | Warmup duration (seconds) |
| `SENTINEL_CONTAINER` | No | `sentinel1` | Sentinel container (oss-sentinel only) |

## Execution

### Quick start

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-primary \
NODE_CONTAINERS="redis-replica1 redis-replica2 redis-primary" \
NODE_RESTART_PAUSE=15 \
./scenarios/scripts/04_rolling_upgrade.sh
```

### Recommended node order

- **Replicas first, primary last** — minimizes failover events
- For OSS Cluster: restart nodes that own fewer slots first
- For RE: the platform handles shard migration automatically

### What the script does

1. Verifies environment parity and dataset
2. Runs warmup (discards data)
3. Captures steady-state baseline
4. Starts continuous workload
5. **For each node in order:**
   - Captures pre-restart Redis INFO
   - Stops the node (`docker stop`)
   - Pauses briefly (simulates binary swap)
   - Starts the node (`docker start`)
   - Waits for Redis to respond
   - Runs platform-specific health check
   - Pauses before next node
6. Captures post-upgrade topology and replication state
7. Runs post-upgrade observation
8. Exports evidence and operator effort summary

### Injection method

- **Enterprise:** `rladmin upgrade` or Operator-managed rolling restart
- **OSS Docker:** Sequential `docker stop` / `docker start` per node
- **OSS Kubernetes:** `kubectl rollout restart` or sequential pod deletion

## Expected Behavior

### Redis Enterprise

- Zero-downtime rolling upgrade
- Automatic shard migration during node maintenance
- Continuous service with minor latency variation
- Single operator command (`rladmin upgrade`)

### OSS Redis (Sentinel)

- Per-node manual restart required
- Failover triggered when primary is restarted
- Operator must verify sentinel quorum between steps
- Potential client disconnections per node restart

### OSS Redis (Cluster)

- Per-node manual restart required
- Slot ownership must be verified between restarts
- Client may see MOVED/ASK redirections during transitions
- Operator must monitor cluster health between steps
- Higher risk of misconfiguration

## Evidence Checklist

- [ ] `events.jsonl` — timeline of each node stop/start/health-check
- [ ] `topology_pre_rolling_upgrade.txt` — topology before upgrade
- [ ] `topology_post_rolling_upgrade.txt` — topology after all restarts
- [ ] `topology_final.txt` — topology after stability observation
- [ ] `replication_sync_post_upgrade.txt` — replication state per node
- [ ] `operator_effort.json` — total steps, duration, node count
- [ ] Locust CSV files — throughput, latency, errors per node restart
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_*.txt` — Redis INFO snapshots at key moments

## Operator Actions to Record

Document every manual step taken during the scenario:

- [ ] Every command executed per node
- [ ] Time per node restart
- [ ] Health checks performed between nodes
- [ ] Rollback actions if needed
- [ ] Total operator time
- [ ] Commands executed outside the scripted path

## Key Metrics to Compare

| Metric | What it shows |
|---|---|
| Error rate during upgrade window | Service continuity |
| Latency spikes per node restart | Per-node impact |
| Total upgrade duration | Operational efficiency |
| Operator steps count | Automation level |
| Commands outside scripted path | Operational complexity |

## Scorecard Questions

1. **What happened?** — N nodes restarted sequentially under load; describe per-node impact
2. **What did the application feel?** — Error bursts per restart, cumulative latency impact, total disruption window
3. **Which platform made recovery faster or simpler?** — Compare operator steps, total duration, and automation level

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Node won't come back after restart | Port conflict or data corruption | Check logs, verify data directory |
| Cluster state not OK between restarts | Insufficient replicas for slot coverage | Ensure enough replicas before starting |
| Sentinel failover not completing | Quorum not met | Verify sentinel count and connectivity |
| Increasing latency across restarts | Replication backlog building up | Increase pause between restarts |
| Client errors persist after all restarts | Connection pool exhaustion | Check client reconnect configuration |
