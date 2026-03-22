# POC Lab Execution Blueprint

**Last updated:** March 22, 2026  
**Status:** Draft execution plan

## 1. Purpose

This document turns the Phase 0 charter into an operating model that Redis Solution Architects can use for internal enablement and customer-facing POCs.

The blueprint is designed to make Redis Enterprise win in a way that is:

- easy to run,
- easy to explain,
- fair enough to be credible,
- and repeatable enough to scale across the SA team.

## 2. Standard Engagement Motions

The project should support four standard motions instead of improvising every time.

### Motion A: 90-minute internal learning lab

Use case: onboard new SAs  
Goal: understand topology behavior, failure events, and the dashboard story  
Output: a completed guided lab and one sample scorecard

### Motion B: 1-day customer live demo

Use case: create urgency early in the sales cycle  
Goal: show one or two dramatic, easy-to-read resiliency differences  
Output: live dashboard screenshots, timeline markers, and a same-day summary

### Motion C: 5-day standard comparison POC

Use case: most field engagements  
Goal: baseline, inject failures, compare recovery, and summarize operational effort  
Output: signed POC charter, run evidence, and final recommendation

### Motion D: 10-day strategic proof

Use case: competitive or skeptical accounts  
Goal: add tuning rounds, scaling events, and maintenance scenarios without losing structure  
Output: full evidence pack with scorecard and executive readout

## 3. Day-1 Reference Architectures

The first release should keep the architecture set intentionally small.

| Architecture | Purpose | Day-1 status | Notes |
|---|---|---|---|
| Redis Enterprise Software on VMs | Enterprise VM reference | Required | 3-node cluster minimum |
| Redis Enterprise Operator on k8s | Enterprise Kubernetes reference | Required | Primary k8s proof path |
| OSS Redis with Sentinel on VMs | OSS HA baseline | Required | Compare failover and operator effort |
| OSS Redis Cluster on VMs | OSS sharded baseline | Required | Compare slot ownership and recovery behavior |
| OSS Redis on k8s operator or chart | OSS Kubernetes baseline | Required | Pick one primary implementation first |

### Architecture rule

Do not add more variants until the primary matrix is stable. A lab with ten half-maintained baselines is weaker than a lab with four excellent ones.

## 4. Workload Catalog for Locust

The lab should ship a small workload catalog tied to real customer narratives.

| Workload | Primary story | Read/write mix | Key behaviors to observe |
|---|---|---|---|
| `cache_read_heavy` | product catalog, content cache | 90/10 | hit ratio, tail latency, recovery after failover |
| `session_mixed` | login/session state | 70/30 | reconnect behavior, write continuity, stale session risk |
| `counter_hotkey` | inventory, counters, rate limits | 60/40 | hot key pressure, latency spikes, failover sensitivity |
| `leaderboard_sorted_set` | ranking/game/ecommerce | 80/20 | sorted-set update latency, cluster balance, recovery |
| `stream_ingest` | event or order pipeline | 50/50 | write durability, consumer lag, recovery pacing |

### Workload design rules

- Use one client library path per language and configure connection pooling consistently.
- Use the same key naming and data model across compared stacks.
- Declare whether replica reads are allowed; do not mix consistency models silently.
- Prefer realistic think time and request pacing over raw firehose mode unless the scenario is explicitly a saturation test.
- Seed enough data to avoid empty-cache benchmark nonsense.

## 5. Standard Scenario Matrix

The strongest customer story comes from a small set of repeatable scenarios.

| Scenario | Why it matters | Must capture | Typical Enterprise advantage to show |
|---|---|---|---|
| Steady-state baseline | Establish normal SLA | latency, throughput, error rate, resource use | stable baseline before disruption |
| Primary process kill | Simple HA proof | time to detect, fail over, recover throughput | lower disruption and clearer visibility |
| Node reboot or node loss | Real infrastructure event | app impact, recovery path, operator effort | better automation and recovery posture |
| Network partition | Hard resiliency proof | split behavior, write safety, diagnostics | stronger control and safer behavior |
| Rolling upgrade under load | Day-2 operations proof | service continuity, latency spikes, operator steps | operational simplicity and less risk |
| Scale-out or rebalance under load | Growth proof | latency during topology change, rebalance overhead | smoother expansion and lower toil |

### Day-1 scenario recommendation

Start with four mandatory scenarios:

