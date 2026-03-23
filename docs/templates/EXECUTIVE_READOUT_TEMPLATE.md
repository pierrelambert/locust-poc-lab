# Executive Readout

**Customer:** `{{ customer_name }}`  
**Opportunity:** `{{ opportunity_name }}`  
**POC window:** `{{ start_date }} – {{ end_date }}`  
**SA owner:** `{{ sa_name }}`  
**Presented to:** `{{ audience }}`  
**Date:** `{{ readout_date }}`

---

## 1. Purpose

This POC was conducted to answer a specific question:

> `{{ What decision should this POC unlock? Example: Should the team adopt Redis Enterprise to replace self-managed OSS Redis for the session-store tier? }}`

## 2. What We Tested

| Dimension | Detail |
|---|---|
| Workload | `{{ workload description — e.g., session store, 80/20 read/write, 50-byte values }}` |
| Compared solutions | `{{ e.g., Redis Enterprise 7.4 cluster vs. OSS Redis 7.2 Sentinel }}` |
| Environment | `{{ e.g., 3-node clusters on AWS m5.xlarge, same VPC }}` |
| Scenarios executed | `{{ e.g., steady-state baseline, primary failover, node restart, rolling upgrade }}` |

## 3. Key Findings

### Resiliency

`{{ 2-3 sentences summarizing failover and recovery behavior. Example: Redis Enterprise completed primary failover in under 200 ms with zero client errors. OSS Sentinel required approximately 4 seconds, during which the application experienced a burst of connection errors and required manual verification. }}`

### Performance Stability

`{{ 2-3 sentences on latency and throughput during normal and disrupted operation. Example: Under steady-state load, both platforms delivered comparable p99 latency (~1.2 ms). During failover, Redis Enterprise p99 spiked briefly to 8 ms before returning to baseline within seconds, while OSS p99 exceeded 1,200 ms and took over 30 seconds to stabilize. }}`

### Operational Simplicity

`{{ 2-3 sentences on operator experience. Example: Redis Enterprise required zero manual intervention across all failure scenarios. The OSS path required 3 manual recovery steps after the node-loss test and a coordinated maintenance window for the rolling upgrade. }}`

## 4. Scorecard Summary

| Criterion | Target | Redis Enterprise | OSS Redis | Winner |
|---|---|---|---|---|
| Recovery time | `{{ target }}` | `{{ result }}` | `{{ result }}` | `{{ winner }}` |
| Tail latency (p99) | `{{ target }}` | `{{ result }}` | `{{ result }}` | `{{ winner }}` |
| Error rate during failure | `{{ target }}` | `{{ result }}` | `{{ result }}` | `{{ winner }}` |
| Operator steps required | `{{ target }}` | `{{ result }}` | `{{ result }}` | `{{ winner }}` |

_Full scorecard: [POC Scorecard]({{ link_to_completed_scorecard }})_

## 5. Recommendation

`{{ 1-2 paragraphs with a clear recommendation tied to the customer's stated priorities. Include any conditions, caveats, or suggested next steps. Example: Based on the evidence collected, Redis Enterprise met or exceeded every agreed success criterion. We recommend proceeding to a production architecture review with the platform team. If the customer requires multi-region active-active, a follow-up POC focused on CRDT conflict resolution is recommended before finalizing the design. }}`

## 6. Risks and Open Items

- `{{ risk or open question }}`
- `{{ environmental caveat or limitation }}`
- `{{ follow-up action with owner }}`

## 7. Evidence References

| Artifact | Location |
|---|---|
| Run summary (JSON) | `{{ path_or_link }}` |
| Run summary (Markdown) | `{{ path_or_link }}` |
| Grafana dashboard export | `{{ path_or_link }}` |
| POC Charter | `{{ path_or_link }}` |
| Completed Scorecard | `{{ path_or_link }}` |

