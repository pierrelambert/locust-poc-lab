# Runbook: Scenario 5 — Network Partition

**Category:** Failure  
**Script:** `scenarios/scripts/05_network_partition.sh`  
**Minimum runs:** 3 per platform

## Purpose

Demonstrate split-brain behavior, write safety, and diagnostic clarity under a network partition — the most challenging failure mode. This tests quorum-based decisions, write rejection on the minority side, and automatic healing when the partition resolves.

## Prerequisites

- [ ] Steady-state baseline (Scenario 1) completed and results saved
- [ ] Workload running at target rate
- [ ] Network topology documented
- [ ] Partition recovery plan ready
- [ ] All nodes healthy and replication in sync
- [ ] Dashboard confirmed receiving metrics

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM` | Yes | — | `re`, `oss-sentinel`, or `oss-cluster` |
| `LOCUST_FILE` | Yes | — | Path to the Locustfile |
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name |
| `PARTITION_TARGET` | Yes | — | Container to isolate via network partition |
| `PARTITION_DURATION` | No | `60` | Duration of the partition in seconds |
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
PARTITION_TARGET=redis-primary \
PARTITION_DURATION=60 \
./scenarios/scripts/05_network_partition.sh
```

### What the script does

1. Verifies environment parity and dataset
2. Runs warmup (discards data)
3. Captures steady-state baseline
4. Starts continuous workload
5. **Disconnects the target container from all Docker networks**
6. Monitors split behavior during partition (which side accepts writes)
7. **Reconnects the container after the configured duration**
8. Monitors recovery (failover detection, replication re-sync)
9. Runs post-recovery observation
10. Exports evidence

### Injection method

- **Docker:** `docker network disconnect` / `docker network connect` to isolate and restore the target container
- **VM/bare-metal:** `iptables -A INPUT -s <target_ip> -j DROP && iptables -A OUTPUT -d <target_ip> -j DROP`
- **Kubernetes:** Network policy injection via `kubectl apply -f partition-policy.yaml`

## Expected Behavior

### Redis Enterprise

- Quorum-based decision — minority side rejects writes
- Clear diagnostic events in logs
- Automatic healing when partition resolves
- No data loss or conflicting writes

### OSS Redis (Sentinel)

- Sentinel may elect conflicting primaries (split-brain risk)
- Risk of writes accepted on both sides of the partition
- Manual resolution likely required after healing
- Less diagnostic clarity — harder to understand what happened

### OSS Redis (Cluster)

- Cluster protocol may mark slots as failed
- Nodes on minority side stop accepting writes after `cluster-node-timeout`
- Risk of conflicting writes during the timeout window
- Manual `CLUSTER MEET` may be needed after healing

## Evidence Checklist

- [ ] `events.jsonl` — timeline of partition inject, monitor, heal, recovery
- [ ] `topology_pre_partition.txt` — topology before disruption
- [ ] `topology_post_recovery.txt` — topology after partition heals
- [ ] `topology_final.txt` — topology after stability observation
- [ ] `partitioned_networks.txt` — Docker networks disconnected
- [ ] Locust CSV files — throughput, latency, errors during partition
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_*.txt` — Redis INFO snapshots at key moments

## Operator Actions to Record

Document every manual step taken during the scenario:

- [ ] Was split-brain detected? Which side accepted writes?
- [ ] Were conflicting or lost writes identified?
- [ ] What diagnostic steps were needed to understand the partition?
- [ ] Were manual resolution commands required after healing?
- [ ] Was data reconciliation needed?
- [ ] How long did diagnosis take?
- [ ] How many commands were executed outside the scripted path?

## Key Metrics to Compare

| Metric | What it shows |
|---|---|
| Write safety | Whether writes were lost or conflicted |
| Split behavior | Which side accepted writes during partition |
| Diagnostic event quality | How clear the platform's logs/events are |
| Time to detect partition | Platform awareness speed |
| Time to heal after resolution | Automatic recovery capability |
| Data consistency post-heal | Whether all data is intact |

## Scorecard Questions

1. **What happened?** — Network partition isolated a node for N seconds; describe split behavior
2. **What did the application feel?** — Error rate, write failures, latency during partition and recovery
3. **Which platform made recovery faster or simpler?** — Compare write safety, diagnostic clarity, and manual effort

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Container won't reconnect to network | Docker network state stale | Restart Docker daemon or recreate network |
| Split-brain writes detected | No quorum enforcement | Document as expected OSS behavior |
| Recovery not detected after heal | Sentinel/Cluster timeout too high | Check timeout configuration |
| Replication diverged | Conflicting writes during partition | Manual data reconciliation needed |
| Locust errors persist after heal | Client connected to wrong primary | Restart client or check connection pool |

