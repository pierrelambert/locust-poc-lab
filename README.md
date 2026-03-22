# Locust POC Lab

A portable, repeatable lab environment for running Redis Proof-of-Concept resilience and performance tests using [Locust](https://locust.io/).

## Quickstart

```bash
make setup    # Install Python dependencies
make help     # Show available targets
```

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `docs/` | Principles, blueprint, guides |
| `docs/templates/` | Charter and scorecard templates |
| `docs/guides/` | SA-facing guided labs and runbooks |
| `infra/docker/` | Docker Compose stacks (RE cluster, OSS Sentinel, OSS Cluster) |
| `infra/k8s/` | Kubernetes manifests (RE Operator, OSS on k8s) |
| `infra/scripts/` | Shared setup/teardown helpers |
| `workloads/locustfiles/` | Locust test files |
| `workloads/lib/` | Shared Python helpers (connections, data seeding) |
| `workloads/profiles/` | Workload profile configs (YAML/JSON) |
| `scenarios/scripts/` | Failure injection scripts (kill, partition, upgrade) |
| `scenarios/runbooks/` | Step-by-step scenario runbooks |
| `observability/grafana/` | Grafana dashboard JSON exports |
| `observability/prometheus/` | Prometheus config and rules |
| `observability/exporters/` | Evidence export scripts |
| `results/` | Run results (gitignored) |
