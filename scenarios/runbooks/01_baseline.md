# Runbook: Scenario 1 — Steady-State Baseline

**Category:** Baseline  
**Script:** `scenarios/scripts/01_baseline.sh`  
**Minimum runs:** 3 per platform

## Purpose

Establish normal SLA behavior before any disruption is introduced. This baseline captures steady-state throughput, latency percentiles, error rate, and resource utilization. All subsequent scenario comparisons reference these numbers to quantify the impact of failures and operational events.

## Prerequisites

- [ ] Platform stack running (`make re-up`, `make oss-sentinel-up`, or `make oss-cluster-up`)
- [ ] Dataset primed (the script warns if the database is empty)
- [ ] Observability stack running (`make obs-up`)
- [ ] Grafana dashboard confirmed receiving metrics
- [ ] All nodes healthy and replication in sync

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLATFORM` | Yes | — | `re`, `oss-sentinel`, or `oss-cluster` |
| `LOCUST_FILE` | Yes | — | Path to the Locustfile |
| `PRIMARY_CONTAINER` | Yes | — | Primary Redis container name |
| `LOCUST_USERS` | No | `10` | Number of simulated users |
| `LOCUST_SPAWN_RATE` | No | `2` | User spawn rate |
| `LOCUST_HOST` | No | `redis://localhost:6379` | Redis host URL |
| `WORKLOAD_PROFILE` | No | — | Path to workload profile YAML |
| `BASELINE_DURATION` | No | `600` | Baseline run duration in seconds |
| `WARMUP_DURATION` | No | `60` | Warmup duration in seconds |
| `SENTINEL_CONTAINER` | No | `sentinel1` | Sentinel container (oss-sentinel only) |

## Execution

### Quick start

```bash
PLATFORM=oss-sentinel \
LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py \
PRIMARY_CONTAINER=redis-primary \
BASELINE_DURATION=600 \
./scenarios/scripts/01_baseline.sh
```

### What the script does

1. Verifies environment parity and records metadata
2. Checks the dataset is primed (warns if empty)
3. Captures pre-warmup Redis INFO
4. Runs warmup (discards data)
5. Captures pre-baseline Redis INFO and topology
6. Runs steady-state baseline (default 10 minutes)
7. Captures post-baseline Redis INFO and topology
8. No disruption — confirms stability
9. Exports evidence
10. Reminds you to repeat at least 3 times

## Expected Behavior

### Redis Enterprise

- Flat, stable throughput throughout the run
- Low and consistent p50/p95/p99 latency
- Zero errors
- Stable memory and connection counts

### OSS Redis (Sentinel)

- Flat, stable throughput throughout the run
- Low and consistent p50/p95/p99 latency
- Zero errors
- Stable memory and connection counts
- Sentinel quorum healthy throughout

### OSS Redis (Cluster)

- Flat, stable throughput throughout the run
- Low and consistent p50/p95/p99 latency
- Zero errors
- Stable memory and connection counts
- Cluster state OK throughout

## Evidence Checklist

- [ ] `events.jsonl` — timeline of warmup, baseline start/end
- [ ] `topology_pre_baseline.txt` — topology before baseline
- [ ] `topology_post_baseline.txt` — topology after baseline
- [ ] Locust CSV files — throughput, latency, errors (should show zero errors)
- [ ] `environment.json` — platform and configuration metadata
- [ ] `redis_info_pre_warmup.txt` — Redis INFO before warmup
- [ ] `redis_info_pre_baseline.txt` — Redis INFO before baseline
- [ ] `redis_info_post_baseline.txt` — Redis INFO after baseline
- [ ] `run_summary.json` — machine-readable summary
- [ ] `run_summary.md` — human-readable report

## Scorecard Questions

1. **What happened?** — No disruption; describe steady-state behavior and confirm metrics were stable throughout
2. **What did the application feel?** — Consistent throughput, low latency, zero errors — this is the reference point
3. **Are both platforms comparable at baseline?** — Confirm similar steady-state performance to ensure a fair starting point for disruption scenarios

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Database is empty warning | Dataset not primed | Run the data priming step before baseline |
| Throughput not stable | Warmup too short or system under-provisioned | Increase `WARMUP_DURATION` or check resource allocation |
| Non-zero error rate | Connectivity or configuration issue | Verify Redis is reachable and Locust host is correct |
| Latency spikes during baseline | Background processes or resource contention | Check for competing workloads on the host |
| Locust fails to start | Missing dependencies or invalid Locustfile path | Run `make setup` and verify `LOCUST_FILE` path |
| Metrics not appearing in Grafana | Exporter or Prometheus misconfigured | Run `make obs-status` and check Prometheus targets |

