# Customer Demo Pack

**Audience:** SA delivering a live 60-minute demo to a customer  
**Time budget:** 60 minutes (live) + 30 minutes pre-demo prep  
**Goal:** Show a real failover comparison between Redis Enterprise and OSS Redis, with live Grafana dashboards and concrete evidence.

---

## What You'll Show

1. **Baseline** — Both platforms running a realistic workload at steady state
2. **Primary kill** — Kill the Redis primary on both platforms and watch recovery in real time
3. **Evidence** — Grafana dashboards, RTO/RPO numbers, data consistency proof

## What the Customer Takes Away

- Side-by-side failover comparison with real numbers (not slides)
- Understanding of Redis Enterprise's sub-second failover vs OSS Sentinel's multi-second recovery
- Confidence that the POC lab can be run in their own environment

## Key References

| Resource | Path |
|----------|------|
| SA Guided Lab (demo basis) | [`docs/guides/SA_GUIDED_LAB.md`](../../docs/guides/SA_GUIDED_LAB.md) |
| Baseline runbook | [`scenarios/runbooks/01_baseline.md`](../../scenarios/runbooks/01_baseline.md) |
| Primary kill runbook | [`scenarios/runbooks/02_primary_kill.md`](../../scenarios/runbooks/02_primary_kill.md) |
| Scorecard template | [`docs/templates/POC_SCORECARD_TEMPLATE.md`](../../docs/templates/POC_SCORECARD_TEMPLATE.md) |
| Sample scorecard | [`examples/scorecards/sample_completed_scorecard.md`](../../examples/scorecards/sample_completed_scorecard.md) |
| Troubleshooting | [`docs/guides/TROUBLESHOOTING.md`](../../docs/guides/TROUBLESHOOTING.md) |

## Next Step

Open [`CHECKLIST.md`](CHECKLIST.md) and work through the pre-demo prep the day before.

