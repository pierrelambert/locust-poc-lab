# Failure Scenario Matrix

**Last updated:** March 22, 2026
**Status:** Phase 1 deliverable
**Source:** POC Lab Execution Blueprint, Section 5

## Overview

This matrix defines the standard failure scenarios used in Redis Enterprise vs OSS Redis comparison POCs. Each scenario has a concrete injection method, expected behavior for both platforms, and evidence capture requirements aligned with the Phase 0 measurement standards.

## Day-1 Mandatory Scenarios

The following four scenarios form the minimum viable comparison set. Do not proceed to Day-2 scenarios until these are stable and repeatable.

### Scenario 1: Steady-State Baseline

| Field | Detail |
|---|---|
| **Name** | Steady-State Baseline |
| **Category** | Baseline |
| **Why it matters** | Establishes normal SLA behavior before any disruption; all subsequent comparisons reference this baseline |
| **Injection method** | None — run the selected Locust workload at target rate for a minimum of 10 minutes with no disruption |
| **Preconditions** | Dataset primed, workload warmed up, all nodes healthy, dashboards confirmed receiving metrics |
| **Expected Enterprise behavior** | Stable latency within declared SLA, consistent throughput, zero errors, clean dashboard |
| **Expected OSS behavior** | Stable latency within declared SLA, consistent throughput, zero errors, clean dashboard |
| **Evidence to capture** | Throughput (ops/sec), p50/p95/p99 latency, error rate, memory usage, connected clients, ops/sec server-side, replication lag |
| **Operator actions to record** | None expected; record any manual steps required to reach steady state |

### Scenario 2: Primary Process Kill

| Field | Detail |
|---|---|
| **Name** | Primary Process Kill |
| **Category** | Failure |
| **Why it matters** | Simple HA proof — the most common first question customers ask about failover quality |
| **Injection method** | `docker kill <primary_container>` (Docker) or `kubectl delete pod <primary_pod> --grace-period=0` (Kubernetes) |
| **Preconditions** | Steady-state baseline confirmed, workload running at target rate, primary node identified |
| **Expected Enterprise behavior** | Automatic failover within seconds, brief latency spike, minimal or zero client errors, no operator intervention required |
| **Expected OSS behavior** | Sentinel-triggered failover with longer detection and promotion time, higher error burst during transition, possible client reconnection failures |
| **Evidence to capture** | Time to detect failure, time to complete failover, time to recover to 95% of baseline throughput, peak latency during recovery, error count and duration, client reconnect behavior |
| **Operator actions to record** | Any manual commands run, client restarts needed, configuration changes required post-failover |

### Scenario 3: Node Reboot or Node Loss

| Field | Detail |
|---|---|
| **Name** | Node Reboot or Node Loss |
| **Category** | Failure |
| **Why it matters** | Real infrastructure event — tests recovery path and operator effort when a full node disappears |
| **Injection method** | `docker stop <node_container> && sleep 30 && docker start <node_container>` (Docker) or `kubectl delete pod <node_pod>` and let the scheduler reschedule (Kubernetes) |
| **Preconditions** | Steady-state baseline confirmed, workload running, topology snapshot taken before disruption |
| **Expected Enterprise behavior** | Automatic detection and recovery, cluster resharding or replica promotion handled internally, operator notified but not required to act |
| **Expected OSS behavior** | Sentinel or Cluster protocol detects loss after timeout, manual slot migration may be needed (Cluster mode), longer recovery window, operator may need to rejoin node manually |
| **Evidence to capture** | Application impact duration, recovery path and time, operator effort (commands and time), topology state before and after, replication sync state after recovery, SLA breach duration |
| **Operator actions to record** | Manual node rejoin steps, slot rebalancing commands, configuration file edits, client-side recovery actions |

### Scenario 4: Rolling Upgrade Under Load

| Field | Detail |
|---|---|
| **Name** | Rolling Upgrade Under Load |
| **Category** | Operations |
| **Why it matters** | Day-2 operations proof — demonstrates whether maintenance can happen without service disruption |
| **Injection method** | Enterprise: `rladmin upgrade` or Operator-managed rolling restart. OSS: sequential `redis-cli SHUTDOWN` and restart with new binary per node, or `kubectl rollout restart` for k8s deployments |
| **Preconditions** | Steady-state baseline confirmed, workload running, upgrade target version available, rollback plan documented |
| **Expected Enterprise behavior** | Zero-downtime rolling upgrade, automatic shard migration, continuous service with minor latency variation, single operator command |
| **Expected OSS behavior** | Per-node manual restart required, potential client disconnections per node, operator must verify cluster health between steps, higher risk of misconfiguration |
| **Evidence to capture** | Service continuity (error rate during upgrade window), latency spikes per node restart, total upgrade duration, operator steps count, commands executed outside scripted path |
| **Operator actions to record** | Every command executed, time per node, health checks performed, rollback actions if needed, total operator time |

## Day-2 Stretch Scenarios

These scenarios extend the comparison into harder resiliency and growth proofs. Add them only after the Day-1 set is stable.

### Scenario 5: Network Partition

