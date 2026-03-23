# Audit V0 — Gap Analysis and Reuse Assessment

**Date:** March 23, 2026  
**Scope:** Audit of the current `locust-poc-lab` repo plus selective review of `https://github.com/pierrelambert/locust-poc` for reusable material.  
**Goal:** Identify what is still missing for Redis Solution Architects to cover the full POC motion confidently and get productive fast.

---

## Executive Summary

The current repo is already in a much better place than the older `locust-poc` attempt:

- the structure is cleaner,
- the intended SA motion is clearer,
- the scenario/workload/topology model is more disciplined,
- and the repo is no longer buried under historical or overly broad material.

That said, it is **not yet a full field-ready POC kit** for the use case you described.

The current state is best described as:

- **strong on framing and structure,**
- **good on Docker-path prototypes,**
- **partial on evidence packaging,**
- **weak on true Kubernetes execution,**
- **weak on true VM execution,**
- **and not yet strong enough on topology-aware client behavior and validation depth.**

The biggest risk is not missing markdown. The biggest risk is **credibility drift**:

- docs and matrices suggest a complete Enterprise vs OSS POC motion,
- but some of the actual execution path is still Docker-centric, partially simulated, or assumes behavior instead of proving it.

If SAs bring this as-is to customers, they can explain the motion well, but they still risk getting stuck on:

1. real Sentinel/Cluster client behavior,
2. real Kubernetes failover execution,
3. real VM deployment expectations,
4. and hard questions about repeatability and validation.

---

## Audit Method

The audit was based on:

- direct review of the current repo structure, docs, workloads, infra, observability, and scenario scripts;
- `make validate` in the current repo, which passed with **82 checks, 0 failures**;
- direct clone and review of the older `locust-poc` repo under `/tmp/locust-poc-old`;
- comparison of what the old repo solved well versus what made it too complex.

Important limitation:

- current validation only proves **syntax and manifest consistency**,
- not that the full comparison flows are already field-proven end-to-end.

---

## What the Current Repo Already Has

These are meaningful strengths and should be preserved.

### Repo shape and SA story

- `README.md` gives a clean top-level project description.
- `docs/PHASE_0_SCOPE_AND_PRINCIPLES.md` defines the charter and guardrails well.
- `docs/POC_LAB_EXECUTION_BLUEPRINT.md` gives a clear operating model for SA motions.
- `docs/TOPOLOGY_MATRIX.md`, `docs/SCENARIO_MATRIX.md`, and `docs/WORKLOAD_CATALOG.md` provide a disciplined comparison model.

### Runnable lab assets

- Docker comparison stacks exist for:
  - Redis Enterprise Software
  - OSS Redis + Sentinel
  - OSS Redis Cluster
- Kubernetes manifests exist for:
  - Redis Enterprise Operator
  - OSS Redis + Sentinel
- Workload implementations exist for:
  - `cache_read_heavy`
  - `session_mixed`
  - `counter_hotkey`
  - `leaderboard_sorted_set`
  - `stream_ingest`

### Scenario and evidence foundations

- Scenario scripts exist for:
  - baseline
  - primary kill
  - node loss
  - rolling upgrade
  - network partition
  - replica promotion / scale event
- Evidence export exists via `observability/exporters/run_summary_exporter.py`.
- A Grafana dashboard exists.
- Templates exist for:
  - POC charter
  - customer scorecard

### Validation baseline

- `make validate` passes.
- Compose files, Python, shell, YAML, and Makefile targets are currently syntactically consistent.

---

## Coverage Snapshot

| Capability | Current State | Audit Call |
|---|---|---|
| SA project framing | Strong | Good foundation |
| Docker-based comparison paths | Good | Usable foundation |
| Workload catalog | Good | Strong Day-1 set |
| Failure scenario design | Good | Strong Day-1 set |
| Evidence export | Partial | Useful but not enough alone |
| Customer-facing templates | Partial | Good start, not complete |
| Onboarding for new SAs | Partial | Better than before, still thin |
| Real Kubernetes POC execution | Partial | Not yet field-ready |
| Real VM execution path | Weak | Missing for the stated goal |
| Topology-aware Redis clients | Weak | Critical gap |
| Observability for side-by-side proof | Partial | Too narrow today |
| CI and runtime validation | Weak | Critical gap |
| Example outputs and sample packs | Weak | Missing |