1. steady-state baseline,
2. primary failure,
3. node loss,
4. rolling upgrade or restart under load.

Network partition and scale events can follow once the core motion is solid.

## 6. Measurement Methodology

The methodology must be boringly consistent. That is what makes the outcome defensible.

### Test flow for each scenario

1. Verify versions, sizing, and config parity assumptions.
2. Prime the dataset.
3. Warm up the workload.
4. Run a steady-state baseline.
5. Inject a single planned disruption.
6. Mark the event in the dashboard timeline.
7. Observe degradation and recovery.
8. Continue long enough to confirm stability.
9. Export evidence and record operator actions.
10. Repeat the scenario at least three times before drawing conclusions.

### Fairness controls

- Same client host sizing and network path
- Same Locust shape and dataset size
- Same persistence posture unless the comparison is explicitly about persistence tradeoffs
- Same declared replica-read policy
- Same TLS posture where applicable
- No hidden emergency tuning on one side only

### Metrics to report by default

- throughput,
- p50, p95, and p99 latency,
- error rate,
- time to first error,
- time to recover to 95 percent of baseline throughput,
- peak latency during recovery,
- number of operator interventions,
- total commands executed outside the scripted path.

### Redis-specific observability requirements

At minimum, the runbook should capture:

- memory usage,
- connected clients,
- blocked clients,
- rejected connections,
- operations per second,
- replication lag or sync state where relevant,
- and platform events tied to failover or restart activity.

## 7. Observability and Evidence Pack

The lab should generate evidence that an SA can narrate in real time.

### Mandatory evidence components

- Locust dashboard with timeline markers
- Redis and infrastructure metrics dashboard
- topology snapshot before and after the disruption
- event log or command log of what was injected
- run summary with timestamps and operator actions

### Scorecard rule

Every scenario must end with a simple answer to three questions:

1. What happened?
2. What did the application feel?
3. Which platform made recovery faster or simpler?

## 8. SA Operating Rhythm

The project should ship a standard rhythm so the SA leads the customer instead of reacting to the customer.

### Before the POC

- Run a discovery call and identify the business-critical workload
- Agree on one primary success criterion and two secondary ones
- Freeze the topology matrix and scenario list
- Document any customer-requested exceptions

### During the POC

- Start each session by restating the scenario and expected signal
- Share dashboards live
- Mark disruptions explicitly
- Record deviations immediately
- Close each session with a short written takeaway

### End of the POC

- Deliver the scorecard within 24 hours
- Separate observed results from opinion
- State where Redis Enterprise was stronger and why it matters operationally
- Recommend the next commercial step

## 9. Required Field Deliverables

The repo should eventually include the following reusable material:

- POC charter template
- environment bill of materials
- day-1 quickstart
- guided SA lab
- customer runbook
- failure injection playbook
- Grafana dashboard pack
- scorecard template
- executive readout template

### Material quality rule

If a deliverable cannot be used by a field SA with minimal editing, it is not done.

## 10. Suggested Build Roadmap

### Phase 1: Repo foundation

Deliver:

- scope and blueprint docs,
- agreed architecture matrix,
- scorecard template,
- repo structure for labs, tooling, and results.

### Phase 2: Minimal runnable lab

Deliver:

- one VM comparison path,
- one Kubernetes comparison path,
- first two Locust workloads,
- baseline and primary-failure scenarios.

### Phase 3: Observability and proof quality

Deliver:

- standard dashboards,
- event marker tooling,
- evidence export process,
- and example result packs.

### Phase 4: Day-2 operations proof

Deliver:

- rolling upgrade scenario,
- node loss scenario,
- operator-effort checklist,
- and customer-ready operational narrative.

### Phase 5: Field hardening

Deliver:

- validation runs on Tier 1 targets,
- troubleshooting guides,
- cleanup automation,
- and sample executive summaries.

## 11. Definition of Field-Ready

The lab is field-ready when an SA can:

- choose a standard motion in less than 10 minutes,
- stand up the target environment from the documented path,
- execute at least three standard scenarios without improvisation,
- show clean dashboards and exported evidence,
- and produce a final recommendation using a standard template.

## 12. Risks to Avoid

- too many topology variants,
- too many workload profiles,
- ambiguous benchmark rules,
- undocumented manual recovery steps,
- and customer-facing claims that are not backed by captured evidence.

The lab should feel smaller, sharper, and more disciplined than a generic benchmark repo.
