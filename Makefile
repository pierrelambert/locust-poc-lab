.PHONY: help setup lint clean export-summary test-smoke
.PHONY: re-up re-down re-status
.PHONY: k8s-scenario-baseline k8s-scenario-primary-kill
.PHONY: oss-sentinel-up oss-sentinel-down oss-sentinel-status
.PHONY: oss-cluster-up oss-cluster-down oss-cluster-status
.PHONY: vm-up vm-down vm-status
.PHONY: k3d-up k3d-down
.PHONY: k8s-re-up k8s-re-down k8s-re-status
.PHONY: k8s-oss-up k8s-oss-down k8s-oss-status
.PHONY: k8s-up k8s-down k8s-status
.PHONY: obs-up obs-down obs-status
.PHONY: validate cleanup-all

COMPOSE = docker compose

# --- k8s Configuration ---
RE_OPERATOR_VERSION ?= v7.8.2-6
RE_OPERATOR_BUNDLE_REMOTE ?= https://raw.githubusercontent.com/RedisLabs/redis-enterprise-k8s-docs/$(RE_OPERATOR_VERSION)/bundle.yaml
RE_OPERATOR_BUNDLE ?= infra/k8s/re-operator/operator-bundle.yaml
RE_NAMESPACE ?= redis-enterprise
OSS_NAMESPACE ?= redis-oss

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

setup: ## Bootstrap environment (prerequisites + venv + pinned deps)
	@bash scripts/bootstrap.sh

lint: ## Run linters
	@echo "TODO: configure linters"

export-summary: ## Export run summary (JSON + markdown) from a results directory. Usage: make export-summary RUN_DIR=results/<run_id>
	python3 observability/exporters/run_summary_exporter.py $(RUN_DIR)

test-smoke: ## Run smoke tests (non-Docker)
	.venv/bin/pytest tests/smoke/ -k "not docker" -v

clean: ## Remove caches and temporary files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .venv

# ── Redis Enterprise Software (3-node cluster) ─────────────────────
re-up: ## Start Redis Enterprise 3-node cluster
	$(COMPOSE) -f infra/docker/re-cluster/docker-compose.yml -p re-cluster up -d

re-down: ## Stop Redis Enterprise cluster and remove containers
	$(COMPOSE) -f infra/docker/re-cluster/docker-compose.yml -p re-cluster down

re-status: ## Show Redis Enterprise cluster container status
	$(COMPOSE) -f infra/docker/re-cluster/docker-compose.yml -p re-cluster ps

# ── OSS Redis with Sentinel (1 primary + 2 replicas + 3 sentinels) ─
oss-sentinel-up: ## Start OSS Redis Sentinel stack
	$(COMPOSE) -f infra/docker/oss-sentinel/docker-compose.yml -p oss-sentinel up -d

oss-sentinel-down: ## Stop OSS Redis Sentinel stack and remove containers
	$(COMPOSE) -f infra/docker/oss-sentinel/docker-compose.yml -p oss-sentinel down

oss-sentinel-status: ## Show OSS Redis Sentinel container status
	$(COMPOSE) -f infra/docker/oss-sentinel/docker-compose.yml -p oss-sentinel ps

# ── OSS Redis Cluster (6 nodes: 3 primaries + 3 replicas) ──────────
oss-cluster-up: ## Start OSS Redis Cluster (6 nodes)
	$(COMPOSE) -f infra/docker/oss-cluster/docker-compose.yml -p oss-cluster up -d

oss-cluster-down: ## Stop OSS Redis Cluster and remove containers
	$(COMPOSE) -f infra/docker/oss-cluster/docker-compose.yml -p oss-cluster down

oss-cluster-status: ## Show OSS Redis Cluster container status
	$(COMPOSE) -f infra/docker/oss-cluster/docker-compose.yml -p oss-cluster ps

# ── Convenience: all VM stacks ──────────────────────────────────────
vm-up: re-up oss-sentinel-up oss-cluster-up ## Start all VM-path stacks
vm-down: re-down oss-sentinel-down oss-cluster-down ## Stop all VM-path stacks
vm-status: re-status oss-sentinel-status oss-cluster-status ## Status of all VM-path stacks



# ── k3d Cluster ────────────────────────────────────────────────────
k3d-up: ## Create k3d cluster for k8s comparison paths
	@bash infra/scripts/k3d-setup.sh create

k3d-down: ## Delete k3d cluster
	@bash infra/scripts/k3d-setup.sh delete

# ── Redis Enterprise Operator on k8s (Architecture #2) ────────────
k8s-re-up: ## Deploy Redis Enterprise Operator + cluster + database on k8s
	kubectl apply -f infra/k8s/re-operator/namespace.yaml
	@echo "Installing Redis Enterprise Operator bundle $(RE_OPERATOR_VERSION)..."
	kubectl apply -f $(RE_OPERATOR_BUNDLE) -n $(RE_NAMESPACE)
	@echo "Waiting for operator to be ready..."
	kubectl rollout status deployment/redis-enterprise-operator -n $(RE_NAMESPACE) --timeout=180s || true
	@echo "Creating Redis Enterprise Cluster..."
	kubectl apply -f infra/k8s/re-operator/rec.yaml
	@echo "Waiting for REC pods (this may take several minutes)..."
	kubectl rollout status statefulset/rec-poc-lab -n $(RE_NAMESPACE) --timeout=600s || true
	@echo "Creating Redis Enterprise Database..."
	kubectl apply -f infra/k8s/re-operator/redb.yaml
	@echo "Redis Enterprise deployed. Run 'make k8s-re-status' to check."