---

## Critical Gaps

These are the gaps that matter most if the goal is: "an easy, rock-solid field kit that lets SAs look strong and run the POC motion without getting trapped in tooling."

### P0.1 — The current client path is not topology-aware enough

**Why this matters**

The current workloads use a simple `redis.Redis` connection pool in `workloads/lib/connections.py`. That is not enough for a serious comparison across:

- Sentinel discovery,
- Redis Cluster redirect handling,
- TLS/SNI customer environments,
- and failure classification during topology changes.

**Current evidence**

- `workloads/lib/connections.py` builds a plain `redis.ConnectionPool`.
- Profiles only model `host`, `port`, `password`, `db`, `ssl`, and pool size.
- There is no explicit adapter for:
  - `redis.sentinel.Sentinel`
  - `redis.cluster.RedisCluster`
  - Redis Enterprise TLS/SNI access patterns

**Risk**

This can make Cluster and Sentinel results look wrong for the wrong reasons:

- MOVED/ASK redirects may not be handled correctly,
- failover discovery may be overly manual,
- TLS customer setups are not represented,
- and failure modes may be misclassified as generic errors.

**What to add**

- A simplified topology-aware client layer for:
  - standalone,
  - Sentinel,
  - Cluster,
  - Enterprise proxy endpoint,
  - TLS/SNI where applicable.
- Failure categorization in Locust results.
- Explicit connection mode in each workload profile.

**Best source from old repo**

- `src/redis_client/connection_manager.py`
- `src/redis_client/resilient_client.py`
- `src/redis_client/retry.py`
- `src/redis_client/circuit_breaker.py`
- `src/locust_tests/base_user.py`
- `src/locust_tests/failure_tracker.py`
- `src/utils/tls_manager.py`

**Recommendation**

Do **not** port the whole old client framework unchanged. Port the concepts and slim them down into a small current-era adapter layer.

---

### P0.2 — Kubernetes is documented as a first-class path, but execution is still mostly Docker-shaped

**Why this matters**

Your stated goal includes:

- Redis Enterprise Operator on Kubernetes,
- OSS Redis on Kubernetes with OSS operators/charts,
- and customer-facing comparison scenarios.

Today the repo has k8s manifests and Make targets, but the actual scenario runners are still Docker-first.

**Current evidence**

- `Makefile` has `k8s-re-up` and `k8s-oss-up`.
- `infra/k8s/` contains useful manifests.
- `scenarios/scripts/*.sh` execute with `docker`, `docker kill`, `docker stop`, `docker network disconnect`, and `docker exec`.
- Runbooks describe Kubernetes variants, but the scripts do not implement them.

**Risk**

An SA can deploy k8s assets, but cannot yet run the full proof motion in a repeatable, script-assisted way on Kubernetes.

**What to add**

- A parallel `scenarios/k8s/` execution path.
- Helpers for:
  - port-forward or in-cluster Locust,
  - pod selection,
  - service discovery,
  - event marking with pod names and namespaces,
  - post-failure topology checks.
- One guided k8s lab path that actually runs end-to-end.

**Best source from old repo**

- `deployments/k3s-comparison/*`
- `deployments/k3s-redis-enterprise/*`
- `docs/reference/LOCUST_GUIDE.md`
- `docs/reference/DAY2_OPERATIONS_GUIDE.md`

**Recommendation**

Do not resurrect the old k3s-comparison tree as-is. Reuse its **deployment and failover ideas**, not its directory sprawl or interactive shell flow.

---

### P0.3 — The repo does not yet provide a true VM customer path

**Why this matters**

You explicitly want:

- Redis Enterprise Software on VMs
- OSS Redis on VMs

The current repo uses Docker Compose as the VM-path approximation. That is good for local learning, but not enough if the lab is meant to support customer POCs on actual VMs.

**Current evidence**

- Current "VM" path in `Makefile` is Docker Compose only.
- There is no actual VM bootstrap, system service layout, or VM environment config in the current repo.

**Risk**

SAs will still need to improvise when the customer says:

- "Can you run this on our Linux VMs?"
- "How does the test runner live on a jump host?"
- "How do we package the load tool and metrics service on a VM?"

**What to add**

