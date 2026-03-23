# TLS Setup Guide

This guide covers TLS configuration for the locust-poc-lab across Docker,
Kubernetes, and Redis Enterprise environments.

## Quick Start — Generate Test Certificates

```bash
bash infra/scripts/generate-test-certs.sh ./certs
```

This creates a CA, server, and client certificate in `./certs/`.

## Profile Configuration

Add TLS fields to the `connection` section of any workload profile:

```yaml
connection:
  host: "redis.example.com"
  port: 6380
  ssl: true
  ssl_certfile: "./certs/client.crt"    # client cert (mTLS)
  ssl_keyfile: "./certs/client.key"     # client key  (mTLS)
  ssl_ca_certs: "./certs/ca.crt"        # CA bundle
  sni_hostname: "db1.redis.example.com" # optional SNI
```

When `ssl_certfile`, `ssl_keyfile`, or `ssl_ca_certs` are set, the
framework uses `TLSCertificateManager` for full cert-path SSL.
Otherwise plain `ssl: true` uses system defaults.

## Environment Variables

Instead of profile fields you can export:

```bash
export REDIS_TLS_CERT=./certs/client.crt
export REDIS_TLS_KEY=./certs/client.key
export REDIS_TLS_CA=./certs/ca.crt
export REDIS_TLS_SNI=db1.redis.example.com
```

Then in Python:

```python
from workloads.lib.tls_manager import TLSCertificateManager
mgr = TLSCertificateManager.load_from_environment()
ctx = mgr.create_ssl_context()
```

## Docker TLS Setup

1. Generate certificates:
   ```bash
   bash infra/scripts/generate-test-certs.sh ./certs
   ```
2. Mount certs and configure Redis in `docker-compose.yml`:
   ```yaml
   services:
     redis:
       image: redis:7
       command: >
         redis-server
         --tls-port 6380 --port 0
         --tls-cert-file /tls/server.crt
         --tls-key-file /tls/server.key
         --tls-ca-cert-file /tls/ca.crt
         --tls-auth-clients yes
       volumes:
         - ./certs:/tls:ro
       ports:
         - "6380:6380"
   ```

## Kubernetes TLS Secrets

### Create a TLS secret

```bash
kubectl create secret generic redis-tls \
  --from-file=tls.crt=./certs/server.crt \
  --from-file=tls.key=./certs/server.key \
  --from-file=ca.crt=./certs/ca.crt
```

### Load certs from a secret at runtime

```python
from workloads.lib.tls_manager import TLSCertificateManager
mgr = TLSCertificateManager.load_from_kubernetes_secret(
    "redis-tls", namespace="redis"
)
ctx = mgr.create_ssl_context()
```

## Redis Enterprise TLS

Redis Enterprise clusters expose a proxy certificate. Download the
proxy CA from the admin UI or REST API and point `ssl_ca_certs` at it:

```yaml
connection:
  connection_mode: enterprise
  host: "cluster.re.example.com"
  port: 12000
  ssl: true
  ssl_ca_certs: "./re-proxy-ca.pem"
  sni_hostname: "db1.cluster.re.example.com"
```

## Mutual TLS (mTLS)

mTLS requires **both** a client certificate/key **and** the CA that
signed the server certificate:

```yaml
connection:
  ssl: true
  ssl_certfile: "./certs/client.crt"
  ssl_keyfile: "./certs/client.key"
  ssl_ca_certs: "./certs/ca.crt"
```

Redis must also be configured with `tls-auth-clients yes`.

## SNI (Server Name Indication)

SNI is required for multi-tenant Redis Enterprise setups where a single
IP hosts multiple databases distinguished by hostname:

```yaml
connection:
  ssl: true
  sni_hostname: "db1.cluster.example.com"
```

The `TLSCertificateManager` sets `ssl_check_hostname = True` when
`sni_hostname` is configured.

## Certificate Validation

If the optional `cryptography` package is installed you can inspect
certificates programmatically:

```python
from workloads.lib.tls_manager import TLSCertificateManager
mgr = TLSCertificateManager(ca_path="./certs/ca.crt")
valid, msg = mgr.validate_certificate("./certs/server.crt")
print(msg)
info = mgr.get_certificate_info("./certs/server.crt")
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ssl.SSLCertVerificationError` | CA not trusted | Set `ssl_ca_certs` to correct CA file |
| `ConnectionRefusedError` on port 6380 | Redis not listening on TLS port | Verify `--tls-port` in Redis config |
| `certificate verify failed` | Hostname mismatch | Set `sni_hostname` or check server SAN |
| `tlsv1 alert unknown ca` | Client cert not signed by expected CA | Re-issue client cert with correct CA |
| `SSL: CERTIFICATE_REQUIRED` | mTLS required but no client cert | Add `ssl_certfile` and `ssl_keyfile` |
| Expired certificate | Cert past `not_valid_after` | Regenerate with `generate-test-certs.sh` |

