# Customer POC Charter Template

**Customer:** `{{ customer_name }}`  
**Opportunity:** `{{ opportunity_name }}`  
**SA owner:** `{{ sa_name }}`  
**Customer sponsor:** `{{ sponsor_name }}`  
**Start date:** `{{ start_date }}`  
**Target readout date:** `{{ readout_date }}`

## 1. Decision This POC Supports

`{{ What decision should this POC unlock? Example: choose Redis Enterprise for the target production architecture. }}`

## 2. Customer Context

### Business driver

`{{ Why is this POC happening now? }}`

### Workload in focus

`{{ Describe the application or workload being represented in the POC. }}`

### Critical risk being evaluated

`{{ Example: failover disruption, operator burden, latency under maintenance, scaling complexity. }}`

## 3. Success Criteria

| Priority | Criterion | Target | How measured |
|---|---|---|---|
| P1 | `{{ criterion }}` | `{{ target }}` | `{{ metric or observation }}` |
| P2 | `{{ criterion }}` | `{{ target }}` | `{{ metric or observation }}` |
| P3 | `{{ criterion }}` | `{{ target }}` | `{{ metric or observation }}` |

## 4. Compared Solutions

| Solution | Deployment mode | Environment | Version target | Owner |
|---|---|---|---|---|
| Redis Enterprise | `{{ vm_or_k8s }}` | `{{ environment }}` | `{{ version }}` | `{{ owner }}` |
| OSS Redis | `{{ vm_or_k8s }}` | `{{ environment }}` | `{{ version }}` | `{{ owner }}` |

## 5. In-Scope Workloads

| Workload | Why it matters | Read/write mix | SLA signal |
|---|---|---|---|
| `{{ workload_name }}` | `{{ business relevance }}` | `{{ ratio }}` | `{{ signal }}` |
| `{{ workload_name }}` | `{{ business relevance }}` | `{{ ratio }}` | `{{ signal }}` |

## 6. In-Scope Scenarios

| Scenario | Why included | Evidence expected |
|---|---|---|
| Steady-state baseline | establish normal behavior | latency, throughput, error rate |
| Primary failure | compare failover quality | recovery time, error burst, operator steps |
| Node loss or restart | compare infrastructure event handling | app impact, recovery path |
| Rolling maintenance or upgrade | compare day-2 operations | continuity, operator complexity |

## 7. Rules of Engagement

- Same workload shape and client path for both compared solutions
- Same declared persistence and replica-read posture unless the scenario explicitly tests a difference
- All tuning changes must be documented
- Any manual recovery action must be recorded and counted
- All claims in the final readout must tie back to captured evidence

## 8. Working Rhythm

| Milestone | Date | Owner | Expected output |
|---|---|---|---|
| Kickoff and charter signoff | `{{ date }}` | `{{ owner }}` | approved scope |
| Environment readiness check | `{{ date }}` | `{{ owner }}` | deployment verified |
| Baseline run review | `{{ date }}` | `{{ owner }}` | baseline metrics |
| Failure scenario review | `{{ date }}` | `{{ owner }}` | comparative evidence |
| Final readout | `{{ date }}` | `{{ owner }}` | scorecard and recommendation |

## 9. Roles and Responsibilities

| Role | Name | Responsibility |
|---|---|---|
| SA owner | `{{ name }}` | scenario ownership, narrative, final recommendation |
| Customer sponsor | `{{ name }}` | business criteria and final decision alignment |
| Customer operator | `{{ name }}` | environment access, operational feedback |
| Redis specialist | `{{ name }}` | escalation support only when needed |

## 10. Risks and Assumptions

- `{{ risk or dependency }}`
- `{{ environmental assumption }}`
- `{{ scenario limitation }}`

## 11. Exit Criteria

The POC is complete when:

- agreed scenarios have been executed,
- evidence has been captured and reviewed,
- the scorecard has been delivered,
- and the customer can make or advance the target decision.
