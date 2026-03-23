# Multi-Day Comparison Checklist

A day-by-day plan for a comprehensive 2–3 day POC engagement.

---

## Pre-Engagement

- [ ] Complete the discovery questionnaire with the customer: [`docs/templates/DISCOVERY_QUESTIONNAIRE.md`](../../docs/templates/DISCOVERY_QUESTIONNAIRE.md)
- [ ] Fill out the POC charter: [`docs/templates/POC_CHARTER_TEMPLATE.md`](../../docs/templates/POC_CHARTER_TEMPLATE.md)
- [ ] Decide which deployment path(s) to use (Docker, k8s, VM) based on customer environment
- [ ] Verify hardware meets prerequisites (see the relevant lab guide)
- [ ] Run `make setup` and do a quick smoke test: `make test-smoke`

---

## Day 1 — Setup & Baselines (full day)

### Morning: Stand Up All Topologies

**Docker path:**
- [ ] Start Redis Enterprise: `make re-up`
- [ ] Start OSS Sentinel: `make oss-sentinel-up`
- [ ] Start OSS Cluster: `make oss-cluster-up`
- [ ] Verify all stacks: `make vm-status`

**Kubernetes path (if applicable):**
- [ ] Create k3d cluster: `make k3d-up`
- [ ] Deploy Redis Enterprise on k8s: `make k8s-re-up`
- [ ] Deploy OSS Redis on k8s: `make k8s-oss-up`
- [ ] Verify all k8s stacks: `make k8s-status`
- [ ] Reference: [`docs/guides/K8S_COMPARISON_LAB.md`](../../docs/guides/K8S_COMPARISON_LAB.md)

**VM path (if applicable):**
- [ ] Follow VM setup: [`docs/guides/VM_COMPARISON_LAB.md`](../../docs/guides/VM_COMPARISON_LAB.md)

**Observability:**
- [ ] Start observability stack: `make obs-up`
- [ ] Confirm Grafana dashboards at `http://localhost:3000`

### Afternoon: Baseline All Platforms

- [ ] Run baseline on Redis Enterprise — [`scenarios/runbooks/01_baseline.md`](../../scenarios/runbooks/01_baseline.md)
- [ ] Run baseline on OSS Sentinel — same runbook, OSS target
- [ ] Run baseline on OSS Cluster — same runbook, cluster target
- [ ] Run baseline on k8s RE (if applicable) — `make k8s-scenario-baseline`
- [ ] Run baseline on k8s OSS (if applicable) — same target
- [ ] Export all baseline summaries: `make export-summary RUN_DIR=results/<run_id>` for each
- [ ] Verify all baselines show stable throughput, zero errors, consistent latency

---

## Day 2 — Failure & Operations Scenarios (full day)

### Morning: Failure Scenarios

For each platform, run these scenarios (minimum 3 runs each per [`scenarios/runbooks/`](../../scenarios/runbooks/)):

- [ ] **Primary kill** on all platforms — [`scenarios/runbooks/02_primary_kill.md`](../../scenarios/runbooks/02_primary_kill.md)
- [ ] **Node loss** on all platforms — [`scenarios/runbooks/03_node_loss.md`](../../scenarios/runbooks/03_node_loss.md)
- [ ] **Network partition** on all platforms — [`scenarios/runbooks/05_network_partition.md`](../../scenarios/runbooks/05_network_partition.md)

### Afternoon: Operations Scenarios

- [ ] **Rolling upgrade** on all platforms — [`scenarios/runbooks/04_rolling_upgrade.md`](../../scenarios/runbooks/04_rolling_upgrade.md)
- [ ] **Replica promotion** on all platforms — [`scenarios/runbooks/06_replica_promotion.md`](../../scenarios/runbooks/06_replica_promotion.md)

### Evidence Collection

- [ ] Export run summaries for every completed run: `make export-summary RUN_DIR=results/<run_id>`
- [ ] Save Grafana dashboard snapshots for key moments (failover, recovery)
- [ ] Review consistency checker output for each failure scenario
- [ ] Review RTO/RPO reports — see [`docs/guides/DATA_CONSISTENCY_METHODOLOGY.md`](../../docs/guides/DATA_CONSISTENCY_METHODOLOGY.md)

---

## Day 3 — Comparison, Scorecard & Readout (half to full day)

### Cross-Run Comparison

- [ ] Run cross-platform comparison: `python3 tooling/compare_runs.py` across all runs
- [ ] Review comparison output — identify key differentiators per scenario
- [ ] Note any anomalies or re-run needs

### Scorecard

- [ ] Open [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md)
- [ ] Fill in every section with real data from your runs
- [ ] Reference [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md) for format guidance
- [ ] Have a peer review the scorecard for accuracy

### Executive Readout

- [ ] Open [`docs/templates/EXECUTIVE_READOUT_TEMPLATE.md`](../../docs/templates/EXECUTIVE_READOUT_TEMPLATE.md)
- [ ] Draft the readout using scorecard data and Grafana snapshots
- [ ] Prepare 3–5 key recommendations based on the evidence
- [ ] Review with your manager or SE lead before presenting

---

## Teardown

- [ ] `make cleanup-all` to tear down all stacks and clean up
- [ ] Archive results directory for future reference