k8s-re-down: ## Tear down Redis Enterprise from k8s
	kubectl delete -f infra/k8s/re-operator/redb.yaml --ignore-not-found
	kubectl delete -f infra/k8s/re-operator/rec.yaml --ignore-not-found
	kubectl delete -f $(RE_OPERATOR_BUNDLE) -n $(RE_NAMESPACE) --ignore-not-found || true
	kubectl delete -f infra/k8s/re-operator/namespace.yaml --ignore-not-found

k8s-re-status: ## Show Redis Enterprise k8s status
	@echo "=== Redis Enterprise Cluster ==="
	@kubectl get rec -n $(RE_NAMESPACE) 2>/dev/null || echo "No REC found"
	@echo ""
	@echo "=== Redis Enterprise Database ==="
	@kubectl get redb -n $(RE_NAMESPACE) 2>/dev/null || echo "No REDB found"
	@echo ""
	@echo "=== Pods ==="
	@kubectl get pods -n $(RE_NAMESPACE) 2>/dev/null || echo "No pods found"

# ── OSS Redis on k8s with Sentinel (Architecture #5) ──────────────
k8s-oss-up: ## Deploy OSS Redis with Sentinel on k8s
	kubectl apply -f infra/k8s/oss-k8s/namespace.yaml
	kubectl apply -f infra/k8s/oss-k8s/configmap.yaml
	kubectl apply -f infra/k8s/oss-k8s/redis-statefulset.yaml
	@echo "Waiting for Redis pods..."
	kubectl rollout status statefulset/redis -n $(OSS_NAMESPACE) --timeout=180s
	kubectl apply -f infra/k8s/oss-k8s/sentinel-deployment.yaml
	@echo "Waiting for Sentinel pods..."
	kubectl rollout status deployment/redis-sentinel -n $(OSS_NAMESPACE) --timeout=120s
	@echo "OSS Redis with Sentinel deployed. Run 'make k8s-oss-status' to check."

k8s-oss-down: ## Tear down OSS Redis from k8s
	kubectl delete -f infra/k8s/oss-k8s/sentinel-deployment.yaml --ignore-not-found
	kubectl delete -f infra/k8s/oss-k8s/redis-statefulset.yaml --ignore-not-found
	kubectl delete -f infra/k8s/oss-k8s/configmap.yaml --ignore-not-found
	kubectl delete -f infra/k8s/oss-k8s/namespace.yaml --ignore-not-found

k8s-oss-status: ## Show OSS Redis k8s status
	@echo "=== Redis Pods ==="
	@kubectl get pods -n $(OSS_NAMESPACE) -l app=redis 2>/dev/null || echo "No Redis pods found"
	@echo ""
	@echo "=== Sentinel Pods ==="
	@kubectl get pods -n $(OSS_NAMESPACE) -l app=redis-sentinel 2>/dev/null || echo "No Sentinel pods found"
	@echo ""
	@echo "=== Services ==="
	@kubectl get svc -n $(OSS_NAMESPACE) 2>/dev/null || echo "No services found"

# ── Convenience: all k8s stacks ───────────────────────────────────
k8s-up: k8s-re-up k8s-oss-up ## Start all k8s-path stacks
k8s-down: k8s-oss-down k8s-re-down ## Stop all k8s-path stacks
k8s-status: k8s-re-status k8s-oss-status ## Status of all k8s-path stacks

# ── Observability stack (Prometheus + Grafana) ────────────────────
obs-up: ## Start observability stack (Prometheus + Grafana + exporters)
	$(COMPOSE) -f observability/docker-compose.yml -p obs-stack up -d

obs-down: ## Stop observability stack and remove containers
	$(COMPOSE) -f observability/docker-compose.yml -p obs-stack down

obs-status: ## Show observability stack container status
	$(COMPOSE) -f observability/docker-compose.yml -p obs-stack ps

# ── k8s Scenario Targets ─────────────────────────────────────────────
k8s-scenario-baseline: ## Run k8s baseline scenario (requires k8s-oss-up). Usage: make k8s-scenario-baseline LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py
	@bash scenarios/k8s/01_baseline.sh

k8s-scenario-primary-kill: ## Run k8s primary kill scenario (requires k8s-oss-up). Usage: make k8s-scenario-primary-kill LOCUST_FILE=workloads/locustfiles/cache_read_heavy.py
	@bash scenarios/k8s/02_primary_kill.sh

# ── Validation & Cleanup ─────────────────────────────────────────────
validate: ## Validate all project artifacts (Compose, Python, Bash, YAML, Makefile)
	@bash infra/scripts/validate_all.sh

cleanup-all: ## Tear down all Docker stacks, k8s resources, and clean results
	@bash infra/scripts/cleanup_all.sh