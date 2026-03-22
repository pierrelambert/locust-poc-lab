# Customer POC Scorecard Template

**Customer:** `{{ customer_name }}`  
**Opportunity:** `{{ account_or_project_name }}`  
**POC window:** `{{ start_date }} - {{ end_date }}`  
**SA owner:** `{{ sa_name }}`

## 1. Executive Summary

### Business question

`{{ What business risk or decision was this POC intended to address? }}`

### Headline conclusion

`{{ One paragraph stating whether Redis Enterprise provided the stronger resiliency, operational simplicity, and performance stability outcome. }}`

### Recommendation

`{{ Recommended next step: proceed, expand, tune, or run a follow-up scenario. }}`

## 2. Compared Solutions

| Solution | Topology | Environment | Version | Notes |
|---|---|---|---|---|
| Redis Enterprise | `{{ topology }}` | `{{ vm_or_k8s }}` | `{{ version }}` | `{{ notes }}` |
| OSS Redis | `{{ topology }}` | `{{ vm_or_k8s }}` | `{{ version }}` | `{{ notes }}` |

## 3. Agreed Success Criteria

| Criterion | Target | Result | Status |
|---|---|---|---|
| Recovery time objective | `{{ target }}` | `{{ result }}` | `{{ met_or_not }}` |
| Tail latency objective | `{{ target }}` | `{{ result }}` | `{{ met_or_not }}` |
| Error-rate objective | `{{ target }}` | `{{ result }}` | `{{ met_or_not }}` |
| Operational simplicity objective | `{{ target }}` | `{{ result }}` | `{{ met_or_not }}` |

## 4. Scenario Summary

| Scenario | Enterprise result | OSS result | Winner | Business implication |
|---|---|---|---|---|
| Steady-state baseline | `{{ summary }}` | `{{ summary }}` | `{{ winner }}` | `{{ implication }}` |
| Primary failure | `{{ summary }}` | `{{ summary }}` | `{{ winner }}` | `{{ implication }}` |
| Node loss or restart | `{{ summary }}` | `{{ summary }}` | `{{ winner }}` | `{{ implication }}` |
| Rolling upgrade or maintenance | `{{ summary }}` | `{{ summary }}` | `{{ winner }}` | `{{ implication }}` |

## 5. Evidence Highlights

### What the application experienced

- `{{ latency or error impact highlight }}`
- `{{ failover or recovery highlight }}`
- `{{ throughput stability highlight }}`

### What the operators experienced

- `{{ amount of manual intervention }}`
- `{{ clarity of observability and diagnosis }}`
- `{{ complexity of recovery or maintenance steps }}`

## 6. Detailed Findings

### Resiliency

`{{ concise explanation of how each platform behaved during failure scenarios }}`  

### Performance Stability

`{{ concise explanation of tail latency, throughput recovery, and error behavior }}`  

### Operational Simplicity

`{{ concise explanation of setup, upgrade, failover handling, and troubleshooting effort }}`  

## 7. Risks and Open Items

- `{{ unresolved question or follow-up item }}`
- `{{ environmental limitation or caveat }}`
- `{{ scenario not covered in this POC }}`

## 8. Final Recommendation

`{{ final recommendation paragraph tied back to customer priorities }}`

## 9. Evidence References

- Dashboard export: `{{ path_or_link }}`
- Raw metrics or results: `{{ path_or_link }}`
- Runbook or command log: `{{ path_or_link }}`
- Architecture notes: `{{ path_or_link }}`