- A real VM lab path with:
  - deploy script,
  - environment file,
  - service units,
  - log locations,
  - TLS handling,
  - cleanup and verification.

**Best source from old repo**

- `deployments/vm/deploy.sh`
- `deployments/vm/systemd/redis-poc-locust.service`
- `deployments/vm/systemd/redis-poc-metrics.service`
- `config/vm.yaml`

**Recommendation**

Bring over the VM packaging ideas, but refit them to the new repo structure and keep them minimal.

---

### P0.4 — Some scenario logic still "assumes" Redis Enterprise behavior instead of proving it

**Why this matters**

In a customer-facing POC, "assumed" is not acceptable.

**Current evidence**

- In `scenarios/scripts/02_primary_kill.sh`, the `re` branch marks failover as detected with `"assumed"`.
- In `05_network_partition.sh`, the `re` recovery path is also effectively assumed.
- In `06_replica_promotion.sh`, the `re` path logs manual placeholders instead of using a real mechanism.

**Risk**

This undermines the exact thing the repo is meant to establish: proof quality.

**What to add**

- Real Redis Enterprise checks via:
  - `rladmin`,
  - REST API,
  - or Kubernetes REC/REDB status depending on path.
- Real timing points for:
  - failure detection,
  - promotion completion,
  - write availability restored,
  - full healthy state restored.

**Best source from old repo**

- `scripts/measure_failover_impact.py`
- `src/chaos/failover.py`
- `src/chaos/failover_impact_tester.py`
- `docs/reference/FAILOVER_IMPACT_MEASUREMENT.md`

**Recommendation**

Reuse the measurement concepts, not the full complexity. The current repo needs a narrower, more credible RE evidence path.

---

### P0.5 — Validation is not yet deep enough to support the “it just works” promise

**Why this matters**

`make validate` passing is good, but it only proves syntax and file consistency.

**Current evidence**

- No `tests/` tree in the current repo.
- No CI workflow in the current repo.
- No smoke tests that:
  - start a stack,
  - run a workload,
  - execute a scenario,
  - and assert the expected evidence pack exists.

**Risk**

The repo can look stable while still failing during actual use.

**What to add**

- Smoke tests for:
  - Docker RE baseline path,
  - Docker OSS Sentinel baseline path,
  - one failover scenario,
  - exporter output shape,
  - dashboard provisioning.
- CI to run syntax plus smoke validation.

**Best source from old repo**

- `tests/unit/*`
- `tests/deployment/*`
- `tests/integration/*`
- `.github/workflows/ci.yml`

**Recommendation**

Do not copy the old test tree mechanically. Create a smaller new smoke suite tailored to the current repo shape.

---

## High-Value Gaps

These are not as blocking as the P0 items, but they matter directly for SA ramp-up and field polish.

### P1.1 — Onboarding is better than before, but still not sharp enough

**Current state**

- The repo has `docs/guides/SA_GUIDED_LAB.md`.
- The top-level `README.md` is still sparse and does not strongly push a new SA into the right first path.

**Specific issues**

- No single "Start Here" doc for:
  - first 30 minutes,
  - first comparison,
  - first customer-ready story.
- Resource guidance is inconsistent:
  - `docs/guides/SA_GUIDED_LAB.md` says `~8 GB free RAM`,
  - `docs/TOPOLOGY_MATRIX.md` recommends `16 GB` or more for comparison pairs.

**What to add**

- `docs/guides/START_HERE.md`
- `docs/guides/FIRST_30_MINUTES.md`
- one unified prerequisites page with exact resource guidance
- one decision tree: laptop demo vs k8s demo vs customer VM POC

---

### P1.2 — Scenario runbooks are incomplete

**Current state**

- Runbooks exist for scenarios 3 to 6.
- Scenario scripts exist for 1 to 6.

**Gap**

- There is no standalone runbook for:
  - Scenario 1 baseline
  - Scenario 2 primary kill

**Why it matters**

The first two scenarios are the most important ones for a new SA and for a short customer demo.

**What to add**

- `scenarios/runbooks/01_baseline.md`
- `scenarios/runbooks/02_primary_kill.md`

---

### P1.3 — Observability is still too narrow for side-by-side proof

**Current state**

- Observability stack exists.
- Grafana dashboard exists.
- Evidence export exists.

