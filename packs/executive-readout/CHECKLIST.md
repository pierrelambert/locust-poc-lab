# Executive Readout Checklist

Step-by-step guide to producing post-POC executive deliverables from your run data.

---

## Phase 1 — Gather Evidence (30 min)

- [ ] Locate all completed run directories under `results/`
- [ ] Export summaries for each run: `make export-summary RUN_DIR=results/<run_id>`
- [ ] Collect Grafana dashboard snapshots (failover moments, recovery curves)
- [ ] Review consistency checker output for each failure scenario
- [ ] Review RTO/RPO reports: `python3 tooling/rto_rpo_report.py` — see [`docs/guides/DATA_CONSISTENCY_METHODOLOGY.md`](../../docs/guides/DATA_CONSISTENCY_METHODOLOGY.md)
- [ ] Run cross-platform comparison: `python3 tooling/compare_runs.py`
- [ ] Reference [`examples/results/sample_run_summary.md`](../../examples/results/sample_run_summary.md) for expected output format

---

## Phase 2 — Fill Out the Scorecard (60 min)

- [ ] Copy [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md) to your working directory
- [ ] Fill in customer metadata (name, opportunity, POC window, SA owner)
- [ ] Write the executive summary — business question and headline conclusion
- [ ] Fill in the scenario results table with data from your run summaries
- [ ] Add RTO/RPO numbers for each failure scenario
- [ ] Add data consistency results (canary writer pass/fail, lost writes)
- [ ] Score each evaluation dimension using evidence from your runs
- [ ] Write the overall recommendation
- [ ] Compare against [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md) for completeness

---

## Phase 3 — Draft the Executive Readout (60 min)

- [ ] Copy [`docs/templates/EXECUTIVE_READOUT_TEMPLATE.md`](../../docs/templates/EXECUTIVE_READOUT_TEMPLATE.md) to your working directory
- [ ] Fill in customer metadata and purpose statement
- [ ] Write the methodology section — what was tested, how, on what infrastructure
- [ ] Summarize key findings with specific numbers from the scorecard
- [ ] Include 2–3 Grafana snapshots that tell the story (baseline vs failover)
- [ ] Write the comparison table — RE vs OSS across key dimensions
- [ ] Draft 3–5 recommendations backed by specific evidence
- [ ] Write the proposed next steps section

---

## Phase 4 — Prepare for Presentation (30 min)

- [ ] Review the readout end to end — does it tell a clear story?
- [ ] Verify all numbers match between scorecard and readout
- [ ] Prepare for likely questions:
  - _"What happens with [scenario not tested]?"_ — reference available runbooks in [`scenarios/runbooks/`](../../scenarios/runbooks/)
  - _"Can we run this in our environment?"_ — reference deployment guides in [`docs/guides/`](../../docs/guides/)
  - _"What about TLS?"_ — reference `docs/guides/TLS_SETUP_GUIDE.md` (if available)
- [ ] Have the live lab ready as backup in case the customer wants to see a scenario re-run
- [ ] Share the readout with your manager or SE lead for review before presenting

---

## ✅ Done

You should now have:

- A completed POC scorecard with real evidence
- An executive readout document ready for customer presentation
- Talking points and backup materials for the readout meeting

