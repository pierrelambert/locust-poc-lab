I want to create an easy to understand, spin-up, POC lab for Redis Solution Architects to be able to make resiliency, performance (...) comparison of Enterprise version (Redis Software , Redis enterprise operator on k8s) vs OSS Redis ( on VMs, on k8s with OSS operators) leveraging locust playbook and tooling.

It must permit to go at customer asily with a plan and material to demonstrate/measure the Enterprise version superiority, giving rythm to POC and for SA to keep ownership.

This is an initial plan, complete, make it stronger, to have something easy , rock solid , to let Redis SA appear as rockstars, and customer to wish to work with us.

# Phase 0 - Scope & Principles

**Date:** December 2025  
**Status:** ✅ **COMPLETE** - Foundation established after Phase 9.1 validation

**Purpose:** Define what we support, what we don't, and the principles that guide all future work.

---

## Executive Summary

This document establishes the **scope and principles** for the Redis Enterprise POC Learning Labs project based on:
- Phase 9.1 validation results (100% success rate)
- PURPOSE_GAP_ANALYSIS.md findings
- Real-world testing on multiple environments

**Key Decisions:**
- ✅ Focus on **guided learning experiences** for Solution Architects
- ✅ Support **tested environments** with clear documentation
- ✅ Prioritize **resiliency POC capabilities** over feature coverage
- ✅ Maintain **"it just works"** standard - no "should work" documentation

---

## 1. Project Purpose & Scope

### 1.1 Primary Purpose

**Enable Solution Architects to:**
1. **Learn** Redis deployment patterns (OSS, Sentinel, Cluster, Enterprise)
2. **Compare** Redis solutions with hands-on labs
3. **Demonstrate** Redis Enterprise resiliency to customers
4. **POC** Redis Enterprise vs other Redis on resiliency

**NOT in scope:**
- ❌ Production deployment guides (use official Redis docs)
- ❌ Feature-by-feature comparison (focus on resiliency)
- ❌ Performance benchmarking (focus on failover/recovery)
- ❌ Multi-cloud deployment (focus on learning environments)

### 1.2 Target Audience

**Primary:** New Solution Architects (0-6 months with Redis)
- First-time Redis users
- Coming from other databases
- Need hands-on learning

**Secondary:** Experienced SAs running customer POCs
- Need resiliency comparison data
- Need visual demos
- Need professional reports

