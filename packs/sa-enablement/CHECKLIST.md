# SA Enablement Checklist

Work through each section in order. Every item links to the exact file or command you need.

---

## Phase 1 — Quickstart (30 min)

- [ ] Read [`FIRST_30_MINUTES.md`](../../FIRST_30_MINUTES.md) end to end
- [ ] Run `make setup` to install Python dependencies
- [ ] Run `make oss-sentinel-up` to start the OSS Sentinel stack
- [ ] Run `make obs-up` to start the observability stack
- [ ] Open Grafana at `http://localhost:3000` and confirm metrics are flowing
- [ ] Run a quick Locust workload and verify data appears in Grafana
- [ ] Run `make oss-sentinel-down` and `make obs-down` to tear down

---

## Phase 2 — SA Guided Lab (90 min)

- [ ] Open [`docs/guides/SA_GUIDED_LAB.md`](../../docs/guides/SA_GUIDED_LAB.md)
- [ ] Complete Phase 1 — Setup (start RE cluster with `make re-up`, start OSS with `make oss-sentinel-up`)
- [ ] Complete Phase 2 — Baseline runs on both platforms
- [ ] Complete Phase 3 — Primary kill scenario on both platforms
- [ ] Complete Phase 4 — Evidence review (Grafana snapshots, canary writer output)
- [ ] Complete Phase 5 — Fill in the sample scorecard using [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md)
- [ ] Compare your scorecard against [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md)
- [ ] Tear down: `make re-down`, `make oss-sentinel-down`, `make obs-down`

---

## Phase 3 — Scenario Runbooks Deep Dive (90 min)

Work through each runbook. You don't need to run every one — but read them all and run at least 2–3.

- [ ] Read [`scenarios/runbooks/01_baseline.md`](../../scenarios/runbooks/01_baseline.md) — Steady-state baseline
- [ ] Read [`scenarios/runbooks/02_primary_kill.md`](../../scenarios/runbooks/02_primary_kill.md) — Primary process kill
- [ ] Read [`scenarios/runbooks/03_node_loss.md`](../../scenarios/runbooks/03_node_loss.md) — Node reboot / node loss
- [ ] Read [`scenarios/runbooks/04_rolling_upgrade.md`](../../scenarios/runbooks/04_rolling_upgrade.md) — Rolling upgrade under load
- [ ] Read [`scenarios/runbooks/05_network_partition.md`](../../scenarios/runbooks/05_network_partition.md) — Network partition
- [ ] Read [`scenarios/runbooks/06_replica_promotion.md`](../../scenarios/runbooks/06_replica_promotion.md) — Scale-out / replica promotion
- [ ] Run at least one additional scenario (beyond baseline + primary kill) on one platform
- [ ] Review the results directory and understand the output structure

---

## Phase 4 — Alternate Deployment Paths (30 min)

Skim the other deployment guides so you know what's available for customer environments.

- [ ] Read [`docs/guides/K8S_COMPARISON_LAB.md`](../../docs/guides/K8S_COMPARISON_LAB.md) — Kubernetes path
- [ ] Read [`docs/guides/VM_COMPARISON_LAB.md`](../../docs/guides/VM_COMPARISON_LAB.md) — VM / bare-metal path
- [ ] Read [`docs/guides/DATA_CONSISTENCY_METHODOLOGY.md`](../../docs/guides/DATA_CONSISTENCY_METHODOLOGY.md) — How RTO/RPO is measured
- [ ] Read [`docs/guides/TROUBLESHOOTING.md`](../../docs/guides/TROUBLESHOOTING.md) — Common issues and fixes

---

## Phase 5 — Cross-Run Comparison & Templates (30 min)

- [ ] Review [`examples/results/sample_run_summary.md`](../../examples/results/sample_run_summary.md) to understand run output format
- [ ] Run `make export-summary RUN_DIR=results/<run_id>` on one of your completed runs
- [ ] Review the comparison tooling: `python3 tooling/compare_runs.py --help`
- [ ] Skim [`docs/templates/DISCOVERY_QUESTIONNAIRE.md`](../../docs/templates/DISCOVERY_QUESTIONNAIRE.md) — pre-POC discovery
- [ ] Skim [`docs/templates/POC_CHARTER_TEMPLATE.md`](../../docs/templates/POC_CHARTER_TEMPLATE.md) — POC scoping
- [ ] Skim [`docs/templates/EXECUTIVE_READOUT_TEMPLATE.md`](../../docs/templates/EXECUTIVE_READOUT_TEMPLATE.md) — post-POC deliverable

---

## ✅ Done

You should now be able to:

- Stand up any topology and run any scenario from the runbooks
- Explain the observability pipeline (Locust → Prometheus → Grafana → evidence export)
- Fill out a scorecard from real run data
- Choose the right deployment path for a customer engagement

