# Customer Demo Checklist

A step-by-step guide for delivering a 60-minute live customer demo.

---

## Pre-Demo Prep (day before — 30 min)

- [ ] Run through the full demo once on your own to verify everything works
- [ ] Run `make setup` to ensure dependencies are current
- [ ] Start stacks and verify: `make re-up`, `make oss-sentinel-up`, `make obs-up`
- [ ] Open Grafana (`http://localhost:3000`) and confirm dashboards load with metrics
- [ ] Run a quick baseline on both platforms to warm up the environment
- [ ] Tear down and restart fresh so the demo starts clean: `make re-down`, `make oss-sentinel-down`, `make obs-down`
- [ ] Review [`docs/guides/TROUBLESHOOTING.md`](../../docs/guides/TROUBLESHOOTING.md) for common issues
- [ ] Prepare a browser with Grafana bookmarked and terminal windows pre-sized

### Fallback Plan

- [ ] Pre-record a backup screencast of the demo in case of environment issues
- [ ] Have [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md) ready to show as backup evidence
- [ ] Have [`examples/results/sample_run_summary.md`](../../examples/results/sample_run_summary.md) ready as backup results

---

## Demo Setup (0:00–0:10)

- [ ] Start Redis Enterprise: `make re-up`
- [ ] Start OSS Redis Sentinel: `make oss-sentinel-up`
- [ ] Start observability stack: `make obs-up`
- [ ] Verify all containers are healthy: `make re-status`, `make oss-sentinel-status`, `make obs-status`
- [ ] Open Grafana and navigate to the POC dashboard

**Talking point:** _"We're running two production-grade Redis deployments side by side — Redis Enterprise (3-node cluster) and OSS Redis with Sentinel (1 primary + 2 replicas + 3 sentinels). Same hardware, same workload, same failure injection."_

---

## Baseline Run (0:10–0:25)

- [ ] Start baseline on Redis Enterprise — follow [`scenarios/runbooks/01_baseline.md`](../../scenarios/runbooks/01_baseline.md)
- [ ] Start baseline on OSS Sentinel — same runbook, different target
- [ ] Show Grafana: point out throughput, latency percentiles, error rate at zero
- [ ] Let baseline run for 3–5 minutes to establish stable numbers

**Talking point:** _"Both platforms are handling the same workload at steady state. Note the throughput and p99 latency — this is our 'normal' that we'll compare against after a failure."_

---

## Primary Kill — The Money Shot (0:25–0:45)

- [ ] Explain what you're about to do: kill the primary Redis process on both platforms
- [ ] Execute primary kill on Redis Enterprise — follow [`scenarios/runbooks/02_primary_kill.md`](../../scenarios/runbooks/02_primary_kill.md)
- [ ] **Pause on Grafana** — show the recovery curve (sub-second for RE)
- [ ] Execute primary kill on OSS Sentinel
- [ ] **Pause on Grafana** — show the longer recovery window, error spike
- [ ] Side-by-side comparison: point out RTO difference, error count, data loss (if any)

**Talking points:**
- _"Redis Enterprise detected the failure and promoted a replica in under 1 second. The client saw zero or near-zero errors."_
- _"OSS Sentinel took 15–30 seconds to detect and failover. During that window, writes failed and clients received errors."_
- _"This isn't a synthetic benchmark — this is the same workload, same hardware, real failover."_

---

## Evidence Review (0:45–0:55)

- [ ] Export run summaries: `make export-summary RUN_DIR=results/<re_run_id>` and `make export-summary RUN_DIR=results/<oss_run_id>`
- [ ] Show the RTO/RPO numbers from the consistency checker output
- [ ] Show the canary writer results — any lost writes?
- [ ] Walk through the scorecard template: [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md)
- [ ] Show the sample completed scorecard: [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md)

**Talking point:** _"Everything you just saw is captured as evidence — JSON data, Grafana snapshots, consistency reports. This is what goes into the POC scorecard for your team."_

---

## Q&A and Next Steps (0:55–1:00)

- [ ] Offer to run additional scenarios if time permits (node loss, network partition)
- [ ] Mention the full scenario matrix: [`scenarios/runbooks/`](../../scenarios/runbooks/)
- [ ] Discuss next steps: customer can run this in their own environment
- [ ] Reference the discovery questionnaire for scoping a full POC: [`docs/templates/DISCOVERY_QUESTIONNAIRE.md`](../../docs/templates/DISCOVERY_QUESTIONNAIRE.md)

---

## Teardown (after demo)

- [ ] `make re-down`
- [ ] `make oss-sentinel-down`
- [ ] `make obs-down`

