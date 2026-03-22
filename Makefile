.PHONY: help setup lint clean
.PHONY: re-up re-down re-status
.PHONY: oss-sentinel-up oss-sentinel-down oss-sentinel-status
.PHONY: oss-cluster-up oss-cluster-down oss-cluster-status
.PHONY: vm-up vm-down vm-status

COMPOSE = docker compose

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies
	pip install -r requirements.txt

lint: ## Run linters
	@echo "TODO: configure linters"

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

