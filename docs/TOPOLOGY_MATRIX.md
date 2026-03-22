# Topology Matrix

**Last updated:** March 22, 2026
**Status:** Draft — Phase 1 foundation document

## 1. Day-1 Reference Architectures

The following five architectures form the complete Day-1 comparison matrix. Each architecture is required before the lab is considered runnable.

| # | Architecture | Deployment Mode | Min Nodes | Min Replicas | vCPU per Node | RAM per Node | Persistence Default | TLS Posture | Comparison Pairing |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Redis Enterprise Software on VMs | VM (Docker containers) | 3 | 1 per shard | 2 vCPU | 4 GB | AOF every 1 sec | TLS off (optional enable) | Pairs with #3 (HA) and #4 (Cluster) |
| 2 | Redis Enterprise Operator on k8s | Kubernetes | 3 pods | 1 per shard | 2 vCPU | 4 GB | AOF every 1 sec | TLS off (optional enable) | Pairs with #5 |
| 3 | OSS Redis with Sentinel on VMs | VM (Docker containers) | 3 (1 primary + 2 replicas) + 3 Sentinels | 2 | 1 vCPU | 2 GB | AOF every 1 sec | TLS off (optional enable) | Pairs with #1 (HA comparison) |
| 4 | OSS Redis Cluster on VMs | VM (Docker containers) | 6 (3 primaries + 3 replicas) | 1 per primary | 1 vCPU | 2 GB | AOF every 1 sec | TLS off (optional enable) | Pairs with #1 (Cluster comparison) |
| 5 | OSS Redis on k8s (operator or chart) | Kubernetes | 3 pods (1 primary + 2 replicas) + 3 Sentinel pods | 2 | 1 vCPU | 2 GB | AOF every 1 sec | TLS off (optional enable) | Pairs with #2 |

### Resource totals for local development

| Architecture | Total vCPU | Total RAM | Suitable for Docker Desktop (8 GB) | Suitable for Docker Desktop (16 GB) |
|---|---|---|---|---|
| #1 RE Software on VMs | 6 vCPU | 12 GB | No | Yes (tight) |
| #2 RE Operator on k8s | 6 vCPU | 12 GB | No | Yes (tight) |
| #3 OSS Sentinel on VMs | 3 vCPU + Sentinels | 6 GB + Sentinels | Marginal | Yes |
| #4 OSS Cluster on VMs | 6 vCPU | 12 GB | No | Yes (tight) |
| #5 OSS on k8s | 3 vCPU + Sentinels | 6 GB + Sentinels | Marginal | Yes |

> **Recommendation:** Allocate at least 16 GB RAM and 6 vCPU to Docker Desktop for any comparison pair. A machine with 32 GB RAM is strongly preferred when running both sides of a comparison simultaneously.

## 2. Comparison Pairing Rules

Comparisons must follow the fairness rules established in the Phase 0 charter and the execution blueprint.

### Mandatory pairing constraints

| Comparison Type | Enterprise Side | OSS Side | Rule |
|---|---|---|---|
| HA vs HA | #1 — RE Software (3-node cluster, single DB with replication) | #3 — OSS Sentinel (1 primary + 2 replicas + 3 Sentinels) | Both must have replication enabled, same persistence posture, same TLS posture |
| Cluster vs Cluster | #1 — RE Software (3-node cluster, sharded DB) | #4 — OSS Cluster (3 primaries + 3 replicas) | Same shard count, same persistence, same dataset size |
| k8s vs k8s | #2 — RE Operator | #5 — OSS k8s operator or chart | Same namespace isolation, same resource requests, same persistence |

### What is NOT a valid comparison

- Redis Enterprise HA vs single-node OSS Redis (strawman)
- Redis Enterprise Cluster vs OSS Sentinel (mismatched architecture class)
- Any comparison where one side has persistence disabled and the other does not
- Any comparison where TLS is enabled on one side only without declaring it as the test variable

## 3. Tier 1 Environment Compatibility

These are the supported local development environments for Day-1 labs.

| Environment | VM Architectures (#1, #3, #4) | k8s Architectures (#2, #5) | Notes |
|---|---|---|---|
| Docker Desktop on macOS | ✅ Supported | ✅ Via built-in Kubernetes | Allocate ≥16 GB RAM, ≥6 vCPU in Docker Desktop settings |
| Docker Desktop on Windows (WSL2) | ✅ Supported | ✅ Via built-in Kubernetes | Ensure WSL2 backend is enabled; allocate resources via `.wslconfig` |
| Docker on Linux | ✅ Supported | ❌ Requires separate k8s | Use k3d or k3s for Kubernetes paths |
| k3d on macOS or Linux | N/A | ✅ Supported | Lightweight k3s-in-Docker; preferred for portable k8s demos |
| k3s on Linux | N/A | ✅ Supported | Bare-metal k3s; preferred for field and lab environments |

### Environment-specific guidance

- **Docker Desktop Kubernetes** is the simplest path for running both VM-style (Docker Compose) and k8s architectures on a single laptop.
- **k3d** is preferred over Docker Desktop Kubernetes when the SA needs a disposable, fast-cycling cluster.
- **k3s** is preferred for persistent lab environments or when running on a dedicated Linux host.

## 4. Not Yet Supported (Deferred Variants)

The following variants are explicitly deferred until the primary five-architecture matrix is stable and validated.

| Variant | Reason for Deferral |
|---|---|
| Redis Enterprise Cloud (managed service) | Different operational model; not a topology the SA deploys locally |
| Redis Enterprise Active-Active (CRDB) | Adds geo-distribution complexity; requires multi-cluster setup |
| OSS Redis Cluster on Kubernetes | Requires a separate operator or StatefulSet pattern; add after #5 is stable |
| Alternative OSS k8s operators (e.g., Spotahome, OpsTree) | One primary implementation first; extras add maintenance burden |
| Minikube | Not a Tier 1 target; resource overhead and networking quirks |
| Podman-only environments | Not a Tier 1 target; Docker compatibility layer is inconsistent |
| Rancher Desktop as primary path | Not a Tier 1 target; use Docker Desktop or k3d instead |
| Non-WSL2 Windows Docker | Not supported; WSL2 is required for Windows |
| ARM64-native builds | Defer until x86_64 matrix is validated; Apple Silicon runs via Rosetta in Docker Desktop |
| TLS-everywhere as default posture | TLS is optional-enable; a TLS-focused comparison can be added as a scenario variant |

### Promotion criteria

A deferred variant may be promoted to the active matrix when:

1. all five Day-1 architectures have been validated end-to-end on at least one Tier 1 environment,
2. the new variant has a clear customer or field demand signal,
3. a maintainer commits to keeping the variant's lab path current,
4. and the addition does not destabilize existing comparison paths.

