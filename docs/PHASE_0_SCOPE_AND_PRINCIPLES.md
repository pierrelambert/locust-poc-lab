# Phase 0: Scope and Principles

**Last updated:** March 22, 2026  
**Status:** Draft foundation for repo build-out

## Executive Summary

This project exists to help Redis Solution Architects run customer-facing POCs that clearly demonstrate why Redis Enterprise is the stronger choice for resiliency, operational simplicity, and performance stability.

The lab will compare:

- Redis Enterprise Software on VMs
- Redis Enterprise Operator on Kubernetes
- OSS Redis on VMs
- OSS Redis on Kubernetes with OSS operators or charts

The lab will use Locust as the standard workload driver, a small catalog of realistic workloads, and a fixed set of failure scenarios to produce evidence that is easy for customers to understand and hard to dispute.

## 1. Mission

### Primary mission

Enable Redis Solution Architects to:

1. learn the behavior of Redis deployment patterns in a hands-on way;
2. run disciplined customer POCs that compare Enterprise and OSS under pressure;
3. produce clear evidence on failover quality, recovery, operational effort, and SLA impact;
4. keep ownership of the technical story and the meeting rhythm throughout the POC.

### Business outcome

The output of this project is not just a lab. It is a repeatable pre-sales motion that helps customers conclude, with confidence, that Redis Enterprise is the safer and simpler platform for critical workloads.

## 2. Target Users and Roles

### Primary users

- New Solution Architects who need a structured way to learn Redis topologies and customer proof patterns
- Experienced Solution Architects who need a fast, credible, customer-ready comparison framework

### Supporting roles

- Customer sponsor who cares about business risk, uptime, and decision speed
- Customer operator or platform owner who cares about installation, upgrades, recovery, and operational burden
- Redis specialist who can be pulled in when the engagement needs deeper product expertise

### Ownership model

The SA owns:

- the POC charter,
- the agreed success criteria,
- the scenario order,
- the measurement narrative,
- and the final recommendation.

Specialists support. They do not replace the SA as the face of the engagement.

## 3. In Scope

The first releases of this project should cover the following comparison dimensions:

- Resiliency and failover behavior
- Recovery time and stability after disruption
- Performance under steady state and during failure or maintenance events
- Operational simplicity, especially on Kubernetes
- Evidence capture, dashboards, and customer-ready reporting
- A small set of realistic workload patterns driven by Locust

## 4. Explicitly Out of Scope

The following items are not day-1 goals:

- exhaustive feature-by-feature comparison,
- generic cloud automation for every provider,
- production hardening guidance for all environments,
- vanity benchmarks built around unrealistic synthetic traffic,
- comparison against non-Redis-compatible databases,
- and broad developer onboarding material unrelated to the POC motion.

If a choice does not help an SA run a stronger Redis Enterprise proof, it is not a priority.

## 5. Comparison Philosophy

This project must remain credible. That requires explicit comparison rules.

### Rule 1: Compare complete solutions, not strawmen

Do not compare Redis Enterprise HA to single-node OSS Redis and call that meaningful. The standard comparison set should always align to the customer conversation:

- HA versus HA
- cluster versus cluster
- Kubernetes operator versus Kubernetes operator or charted equivalent

### Rule 2: Optimize for customer-relevant outcomes

Prioritize outcomes customers feel directly:

- application errors,
- latency spikes,
- time to fail over,
- time to recover normal throughput,
- data loss or inconsistency,
- operator actions required,
- and time to understand what happened.

### Rule 3: Pre-declare workload and failure scenarios

The lab must publish the workload profile, topology, hardware assumptions, and injected failure type before each run. This prevents ad hoc interpretation after the fact.

### Rule 4: Make tuning explicit

If one side requires special tuning, manual repair, or expert intervention, that is part of the comparison result, not something to hide.

### Rule 5: Measure performance stability, not only peak throughput

Raw throughput matters less than:

- whether latency stays inside SLA,
- whether errors remain bounded,
- whether the system recovers quickly,
- and whether the operator had to scramble.

### Rule 6: Use repeatable defaults

A narrow, well-tested comparison is more valuable than a huge matrix that only works once. The repo should standardize on a small number of topologies and workload profiles.

## 6. Support Tiers

These are target support tiers for the initial build. They are not yet validation claims.

### Tier 1: Core build targets

- Docker Desktop on macOS
- Docker Desktop on Windows with WSL2
- Docker on Linux
- k3d on macOS or Linux for portable Kubernetes demos
- k3s on Linux for field and lab environments

### Tier 2: Secondary targets

