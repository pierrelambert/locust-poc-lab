# Workload Catalog for Locust

**Last updated:** March 22, 2026
**Status:** Phase 1 specification

## 1. Purpose

This catalog defines the standard Locust workload profiles used across all POC lab scenarios. Each workload maps to a real customer narrative and provides enough implementation detail for a developer to write the corresponding Locustfile.

All workloads share a common configuration schema (Section 3) and follow the design rules in Section 4.

## 2. Workload Profiles

### 2.1 `cache_read_heavy`

**Business narrative:** A product catalog or content cache serving high-volume read traffic with occasional cache invalidation writes. This is the most common Redis use case and the simplest proof of failover impact on read-heavy applications.

| Property | Value |
|---|---|
| Read/write ratio | 90/10 |
| Redis commands (read) | `GET`, `MGET` |
| Redis commands (write) | `SET` with TTL, `DEL` |
| Key pattern | `cache:{category}:{item_id}` |
| Key space size | 100,000 keys (seeded) |
| Value size | 512 bytes – 2 KB (JSON payload) |
| Think time | 5–20 ms (uniform random) |
| Target RPS range | 5,000 – 50,000 |
| TTL | 300–900 seconds (random) |

**Key behaviors to observe:** hit ratio, tail latency, recovery after failover.

**Data seeding requirements:**
- Pre-populate 100,000 keys with randomized JSON payloads before the test begins.
- Keys must be distributed across the full key space to avoid slot imbalance in cluster mode.
- Seeding must complete and be verified before the warm-up phase starts.

---

### 2.2 `session_mixed`

**Business narrative:** A login and session-state store where users authenticate, read session data on every request, and periodically update session attributes. Demonstrates reconnect behavior and the risk of stale or lost sessions during failover.

| Property | Value |
|---|---|
| Read/write ratio | 70/30 |
| Redis commands (read) | `HGETALL`, `HGET`, `TTL` |
| Redis commands (write) | `HSET`, `HMSET`, `EXPIRE`, `DEL` |
| Key pattern | `session:{user_id}` |
| Key space size | 50,000 keys (seeded) |
| Value size | 256 bytes – 1 KB (hash with 5–10 fields) |
| Think time | 10–50 ms (uniform random) |
| Target RPS range | 2,000 – 20,000 |
| TTL | 1,800 seconds (session timeout) |

**Key behaviors to observe:** reconnect behavior, write continuity, stale session risk.

**Data seeding requirements:**
- Pre-populate 50,000 session hashes with realistic field sets (user_id, role, preferences, last_active, csrf_token).
- Each session must have a TTL set to simulate natural expiration.
- Verify session count matches expected key space before starting the workload.

---

### 2.3 `counter_hotkey`

**Business narrative:** Inventory counters, rate limiters, or real-time metrics where a subset of keys receives disproportionate write traffic. Demonstrates hot-key pressure, latency spikes under contention, and failover sensitivity when write-heavy keys move between nodes.

| Property | Value |
|---|---|
| Read/write ratio | 60/40 |
| Redis commands (read) | `GET`, `MGET` |
| Redis commands (write) | `INCR`, `INCRBY`, `DECR`, `SET` |
| Key pattern | `counter:{scope}:{counter_id}` |
| Key space size | 10,000 keys total; 100 hot keys receive 80% of traffic |
| Value size | 8–64 bytes (integer or small string) |
| Think time | 1–5 ms (uniform random) |
| Target RPS range | 10,000 – 100,000 |
| TTL | None (persistent counters) |

**Key behaviors to observe:** hot key pressure, latency spikes, failover sensitivity.

**Data seeding requirements:**
- Pre-populate 10,000 counter keys initialized to zero or a random starting value.
- The 100 hot keys must be explicitly identified and tracked for per-key latency analysis.
- Hot key distribution must follow a Zipfian pattern to simulate realistic access skew.

---

### 2.4 `leaderboard_sorted_set`

**Business narrative:** A ranking system for gaming, e-commerce, or social platforms where scores are updated frequently and leaderboard queries retrieve top-N or rank-range results. Demonstrates sorted-set update latency, cluster balance with large sorted sets, and recovery behavior.

| Property | Value |
|---|---|
| Read/write ratio | 80/20 |
| Redis commands (read) | `ZRANGE`, `ZREVRANGE`, `ZRANK`, `ZSCORE`, `ZCARD` |
| Redis commands (write) | `ZADD`, `ZINCRBY`, `ZREM` |
| Key pattern | `leaderboard:{board_id}` |
| Key space size | 50 leaderboards, each with 10,000–100,000 members |
| Value size | Member: 16–32 bytes (user ID); Score: 8 bytes (float) |
| Think time | 10–30 ms (uniform random) |
| Target RPS range | 1,000 – 15,000 |
| TTL | None (persistent leaderboards) |

**Key behaviors to observe:** sorted-set update latency, cluster balance, recovery.

**Data seeding requirements:**
- Pre-populate 50 sorted sets, each containing 10,000 members with randomized scores.
- Member IDs must be unique across each leaderboard but may repeat across boards.
- Verify cardinality of each sorted set matches the expected member count before starting.

---

### 2.5 `stream_ingest`

