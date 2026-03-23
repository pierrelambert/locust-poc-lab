# Offline Field Kit

How to run the Locust POC Lab in an air-gapped environment with no internet.

## Overview

Three things need to be pre-downloaded on a connected machine:

1. **Docker images** — all container images used by the lab
2. **Python packages** — pinned wheels for the virtualenv
3. **Kubernetes manifests** — already vendored in the repo

## 1. Pre-download Docker Images

On a connected machine, pull and save every image the lab uses:

```bash
# Redis Enterprise
docker pull redislabs/redis:7.8.2-6
docker pull redislabs/operator:7.8.2-6
docker pull redislabs/k8s-controller:7.8.2-6

# OSS Redis
docker pull redis:7.2-alpine

# k3s (for k3d)
docker pull rancher/k3s:v1.29.4-k3s1

# Observability
docker pull prom/prometheus:latest
docker pull grafana/grafana:latest
docker pull oliver006/redis_exporter:latest

# Save to a tarball
docker save \
  redislabs/redis:7.8.2-6 \
  redislabs/operator:7.8.2-6 \
  redislabs/k8s-controller:7.8.2-6 \
  redis:7.2-alpine \
  rancher/k3s:v1.29.4-k3s1 \
  prom/prometheus:latest \
  grafana/grafana:latest \
  oliver006/redis_exporter:latest \
  -o locust-poc-lab-images.tar
```

## 2. Pre-download Python Packages

```bash
# Download wheels for all pinned dependencies
pip download -r requirements.txt -d ./offline-packages/

# Or use the full lock file for exact reproducibility
pip download -r requirements-lock.txt -d ./offline-packages/
```

## 3. Carry Everything on USB

Copy these to a USB drive or transfer medium:

```
usb-drive/
├── locust-poc-lab/              # This git repo (cloned)
├── locust-poc-lab-images.tar    # Docker images (~3 GB)
├── offline-packages/            # Python wheels (~50 MB)
└── tools/                       # Optional: k3d, helm, kubectl binaries
    ├── k3d
    ├── helm
    └── kubectl
```

## 4. Set Up Without Internet

### a) Load Docker images

```bash
docker load -i /media/usb/locust-poc-lab-images.tar
```

### b) Import images into k3d

```bash
# After creating the k3d cluster
k3d image import /media/usb/locust-poc-lab-images.tar \
  -c locust-poc-lab
```

### c) Install Python packages offline

```bash
cd /media/usb/locust-poc-lab
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links=/media/usb/offline-packages/ \
  -r requirements.txt
```

### d) Install CLI tools (if not already present)

```bash
# Copy pre-downloaded binaries
sudo cp /media/usb/tools/k3d /usr/local/bin/
sudo cp /media/usb/tools/helm /usr/local/bin/
sudo cp /media/usb/tools/kubectl /usr/local/bin/
sudo chmod +x /usr/local/bin/{k3d,helm,kubectl}
```

### e) Run the lab

```bash
# The operator bundle is already vendored — no download needed
make k3d-up
make k8s-re-up    # Uses local operator-bundle.yaml
make k8s-oss-up
make obs-up
```

## Tips

- **Test offline setup on a connected machine first** by disabling networking
  after the pre-download step.
- **Pin Docker image tags** — never use `:latest` in production field kits.
  Update the image list above when upgrading versions.
- The `requirements-lock.txt` file ensures byte-identical installs across
  machines. Use it instead of `requirements.txt` for maximum reproducibility.