**Gap**

- Prometheus only scrapes a single Redis exporter target.
- Labels are static and currently biased toward one stack.
- There is no clean multi-topology comparison view.
- There is no native Grafana annotation push path in the current repo.

**Why it matters**

A strong customer proof needs:

- side-by-side visibility,
- clean event markers,
- easy screenshots,
- and clear differentiation between Enterprise and OSS runs.

**What to add**

- multiple exporters or target relabeling per topology,
- dashboard variables for platform/run/scenario,
- Grafana annotation API support,
- a "comparison view" dashboard for Enterprise vs OSS.

**Best source from old repo**

- `src/observability/event_annotator.py`
- `deployments/grafana/redis-poc-dashboard.json`
- `docs/reference/OBSERVABILITY_GUIDE.md`

---

### P1.4 — Customer-facing material is still incomplete

**Current state**

- Good start with:
  - POC charter template
  - scorecard template

**Missing**

- discovery questionnaire,
- executive readout template,
- reusable recommendations language,
- sample screenshots,
- sample completed scorecard,
- sample result pack from a known-good run.

**Why it matters**

SAs need more than scripts. They need polished material they can use in front of customers quickly.

**What to add**

- `docs/templates/DISCOVERY_QUESTIONNAIRE.md`
- `docs/templates/EXECUTIVE_READOUT_TEMPLATE.md`
- `examples/results/` with one sanitized sample pack
- `examples/scorecards/` with a completed example

---

### P1.5 — Data consistency and RTO/RPO proof are not yet first-class

**Current state**

- Current scripts capture event timing and Redis INFO snapshots.
- Network partition script records command counters before and after.

**Gap**

- No real canary-write validation.
- No checksum or key-consistency verifier.
- No RTO/RPO-specific evidence output.

**Why it matters**

Customers will eventually ask:

- "Did we lose writes?"
- "Could both sides accept writes?"
- "What is the actual recovery objective?"

**What to add**

- canary key writer,
- post-failure consistency checker,
- RTO/RPO summary fields in run summaries,
- dedicated methodology doc.

**Best source from old repo**

- `docs/RESILIENCY_POC_GAP_ANALYSIS.md`
- `docs/reference/FAILOVER_IMPACT_MEASUREMENT.md`
- `scripts/measure_failover_impact.py`

---

### P1.6 — Setup is not yet hermetic enough for field speed

**Current state**

- `make setup` installs Python dependencies directly.
- `k8s-re-up` fetches the Redis Enterprise Operator bundle from GitHub on every run.

**Gap**

- No bootstrap script for a clean workstation.
- No lockfile or reproducible Python environment.
- No offline or low-connectivity field mode.
- No cached operator bundle or release artifact.

**Why it matters**

Customer-site networks and laptop setups are where POCs go wrong.

**What to add**

- `scripts/bootstrap.sh`
- pinned dependency strategy
- vendored or release-pinned operator manifests
- "offline field kit" notes

---

## Strategic Gaps

These are worth planning, but should not come before the P0/P1 items above.

### P2.1 — Kubernetes OSS comparison breadth is still narrow

Current k8s OSS support is mainly a Sentinel-style implementation. If the ambition is to cover the full competitive k8s story, you will likely want:

- one chart-based OSS k8s baseline,
- one operator-based OSS k8s baseline,
- and eventually one OSS Cluster-on-k8s path.

The current repo should keep one strong baseline first. But the roadmap should be explicit here.

### P2.2 — No cross-run comparator yet

The current exporter is per-run. There is no clean aggregator that says:

- Enterprise run A vs OSS run B vs OSS run C,
- median failover time,
- error count distribution,
- operator effort comparison.

The old repo had this idea, but in a crude shell-report form.

### P2.3 — No role-based motion packs yet

You will eventually want:

- SA enablement pack,
- customer live-demo pack,
- multi-day comparison pack,
- executive readout pack.

Right now those motions exist mostly in documents, not in packaging.

---

## What We Should Reuse from the Old `locust-poc` Repo

The right approach is **selective import**, not migration.

### Must-Adapt First

