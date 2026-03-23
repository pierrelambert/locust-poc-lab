# Executive Readout Pack

**Audience:** SA preparing post-POC executive deliverables  
**Time budget:** 2–4 hours  
**Goal:** Transform raw POC evidence into a polished scorecard and executive readout with clear recommendations.

---

## What You'll Do

1. Gather all evidence from completed POC runs (results, Grafana snapshots, consistency reports)
2. Fill out the POC scorecard with real data
3. Draft the executive readout document
4. Prepare recommendations and next-step proposals

## What You'll Produce

- A completed POC scorecard
- An executive readout document ready for customer presentation
- A clear set of recommendations backed by evidence

## Prerequisites

This pack assumes you have already completed POC runs and have results in the `results/` directory. If not, use the [Multi-Day Comparison Pack](../multi-day-comparison/) or [SA Enablement Pack](../sa-enablement/) first.

## Key References

| Resource | Path |
|----------|------|
| Scorecard template | [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md) |
| Sample scorecard | [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md) |
| Executive Readout template | [`docs/templates/EXECUTIVE_READOUT_TEMPLATE.md`](../../docs/templates/EXECUTIVE_READOUT_TEMPLATE.md) |
| Sample run summary | [`examples/results/sample_run_summary.md`](../../examples/results/sample_run_summary.md) |
| Cross-run comparison tool | `tooling/compare_runs.py` |
| RTO/RPO report tool | `tooling/rto_rpo_report.py` |
| Data Consistency Methodology | [`docs/guides/DATA_CONSISTENCY_METHODOLOGY.md`](../../docs/guides/DATA_CONSISTENCY_METHODOLOGY.md) |
| Run summary exporter | `make export-summary RUN_DIR=results/<run_id>` |

## Next Step

Open [`CHECKLIST.md`](CHECKLIST.md) and work through it in order.

