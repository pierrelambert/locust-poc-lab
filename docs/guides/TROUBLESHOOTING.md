# Troubleshooting Guide

Common failure modes and fixes for the Locust POC Lab.

---

## 1. Docker Resource Issues

**Symptoms:** Containers exit with code 137 (OOMKilled), `docker compose up` hangs, or nodes fail to start.

**Causes & Fixes:**

| Cause | Fix |
|---|---|
| Docker Desktop memory too low | Increase to ≥16 GB in Docker Desktop → Settings → Resources |
| Too many stacks running at once | Run `make cleanup-all` then start only the stack you need |
| Dangling volumes consuming disk | `docker volume prune -f` |
| Old images filling disk | `docker image prune -a -f` |

**Verify resources:**

```bash
docker info | grep -E 'Memory|CPUs'
docker system df
```

---

## 2. Port Conflicts

**Symptoms:** `Bind for 0.0.0.0:<port> failed: port is already allocated`

**Common ports used by the lab:**

| Port | Service |
|---|---|
| 6380 | Redis primary (OSS Sentinel) |
| 7001–7006 | Redis Cluster nodes |
| 9443 | Redis Enterprise Admin UI |
| 12000 | Redis Enterprise database |
| 9090 | Prometheus |
| 3000 | Grafana |
| 8089 | Locust web UI |
| 9121 | Redis Exporter |
| 9646 | Locust Exporter |

**Find what's using a port:**

```bash
lsof -i :<port>
# or on Linux:
ss -tlnp | grep <port>
```

**Fix:** Stop the conflicting process, or change the port mapping in the relevant `docker-compose.yml`.

---

## 3. Redis Enterprise License

**Symptoms:** RE nodes start but cluster creation fails, or the Admin UI shows a license warning.

**Causes & Fixes:**

- **Trial expired:** Redis Enterprise containers include a built-in trial license. If it expires, pull a fresh image: `docker pull redislabs/redis:latest`
- **Cluster not bootstrapped:** After `make re-up`, the 3 nodes are running but not yet joined into a cluster. Use the REST API or Admin UI (https://localhost:9443) to create and join the cluster.
- **Node join timeout:** Ensure all 3 RE containers are healthy before attempting cluster creation:

```bash
make re-status
# All 3 containers should show "running"
```

---

## 4. k3d Cluster Problems

**Symptoms:** `k3d cluster create` fails, `kubectl` commands return connection errors, or pods stay in Pending.

**Causes & Fixes:**

| Cause | Fix |
|---|---|
| k3d not installed | Install: `brew install k3d` (macOS) or see https://k3d.io |
| kubectl not installed | Install: `brew install kubectl` |
| Docker not running | Start Docker Desktop |
| Port 6550 in use | Set `K3D_API_PORT` env var to a different port |
| Pods stuck in Pending | Check node resources: `kubectl describe node` — increase Docker memory |
| ImagePullBackOff | Check internet connectivity; verify image names in manifests |

**Reset the cluster:**

```bash
make k3d-down
make k3d-up
```

---

## 5. Locust Connection Errors

**Symptoms:** Locust workers report `ConnectionError`, `TimeoutError`, or `redis.exceptions.ConnectionError`.

**Causes & Fixes:**

- **Redis not running:** Verify the target Redis stack is up:
  ```bash
  make re-status        # or oss-sentinel-status, oss-cluster-status
  ```

- **Wrong host/port in workload profile:** Check the profile YAML matches the running topology:
  ```bash
  cat workloads/profiles/<profile>.yaml
  ```

- **Network mismatch:** If Locust runs on the host but Redis is in Docker, use `localhost` and the mapped port. If both are in Docker, use the container hostname and internal port.

- **Redis Cluster not initialized:** For OSS Cluster, the `redis-cli --cluster create` command must be run after containers start:
  ```bash
  docker exec redis-node1 redis-cli --cluster create \
    redis-node1:6379 redis-node2:6379 redis-node3:6379 \
    redis-node4:6379 redis-node5:6379 redis-node6:6379 \
    --cluster-replicas 1 --cluster-yes
  ```

---

## 6. Grafana Not Showing Data

**Symptoms:** Dashboards load but panels show "No data" or "N/A".

**Causes & Fixes:**

1. **Prometheus not scraping:** Open http://localhost:9090/targets and check all targets are UP.

2. **Exporters not running:**
   ```bash
   make obs-status
   # Verify redis-exporter and locust-exporter containers are running
   ```

3. **Wrong Prometheus data source URL:** In Grafana (http://localhost:3000), go to Configuration → Data Sources → Prometheus. The URL should be `http://prometheus:9090` (not `localhost`).

4. **Time range too narrow:** Expand the Grafana time picker to "Last 15 minutes" or wider.

5. **Redis exporter pointing at wrong Redis:**
   Check the `REDIS_ADDR` environment variable in `observability/docker-compose.yml`. It must match the running Redis instance.

6. **Locust not running:** The Locust exporter only has data when a Locust test is actively running. Start a workload first.

---

## General Tips

- **Run validation first:** `make validate` checks all project files for syntax errors.
- **Full reset:** `make cleanup-all` tears down everything. Then start fresh.
- **Check logs:** `docker logs <container-name>` for any container.
- **k8s logs:** `kubectl logs <pod-name> -n <namespace>` for k8s pods.
- **Disk space:** The lab can consume significant disk. Run `docker system df` periodically.