**NOT for:**
- ❌ Developers (use official Redis docs)
- ❌ Production SREs (use official Redis Enterprise docs)
- ❌ Redis experts (they don't need this)

---

## 2. Supported Environments

### 2.1 Tested & Fully Supported ✅

**These environments are tested end-to-end and guaranteed to work:**

| Environment | OS | Use Case | Status | Validation |
|-------------|-----|----------|--------|------------|
| **Docker Desktop** | macOS | Local learning | ✅ Tested | Phase 9.1 |
| **Docker Desktop** | Windows (WSL2) | Local learning | ✅ Tested | Phase 9.1 |
| **Docker** | Linux | Local learning | ✅ Tested | Phase 9.1 |
| **k3d (k3s in Docker)** | macOS | k8s learning | ✅ Tested | Phase 9.1 |
| **k3d (k3s in Docker)** | Linux | k8s learning | ✅ Tested | Phase 9.1 |
| **k3s (native)** | Linux | k8s learning | ✅ Tested | Phase 9.1 |

**Guarantee:** If you follow the guides on these environments, **it will work**. If it doesn't, it's a bug.

### 2.2 Expected to Work (Best Effort) ⚠️

**These environments should work but are not regularly tested:**

| Environment | OS | Use Case | Status | Notes |
|-------------|-----|----------|--------|-------|
| **GKE** | Cloud | Production POC | ⚠️ Best effort | Use official Redis docs |
| **EKS** | Cloud | Production POC | ⚠️ Best effort | Use official Redis docs |
| **AKS** | Cloud | Production POC | ⚠️ Best effort | Use official Redis docs |
| **OpenShift** | Any | Enterprise k8s | ⚠️ Best effort | May need adjustments |

**Note:** We provide guidance but don't guarantee these work without modifications.

### 2.3 Not Supported ❌

**These environments are explicitly NOT supported:**

- ❌ **Minikube** - Use k3d instead (lighter, faster)
- ❌ **Docker Desktop on Windows (non-WSL2)** - Use WSL2
- ❌ **Podman** - Use Docker
- ❌ **Rancher Desktop** - Use k3d
- ❌ **Production environments** - Use official Redis Enterprise docs

**Reason:** Limited testing resources, better alternatives available.

---

## 3. Supported Redis Solutions

### 3.1 Fully Supported (Tested) ✅

**These solutions are tested and documented:**

| Solution | Deployment | Version | Status | Use Case |
|----------|------------|---------|--------|----------|
| **Redis OSS** | Docker | Latest | ✅ Tested | Learning basics |
| **Redis Sentinel** | Docker | Latest | ✅ Tested | HA learning |
| **Redis Cluster** | Docker | Latest | ✅ Tested | Sharding learning |
| **Redis Enterprise** | k3s | v8.0.2-17 | ✅ Tested | Enterprise learning |
| **Sentinel (Bitnami)** | k3s | Latest | ✅ Tested | OSS comparison |
| **Sentinel (Opstree)** | k3s | Latest | ✅ Tested | OSS comparison |
| **Cluster (Bitnami)** | k3s | Latest | ✅ Tested | OSS comparison |
| **Cluster (Opstree)** | k3s | Latest | ✅ Tested | OSS comparison |

### 3.2 Not Covered ❌

- ❌ **Redis Stack** - Different use case (modules)
- ❌ **KeyDB** - Not Redis
- ❌ **Dragonfly** - Not Redis
- ❌ **Valkey** - Fork, not officially supported yet

---

## 4. Core Principles

### 4.1 "It Just Works" Standard

**Principle:** Every guide must work end-to-end on supported environments without modifications.

**Rules:**
- ✅ Test on fresh environments before publishing
- ✅ Use exact commands that work (no placeholders)
- ✅ Document exact versions tested
- ✅ If it doesn't work, it's a bug (not user error)

**Anti-patterns:**
- ❌ "This should work..." - NO! Either it works or we don't document it
- ❌ "You may need to adjust..." - NO! Provide exact commands
- ❌ "Depending on your environment..." - NO! Specify supported environments

### 4.2 Guided Learning Over Automation

**Principle:** Teach manual steps first, automation second.

**Why:** SAs need to understand what's happening, not just run scripts.

**Rules:**
- ✅ Labs show step-by-step manual commands
- ✅ Explain what each command does
- ✅ Automation scripts are optional (for speed)
- ✅ Reference docs can assume knowledge

**Example:**
```bash
# ✅ GOOD - Explains what's happening
# Deploy Redis Enterprise Cluster (3 nodes)
kubectl apply -f 02-rec.yaml

# Wait for cluster to be ready (~9 minutes)
kubectl wait --for=condition=Ready --timeout=240s rec/rec -n redis-enterprise

# ❌ BAD - Just automation
./deploy-all.sh
```

### 4.3 Visual Proof Over Text

**Principle:** Show, don't tell. Use visuals for demos.

**Rules:**
- ✅ Provide Grafana dashboards for failover demos
- ✅ Use comparison tables with actual data
- ✅ Include screenshots where helpful
- ✅ Generate graphs from test results

**Why:** Customers believe what they see, not what they read.

### 4.4 Resiliency First

**Principle:** Focus on resiliency (failover, recovery) over features.

**Why:** This is Redis Enterprise's key differentiator.

**Priority:**
1. **P0:** Failover testing and comparison
2. **P1:** Recovery time measurement
3. **P1:** Data consistency validation
4. **P2:** Performance comparison
5. **P3:** Feature comparison

### 4.5 Tested Versions Only

**Principle:** Only document versions we've actually tested.

**Rules:**
- ✅ Specify exact versions in docs
- ✅ Update versions when tested
- ✅ Mark validation date
- ✅ Don't assume newer versions work

**Current tested versions (as of Dec 2025):**
- Redis Enterprise: v8.0.2-17
- Redis Enterprise Operator: v8.0.2-2
- k3s: v1.28+
- Docker: 20.10+

### 4.6 Remove, Don't Archive

**Principle:** Delete outdated content, don't mark it as "OLD".

**Why:** Clutter confuses users.

**Rules:**
- ✅ Delete files that are superseded
- ✅ Update existing files instead of creating new versions
- ✅ Use git history for old versions
- ❌ Don't create README_OLD.md, INDEX_OLD.md, etc.

---

## 5. Documentation Structure

### 5.1 Three-Tier Structure

```
labs/           # Guided learning experiences (step-by-step)
docs/reference/ # Technical reference (deep dives)
docs/validation/# Test results and planning
```

**Rules:**
- Labs = Beginner-friendly, step-by-step
- Reference = Assumes knowledge, technical details
- Validation = Internal, for maintainers

### 5.2 Lab Requirements

Every lab must have:
- ✅ Clear prerequisites
- ✅ Estimated time
- ✅ Difficulty level
- ✅ Step-by-step instructions
- ✅ Expected output
- ✅ Cleanup instructions
- ✅ Validation date

### 5.3 Reference Doc Requirements

Every reference doc must have:
- ✅ Purpose statement
- ✅ Target audience
- ✅ Table of contents
- ✅ Examples
- ✅ Troubleshooting section

---

## 6. Quality Standards

### 6.1 Testing Requirements

**Before publishing any lab:**
1. ✅ Test on fresh environment (no prior setup)
2. ✅ Follow exact commands in doc
3. ✅ Verify expected output matches
4. ✅ Test cleanup works
5. ✅ Document validation date

**Validation frequency:**
- Labs: Every 3 months or when dependencies update
- Reference docs: Every 6 months
- Validation reports: Archive after 1 year

### 6.2 Code Quality

**Python code:**
- ✅ Type hints
- ✅ Docstrings
- ✅ Unit tests (>80% coverage)
- ✅ Linting (black, flake8)

**Shell scripts:**
- ✅ Error handling (set -e)
- ✅ Comments explaining each step
- ✅ Tested on supported environments

### 6.3 Documentation Quality

**Writing style:**
- ✅ Clear, concise, beginner-friendly
- ✅ Active voice ("Deploy Redis" not "Redis should be deployed")
- ✅ Exact commands (no placeholders unless necessary)
- ✅ Explain why, not just how

---

## 7. Maintenance & Updates

### 7.1 Update Triggers

**Update documentation when:**
- ✅ Redis Enterprise releases new version
- ✅ Validation fails on supported environment
- ✅ User reports bug
- ✅ Quarterly review

### 7.2 Deprecation Policy

**When to deprecate:**
- Solution is no longer maintained (e.g., Opstree operator)
- Environment is no longer supported (e.g., k8s 1.20)
- Better alternative exists

**How to deprecate:**
1. Add deprecation notice to doc
2. Wait 3 months
3. Remove doc entirely
4. Update references

---

## 8. Success Metrics

### 8.1 Lab Success Metrics

**A lab is successful if:**
- ✅ 90%+ of SAs complete it without help
- ✅ Completion time ≤ 1.5x estimated time
- ✅ 0 critical bugs reported
- ✅ Positive feedback from SAs

### 8.2 Project Success Metrics

**The project is successful if:**
- ✅ New SAs can learn Redis in 2 hours
- ✅ SAs can run resiliency POCs with customers
- ✅ Documentation is trusted ("it just works")
- ✅ Maintenance burden is low

---

## 9. Out of Scope (Explicitly)

**These are NOT goals of this project:**

- ❌ Replace official Redis documentation
- ❌ Production deployment guides
- ❌ Comprehensive feature comparison
- ❌ Performance benchmarking suite
- ❌ Multi-cloud deployment automation
- ❌ CI/CD pipeline examples
- ❌ Application integration guides
- ❌ Security hardening guides

**For these, use official Redis documentation.**

---

## 10. Next Steps

**Based on this scope:**

**Immediate (This Week):**
1. Create `labs/RESILIENCY_POC_LAB.md` (P0)
2. Create `docs/RESILIENCY_BENCHMARKS.md` (P0)
3. Create Grafana dashboard for failover visualization (P0)

**Short-term (Next 2 Weeks):**
4. Add network partition testing lab (P1)
5. Add data consistency validation (P1)
6. Update comparison labs with resiliency focus

**Long-term (Next Month):**
7. Create customer report generator (P2)
8. Add cascading failure scenarios (P2)
9. Quarterly validation of all labs

---

**Status:** ✅ **COMPLETE** - Scope and principles established

**Approved by:** Phase 9.1 validation results (100% success rate)

**Next Phase:** Create P0 resiliency POC capabilities
