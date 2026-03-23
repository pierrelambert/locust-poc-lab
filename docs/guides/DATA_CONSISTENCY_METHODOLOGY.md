# Data Consistency & RTO/RPO Measurement Methodology

This guide explains how the POC lab measures data consistency, Recovery Time
Objective (RTO), and Recovery Point Objective (RPO) during failover and fault
injection scenarios.

---

## Overview

Three tools work together to produce evidence:

| Tool | Purpose | Output |
|------|---------|--------|
| `tooling/canary_writer.py` | Writes canary keys at 10/s during the scenario | `canary_writes.jsonl` |
| `tooling/consistency_checker.py` | Reads keys back post-run, compares with log | `consistency_report.json` |
| `tooling/rto_rpo_report.py` | Computes RTO/RPO from events + canary log | `rto_rpo.json` |

## Definitions

- **RTO (Recovery Time Objective)** — elapsed time from fault injection to the
  first successful canary write after recovery. Measured in seconds.
- **RPO (Recovery Point Objective)** — number of writes lost (failed) during
  the outage window. Also expressed as the time span of the error window.
- **Consistency %** — percentage of successfully-acknowledged writes that are
  readable post-recovery.

## How It Works

### 1. Canary Writer

The `CanaryWriter` runs as a background thread (or standalone process) alongside
the Locust workload. It writes keys of the form `canary:<seq_id>` at a fixed
rate (default 10 writes/second) and logs every attempt to `canary_writes.jsonl`:

```jsonl
{"seq": 1, "key": "canary:1", "ts": 1711234567.123, "iso": "2026-03-23T...", "status": "ok"}
{"seq": 2, "key": "canary:2", "ts": 1711234567.223, "iso": "2026-03-23T...", "status": "error", "error": "ConnectionError: ..."}
```

Each record captures the sequence number, timestamp, and whether the write
succeeded or failed. During a failover, you will see a burst of `"status": "error"`
entries — this is the outage window.

**Connection modes:** The canary writer uses the same `topology_clients.create_client()`
factory as the Locust workloads, so it supports standalone, sentinel, cluster,
and enterprise topologies.

### 2. Consistency Checker

After the scenario completes, the `ConsistencyChecker` scans Redis for all
`canary:*` keys and cross-references them with the write log:

- **Missing keys** — written successfully but not found in Redis (data loss).
- **Unexpected keys** — found in Redis but not in the write log.
- **Out-of-order** — stored timestamp differs significantly from log timestamp.
- **Duplicates** — sequence IDs that appear more than once in the log.

```bash
python -m tooling.consistency_checker \
    --host localhost --port 6379 \
    --canary-log results/run1/canary_writes.jsonl
```

### 3. RTO/RPO Reporter

The `RtoRpoReporter` combines `events.jsonl` (timeline markers from the scenario
script) with `canary_writes.jsonl` to compute:

- **RTO**: finds the fault injection event, then scans canary writes for the
  first successful write after a gap of errors.
- **RPO**: counts all error writes during and after the fault window.

```bash
python -m tooling.rto_rpo_report results/run1
```

## Scenario Integration

The shell helpers in `scenarios/scripts/lib/common.sh` provide `start_canary`
and `stop_canary` functions. A typical scenario script uses them like this:

```bash
source "$(dirname "$0")/lib/common.sh"

setup_run_dir "primary_kill"
check_environment
init_events_log

start_canary          # ← starts canary writer in background
start_locust 600

sleep "$WARMUP_DURATION"
record_event "fault_inject" "killing primary"
# ... inject fault ...
record_event "recovery_complete" "primary recovered"

stop_locust
stop_canary           # ← stops canary writer, runs consistency check
export_evidence
```

## Interpreting Results

### RTO/RPO Report (`rto_rpo.json`)

```json
{
  "rto": {"rto_seconds": 2.341, "first_ok_epoch": 1711234569.464},
  "rpo": {"lost_writes": 23, "rpo_seconds": 2.3}
}
```

- **rto_seconds < 1** — sub-second recovery (typical for Redis Enterprise).
- **rto_seconds 1–5** — acceptable for Sentinel-managed failover.
- **lost_writes = 0** — no data loss during failover.

### Consistency Report (`consistency_report.json`)

```json
{
  "total_written": 6000,
  "total_found": 6000,
  "missing_count": 0,
  "consistency_pct": 100.0
}
```

- **consistency_pct = 100** — all acknowledged writes survived the failover.
- **missing_count > 0** — potential data loss; investigate replication lag.

## CLI Reference

### Canary Writer

```bash
python -m tooling.canary_writer \
    --host localhost --port 6379 \
    --connection-mode standalone \
    --rate 10 --ttl 3600 \
    --output-dir results/run1 \
    --duration 600
```

### Consistency Checker

```bash
python -m tooling.consistency_checker \
    --host localhost --port 6379 \
    --canary-log results/run1/canary_writes.jsonl \
    --output results/run1/consistency_report.json
```

### RTO/RPO Reporter

```bash
python -m tooling.rto_rpo_report results/run1 \
    --output results/run1/rto_rpo.json
```