| Old asset | Why it is valuable | How to reuse it |
|---|---|---|
| `src/redis_client/*` | topology-aware client patterns, retry, circuit breaker | Extract only the connection-mode logic and resilient execution concepts |
| `src/utils/tls_manager.py` | TLS/SNI support for customer-grade Enterprise setups | Adapt into a lightweight current TLS helper |
| `src/locust_tests/base_user.py` | structured Locust-to-Redis request tracking | Reuse the request instrumentation pattern |
| `src/locust_tests/failure_tracker.py` | failure categorization by type | Port into the current evidence path |
| `src/observability/event_annotator.py` | push annotations into Grafana | Add as optional enhancement on top of `events.jsonl` |
| `scripts/measure_failover_impact.py` | structured failover measurement/reporting | Simplify into a current comparison summarizer |
| `deployments/vm/*` | true VM deployment shape | Rebuild into `infra/vm/` |
| `tests/*` and `.github/workflows/ci.yml` | quality gates and regression detection | Recreate as a smaller smoke suite and CI workflow |

### Strong Reference Material

| Old asset | Use |
|---|---|
| `docs/reference/LOCUST_GUIDE.md` | mine for k8s Locust execution patterns, not for direct copy |
| `docs/reference/DAY2_OPERATIONS_GUIDE.md` | mine for maintenance/failover language |
| `docs/reference/FAILOVER_IMPACT_MEASUREMENT.md` | mine for proof methodology |
| `deployments/k3s-comparison/*` | reuse scenario/deploy logic ideas for future k8s comparison pack |
| `docs/RESILIENCY_POC_GAP_ANALYSIS.md` | useful as a checklist of scenario classes and evidence expectations |
| `docs/validation/PURPOSE_GAP_ANALYSIS.md` | useful as a sanity check against missing onboarding and deployment paths |

### Do Not Port As-Is

| Old asset | Why not |
|---|---|
| `archive/` tree | historical clutter; exactly the complexity problem you want to avoid |
| old README and large phase-history narratives | too broad, too many claims, too much context switching |
| `run-all-tests.sh` | interactive monolith, not field-safe |
| `compare-results.sh` | useful idea, weak implementation; replace with a proper Python comparison report |
| broad `src/` structure in full | too much framework for the new repo’s tighter scope |

---

## Recommended Additions to the Current Repo

### Wave 1 — Make the repo credible and usable

1. Add topology-aware client adapters.
2. Add real RE failover verification instead of assumed checks.
3. Add smoke tests and CI.
4. Add `START_HERE.md` and align resource guidance.
5. Add scenario runbooks for baseline and primary kill.

### Wave 2 — Cover the actual field paths

6. Add a real VM deployment path under `infra/vm/`.
7. Add Kubernetes scenario execution scripts.
8. Add a k8s guided lab that truly runs end-to-end.
9. Add multi-topology observability and comparison dashboarding.

### Wave 3 — Make SAs look polished

10. Add discovery questionnaire and executive readout template.
11. Add example result packs and completed sample scorecards.
12. Add cross-run comparison reporting.
13. Add data consistency, RTO, and RPO checks.

---

## Suggested File/Directory Additions

The following additions would close most of the practical gaps quickly.

```text
docs/guides/START_HERE.md
docs/guides/FIRST_30_MINUTES.md
docs/guides/K8S_COMPARISON_LAB.md
docs/guides/VM_COMPARISON_LAB.md
docs/templates/DISCOVERY_QUESTIONNAIRE.md
docs/templates/EXECUTIVE_READOUT_TEMPLATE.md
examples/results/
examples/scorecards/
infra/vm/
scenarios/k8s/
tests/smoke/
.github/workflows/ci.yml
workloads/lib/topology_clients.py
tooling/compare_runs.py
tooling/check_data_consistency.py
```

---

## Final Assessment

### Is the current repo useful?

Yes. It is already a strong foundation and much healthier than the older attempt.

### Is it enough for the full SA POC mission yet?

Not yet.

### What is the biggest remaining gap?

The biggest gap is the distance between:

- **what the docs promise**  
and
- **what is actually executable and defensible across Docker, Kubernetes, and VM customer paths.**

### What should happen next?

If the goal is fast progress with high leverage, the next implementation work should be:

1. topology-aware clients,
2. real k8s scenario execution,
3. real VM path,
4. smoke tests + CI,
5. and polished customer material.

That is the shortest path from "promising foundation" to "SAs can walk into customer meetings and run this without losing control."