**Business narrative:** An event or order pipeline where producers write events to Redis Streams and consumers read them in consumer groups. Demonstrates write durability, consumer lag during disruption, and recovery pacing when the producer resumes after failover.

| Property | Value |
|---|---|
| Read/write ratio | 50/50 |
| Redis commands (write) | `XADD` |
| Redis commands (read) | `XREADGROUP`, `XACK`, `XLEN`, `XINFO GROUPS` |
| Key pattern | `stream:{topic}:{partition}` |
| Key space size | 10 streams, each with 1–3 consumer groups |
| Value size | 256 bytes – 1 KB per stream entry (JSON event payload) |
| Think time | 2–10 ms (uniform random) |
| Target RPS range | 5,000 – 30,000 |
| Max stream length | 100,000 entries (trimmed with `MAXLEN ~`) |

**Key behaviors to observe:** write durability, consumer lag, recovery pacing.

## 3. Configuration Schema

All workload profiles are parameterized via YAML. Each Locustfile reads its configuration from a profile file that follows this schema.

```yaml
# workload_profile.yaml
workload:
  name: "cache_read_heavy"          # Must match a catalog entry
  description: "Product catalog cache simulation"

  connection:
    host: "redis-host"
    port: 6379
    password: "${REDIS_PASSWORD}"    # Environment variable reference
    db: 0
    ssl: false
    socket_timeout: 5.0
    retry_on_timeout: true
    max_connections: 50              # Connection pool size

  key_config:
    pattern: "cache:{category}:{item_id}"
    key_space_size: 100000
    hot_key_count: 0                 # 0 = uniform distribution
    hot_key_percentage: 0            # Percentage of traffic to hot keys

  data_config:
    value_size_min: 512
    value_size_max: 2048
    value_type: "json"               # json | string | integer
    ttl_min: 300
    ttl_max: 900

  traffic_config:
    read_ratio: 90
    write_ratio: 10
    think_time_min_ms: 5
    think_time_max_ms: 20
    think_time_distribution: "uniform"  # uniform | exponential
    target_rps: 10000                   # Target requests per second per worker

  seeding:
    enabled: true
    key_count: 100000
    batch_size: 1000                 # Keys per pipeline batch
    verify_after_seed: true

  replica_reads:
    enabled: false                   # Must be declared explicitly
    policy: "none"                   # none | readonly | prefer_replica
```

### Schema rules

- Every profile must declare `replica_reads.enabled` explicitly. Silent mixing of consistency models is not allowed.
- Connection pooling must be configured consistently across compared stacks.
- Environment variables are supported for secrets using `${VAR_NAME}` syntax.
- The `hot_key_count` and `hot_key_percentage` fields are only meaningful for the `counter_hotkey` workload but must be present (set to 0) in all profiles for schema consistency.
- The `target_rps` value is per Locust worker. Total target RPS = `target_rps × worker_count`.

## 4. Workload Design Rules

These rules apply to all workloads in the catalog and must be followed when implementing Locustfiles.

1. **One client library path per language.** Use the same Redis client library and version across all workloads. Configure connection pooling consistently.

2. **Consistent key naming and data model.** Use the same key patterns and data shapes across compared stacks (Enterprise vs. OSS). Never change the data model between comparison runs.

3. **Explicit replica-read declaration.** Every workload profile must declare whether replica reads are allowed. Do not mix consistency models silently within or across runs.

4. **Realistic pacing over raw throughput.** Prefer realistic think time and request pacing over raw firehose mode unless the scenario is explicitly a saturation test. The `think_time` configuration must be used.

5. **Sufficient data seeding.** Seed enough data to avoid empty-cache benchmark artifacts. Every workload specifies its seeding requirements, and seeding must be verified before the warm-up phase begins.

6. **Deterministic key distribution.** Key selection must use a seeded random number generator so that runs are reproducible. The seed should be configurable in the YAML profile.

7. **Error handling and retry transparency.** Locustfiles must log connection errors, timeouts, and retries as Locust failures. Do not silently swallow errors — they are part of the measurement.

8. **Pipeline and batch consistency.** If one workload uses pipelining or MGET/MSET batching, the same batching strategy must be used on both compared stacks.

## 5. Workload Summary Matrix

| Workload | Read/Write | Commands | Key Pattern | Value Size | Think Time | Target RPS |
|---|---|---|---|---|---|---|
| `cache_read_heavy` | 90/10 | GET, MGET, SET, DEL | `cache:{cat}:{id}` | 512 B – 2 KB | 5–20 ms | 5K–50K |
| `session_mixed` | 70/30 | HGETALL, HGET, HSET, HMSET, EXPIRE, DEL | `session:{uid}` | 256 B – 1 KB | 10–50 ms | 2K–20K |
| `counter_hotkey` | 60/40 | GET, MGET, INCR, INCRBY, DECR, SET | `counter:{scope}:{id}` | 8–64 B | 1–5 ms | 10K–100K |
| `leaderboard_sorted_set` | 80/20 | ZRANGE, ZREVRANGE, ZRANK, ZADD, ZINCRBY | `leaderboard:{bid}` | 16–32 B member | 10–30 ms | 1K–15K |
| `stream_ingest` | 50/50 | XADD, XREADGROUP, XACK, XLEN | `stream:{topic}:{part}` | 256 B – 1 KB | 2–10 ms | 5K–30K |
