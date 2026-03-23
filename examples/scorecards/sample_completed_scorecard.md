# Customer POC Scorecard — Sample

**Customer:** Acme Financial Services  
**Opportunity:** Session-store migration  
**POC window:** 2026-02-10 – 2026-02-21  
**SA owner:** Jordan Chen

## 1. Executive Summary

### Business question

Acme's platform team needed to determine whether Redis Enterprise could replace their self-managed OSS Redis Sentinel deployment for the session-store tier, reducing failover risk and operational burden ahead of a peak-traffic product launch.

### Headline conclusion

Redis Enterprise delivered sub-200 ms failover with zero client errors across all failure scenarios, while the OSS Sentinel deployment required approximately 4 seconds to recover and produced a burst of connection errors on every primary failure. Redis Enterprise also eliminated all manual recovery steps that the OSS path required after node-loss and rolling-upgrade scenarios.

### Recommendation

Proceed to production architecture review. The evidence supports adopting Redis Enterprise for the session-store tier. A follow-up POC for the real-time analytics workload is recommended before expanding scope.

## 2. Compared Solutions

| Solution | Topology | Environment | Version | Notes |
|---|---|---|---|---|
| Redis Enterprise | 3-node cluster, 1 shard, 1 replica | AWS m5.xlarge, us-east-1 | 7.4.2 | Active-passive replication |
| OSS Redis | 3-node Sentinel, 1 primary + 2 replicas | AWS m5.xlarge, us-east-1 | 7.2.4 | Sentinel quorum = 2 |

## 3. Agreed Success Criteria

| Criterion | Target | Result | Status |
|---|---|---|---|
| Recovery time objective | < 1 s | RE: 180 ms / OSS: 4.1 s | ✅ RE met |
| Tail latency (p99) during failure | < 50 ms | RE: 8 ms / OSS: 1,240 ms | ✅ RE met |
| Error rate during failure | < 0.1 % | RE: 0.00 % / OSS: 2.3 % | ✅ RE met |
| Operator steps for recovery | 0 manual steps | RE: 0 / OSS: 3 | ✅ RE met |

## 4. Scenario Summary

| Scenario | Enterprise result | OSS result | Winner | Business implication |
|---|---|---|---|---|
| Steady-state baseline | p99 1.1 ms, 12,480 ops/s, 0 errors | p99 1.2 ms, 12,310 ops/s, 0 errors | Comparable | Both platforms handle baseline load well |
| Primary failure | 180 ms recovery, 0 errors | 4.1 s recovery, 2.3 % error burst | RE | RE eliminates session-loss risk during failover |
| Node loss or restart | Auto-recovery, 0 manual steps | Required manual replica promotion | RE | RE reduces on-call burden |
| Rolling upgrade | Zero-downtime upgrade, p99 < 2 ms | 12 s maintenance window, p99 spike to 800 ms | RE | RE enables upgrades without change windows |

## 5. Evidence Highlights

### What the application experienced

- RE maintained p99 latency under 8 ms even during primary failover; OSS p99 exceeded 1,200 ms
- RE produced zero client-visible errors across all scenarios; OSS produced 2.3 % error rate during failover
- Throughput recovered to baseline within 2 seconds on RE vs. 35 seconds on OSS

### What the operators experienced

- RE required zero manual intervention across all four scenarios
- OSS required 3 manual steps after node-loss (verify sentinel state, promote replica, reconfigure app)
- RE provided built-in cluster health dashboard; OSS required custom monitoring setup

## 6. Detailed Findings

### Resiliency

Redis Enterprise detected primary failure and completed automatic failover in 180 ms. The proxy layer absorbed the transition, and the client connection remained intact. OSS Sentinel detected the failure after its configured `down-after-milliseconds` (2,000 ms), then required an additional ~2 seconds for leader election and promotion, totaling 4.1 seconds of unavailability.

### Performance Stability

Under steady-state load (50 concurrent users, 80/20 read/write, 50-byte session payloads), both platforms delivered comparable latency (p99 ~1.1–1.2 ms) and throughput (~12,400 ops/s). During the primary-failure scenario, RE p99 spiked briefly to 8 ms before returning to baseline within 2 seconds. OSS p99 exceeded 1,200 ms and required over 30 seconds to fully stabilize.

### Operational Simplicity

RE cluster management handled shard placement, failover, and rebalancing without operator input. The rolling-upgrade scenario completed with zero downtime on RE. The OSS path required a coordinated maintenance window, manual sentinel reconfiguration, and post-upgrade verification — 3 distinct operator actions.

## 7. Risks and Open Items

- Multi-region active-active was not tested; recommended as a follow-up if geo-distribution is required
- Persistence (AOF/RDB) was disabled for both platforms during this POC to isolate network behavior
- Cost comparison was out of scope; procurement team to evaluate licensing separately

## 8. Final Recommendation

Based on the evidence collected across four scenarios, Redis Enterprise met or exceeded every agreed success criterion. The platform delivered sub-second failover, zero client errors, and zero manual recovery steps — directly addressing Acme's concerns about session-loss risk and operational burden. We recommend proceeding to a production architecture review with the platform team, targeting the session-store tier as the initial workload.

## 9. Evidence References

- Dashboard export: `examples/results/sample_run_summary.md`
- Raw metrics or results: `examples/results/sample_run_summary.json`
- Runbook or command log: `docs/runbooks/`
- Architecture notes: `docs/templates/POC_CHARTER_TEMPLATE.md`