| Field | Detail |
|---|---|
| **Name** | Network Partition |
| **Category** | Failure |
| **Why it matters** | Hard resiliency proof — tests split-brain behavior, write safety, and diagnostic clarity under the most challenging failure mode |
| **Injection method** | `iptables -A INPUT -s <target_node_ip> -j DROP && iptables -A OUTPUT -d <target_node_ip> -j DROP` (VM) or network policy injection via `kubectl apply -f partition-policy.yaml` (Kubernetes) |
| **Preconditions** | Steady-state baseline confirmed, workload running, network topology documented, partition recovery plan ready |
| **Expected Enterprise behavior** | Quorum-based decision, controlled write rejection on minority side, clear diagnostic events, automatic healing when partition resolves |
| **Expected OSS behavior** | Sentinel may elect conflicting primaries, risk of split-brain writes, manual resolution likely required, less diagnostic clarity |
| **Evidence to capture** | Split behavior (which side accepts writes), write safety (lost or conflicting writes), diagnostic event quality, time to detect partition, time to heal after resolution, data consistency check results |
| **Operator actions to record** | Partition diagnosis steps, manual resolution commands, data reconciliation actions, time to understand what happened |

### Scenario 6: Scale-Out or Rebalance Under Load

| Field | Detail |
|---|---|
| **Name** | Scale-Out or Rebalance Under Load |
| **Category** | Operations |
| **Why it matters** | Growth proof — demonstrates whether the platform can expand capacity without disrupting running workloads |
| **Injection method** | Enterprise: `rladmin node add` + `rladmin shard migrate` or Operator replica count increase. OSS: `redis-cli --cluster add-node` + `redis-cli --cluster rebalance` or manual slot migration |
| **Preconditions** | Steady-state baseline confirmed, workload running, additional node or pod capacity available, current slot/shard distribution documented |
| **Expected Enterprise behavior** | Smooth shard migration with minimal latency impact, automatic rebalancing, no client-visible errors, single operational workflow |
| **Expected OSS behavior** | Manual slot migration with potential latency spikes during key migration, client may see MOVED/ASK redirections, operator must monitor and verify balance, higher risk of uneven distribution |
| **Evidence to capture** | Latency during topology change, rebalance duration, throughput impact during migration, error rate during scale event, final slot/shard distribution, operator time and effort |
| **Operator actions to record** | Node addition commands, rebalance commands, health verification steps, client-side adjustments, total operator time |



## Test Flow Methodology

Every scenario in this matrix must follow this 10-step process. No shortcuts.

1. **Verify environment parity.** Confirm versions, sizing, and configuration assumptions match between Enterprise and OSS deployments. Record software versions, node sizing, persistence settings, client configuration, and replica-read policy.

2. **Prime the dataset.** Load the target dataset using the selected Locust workload profile. Seed enough data to avoid empty-cache benchmark artifacts.

3. **Warm up the workload.** Run the workload at target rate for a warm-up period until metrics stabilize. Discard warm-up data from results.

4. **Run a steady-state baseline.** Capture at least 10 minutes of clean baseline metrics. This becomes the reference point for all disruption comparisons.

5. **Inject a single planned disruption.** Execute exactly one injection method from the scenario definition. Do not combine multiple failure types in a single run.

6. **Mark the event in the dashboard timeline.** Record the exact timestamp of injection in both the Locust dashboard and the infrastructure metrics dashboard. Use timeline markers or annotations.

7. **Observe degradation and recovery.** Monitor client-side metrics (throughput, latency, errors) and server-side metrics (replication lag, failover events, pod restarts) continuously through the disruption and recovery window.

8. **Continue long enough to confirm stability.** Run the workload for at least 5 minutes after recovery metrics return to baseline levels. Confirm no delayed failures or degradation.

9. **Export evidence and record operator actions.** Capture dashboard screenshots, export metric data, save event logs, and document every operator command executed during the scenario. Include topology snapshots before and after.

10. **Repeat at least three times.** Do not draw conclusions from a single run. Execute each scenario a minimum of three times and report consistency of results alongside averages.

## Fairness Controls Checklist

Before any comparison run, verify all of the following controls are in place. Document any exceptions explicitly.

- [ ] **Same client host sizing and network path** — both Enterprise and OSS workloads run from the same client machine(s) with equivalent network topology
- [ ] **Same Locust shape and dataset size** — identical workload profile, user count, spawn rate, and pre-seeded dataset
- [ ] **Same persistence posture** — unless the comparison is explicitly about persistence tradeoffs, both sides use the same AOF/RDB configuration
- [ ] **Same declared replica-read policy** — do not mix consistency models silently between compared stacks
- [ ] **Same TLS posture** — if TLS is enabled on one side, enable it on the other (where applicable)
- [ ] **No hidden emergency tuning** — any tuning applied to one side must be documented and, where possible, applied equivalently to the other side

## Evidence Capture Reference

All scenarios must capture evidence aligned with the Phase 0 measurement standards (see `docs/PHASE_0_SCOPE_AND_PRINCIPLES.md`, Section 9).

### Client-side evidence (from Locust)

- Throughput (ops/sec)
- p50, p95, p99 latency
- Error rate
- Reconnect and retry behavior
- Time to resume target throughput

### Server and platform evidence

- Memory usage
- CPU utilization
- Connected clients
- Blocked clients
- Operations per second
- Replication lag or sync state
- Failover events
- Kubernetes events and pod restarts (where applicable)

### Operational evidence

- Number of human interventions
- Number of commands executed outside the planned runbook
- Time to diagnose the issue
- Time to restore confidence in normal service

### Business-facing evidence

- SLA breach duration
- Visible application disruption
- Risk of lost writes or stale reads
- Operator confidence and explainability

## Scorecard Questions

Every scenario must end with a clear answer to three questions:

1. **What happened?** — factual description of the disruption and system response
2. **What did the application feel?** — client-visible impact in terms of errors, latency, and downtime
3. **Which platform made recovery faster or simpler?** — comparative conclusion with supporting evidence