- Customer-owned Kubernetes distributions where the SA needs to transpose the lab
- Public cloud Kubernetes platforms after the core lab is stable

### Not supported in the initial motion

- Minikube
- Podman-only environments
- Rancher Desktop as a primary path
- Non-WSL2 Windows Docker flows

The project should be opinionated here. Field velocity is more important than supporting every local setup.

## 7. Solution Coverage

### Enterprise reference stacks

- Redis Enterprise Software on VMs for cluster, failover, and operational recovery demonstrations
- Redis Enterprise Operator on Kubernetes for day-2 operations, failover, scaling, and upgrade demonstrations

### OSS reference stacks

- OSS Redis with Sentinel on VMs for HA comparison
- OSS Redis Cluster on VMs for sharded comparison
- OSS Redis on Kubernetes using one primary operator or charted implementation as the day-1 baseline

### Coverage principle

The first release should favor one strong baseline per architecture over many partially maintained variants. Extra OSS operators can be added later, but the core motion must stay easy to run and easy to explain.

## 8. Core Principles

### 8.1 It Must Work End-to-End

If a guide is published as supported, an SA should be able to follow it on a clean environment and complete it without improvisation.

### 8.2 Guided Learning Before Full Automation

The repo should teach what is happening before hiding everything behind scripts. SAs need to explain the system, not just launch it.

### 8.3 Fast Time to First Proof

The initial local or portable path should produce a first useful result quickly:

- first environment standing up in less than 30 minutes,
- first baseline workload in less than 15 minutes after install,
- first visible failure comparison in less than 2 hours.

### 8.4 Visual Evidence Beats Verbal Claims

Every important scenario should yield:

- a dashboard,
- a timeline of the injected event,
- a simple scorecard,
- and a short explanation of business impact.

### 8.5 Resiliency First, Performance Second, Peak Numbers Last

The priority order is:

1. resiliency under failure,
2. performance stability during disruption,
3. operational effort to stay healthy,
4. steady-state efficiency,
5. raw best-case benchmark numbers.

### 8.6 Field Credibility Over Internal Optimism

No claims should be written as complete, validated, or guaranteed without recorded evidence in the repo. Validation status must be earned and dated.

### 8.7 SA Ownership Is a Product Requirement

The lab is incomplete if it produces good graphs but leaves the SA dependent on ad hoc help to run the motion.

### 8.8 Narrow Defaults, Explicit Extensions

Day-1 defaults should be small in number and heavily documented. Optional expansions should be clearly marked as stretch paths.

## 9. Measurement Standards

Each benchmark or failure scenario should capture four classes of evidence.

### Client-side evidence

- throughput,
- p50, p95, and p99 latency,
- error rate,
- reconnect and retry behavior,
- time to resume target throughput.

### Server and platform evidence

- memory,
- CPU,
- connected clients,
- blocked clients,
- operations per second,
- replication or synchronization lag,
- failover events,
- Kubernetes events and pod restarts where applicable.

### Operational evidence

- number of human interventions,
- number of commands executed outside the planned runbook,
- time to diagnose the issue,
- time to restore confidence in normal service.

### Business-facing evidence

- SLA breach duration,
- visible application disruption,
- risk of lost writes or stale reads,
- operator confidence and explainability.

## 10. Lab Quality Standards

Every published lab must contain:

- prerequisites,
- exact supported environment,
- estimated time,
- topology description,
- workload profile used,
- expected outputs,
- cleanup steps,
- validation status with date,
- and troubleshooting for the known failure modes.

Every benchmark run should also record:

- software versions,
- hardware or node sizing,
- persistence settings,
- client configuration,
- and whether replica reads or special tuning were enabled.

## 11. Success Metrics

This project is successful when:

- a new SA can run the core lab without expert help,
- a field SA can produce a professional POC package quickly,
- customers can understand the result without decoding internal Redis jargon,
- and the Redis Enterprise advantage is visible in both technical and operational terms.

## 12. Phase 1 Exit Criteria

Phase 1 should be considered complete only when the repo contains:

- one approved topology matrix,
- one approved Locust workload catalog,
- one approved failure scenario matrix,
- one dashboard pack,
- one scorecard template,
- and one end-to-end guided path that has been run successfully on a clean Tier 1 environment.

## 13. Immediate Next Steps

1. Build the execution blueprint and standard POC rhythm.
2. Select the minimal day-1 topology set for VM and Kubernetes comparisons.
3. Define the first three Locust workloads and the first four failure scenarios.
4. Create the scorecard, dashboard, and customer readout templates.
5. Validate the first end-to-end path before broadening the matrix.
