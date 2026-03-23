#!/usr/bin/env bash
# generate-test-certs.sh — Generate a CA, server, and client certificate chain
# for local TLS testing with Redis.
#
# Usage:
#   bash infra/scripts/generate-test-certs.sh [output_dir]
#
# Default output: ./certs/

set -euo pipefail

CERT_DIR="${1:-./certs}"
DAYS=365
CA_SUBJ="/CN=locust-poc-lab-ca"
SERVER_SUBJ="/CN=localhost"
CLIENT_SUBJ="/CN=redis-client"

echo "==> Generating test certificates in ${CERT_DIR}"
mkdir -p "${CERT_DIR}"

# -------------------------------------------------------------------
# 1. Certificate Authority (CA)
# -------------------------------------------------------------------
echo "--- Generating CA key and certificate"
openssl genrsa -out "${CERT_DIR}/ca.key" 4096
openssl req -new -x509 -days "${DAYS}" -key "${CERT_DIR}/ca.key" \
    -out "${CERT_DIR}/ca.crt" -subj "${CA_SUBJ}"

# -------------------------------------------------------------------
# 2. Server certificate (used by Redis)
# -------------------------------------------------------------------
echo "--- Generating server key and certificate"
openssl genrsa -out "${CERT_DIR}/server.key" 2048

# Create SAN config for localhost + 127.0.0.1
cat > "${CERT_DIR}/server.cnf" <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_dn
prompt = no

[req_dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = redis
DNS.3 = *.redis.local
IP.1 = 127.0.0.1
EOF

openssl req -new -key "${CERT_DIR}/server.key" \
    -out "${CERT_DIR}/server.csr" -config "${CERT_DIR}/server.cnf"

openssl x509 -req -days "${DAYS}" \
    -in "${CERT_DIR}/server.csr" \
    -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" -CAcreateserial \
    -out "${CERT_DIR}/server.crt" \
    -extensions v3_req -extfile "${CERT_DIR}/server.cnf"

# -------------------------------------------------------------------
# 3. Client certificate (for mTLS)
# -------------------------------------------------------------------
echo "--- Generating client key and certificate"
openssl genrsa -out "${CERT_DIR}/client.key" 2048
openssl req -new -key "${CERT_DIR}/client.key" \
    -out "${CERT_DIR}/client.csr" -subj "${CLIENT_SUBJ}"

openssl x509 -req -days "${DAYS}" \
    -in "${CERT_DIR}/client.csr" \
    -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" -CAcreateserial \
    -out "${CERT_DIR}/client.crt"

# -------------------------------------------------------------------
# 4. Clean up CSRs and temp files
# -------------------------------------------------------------------
rm -f "${CERT_DIR}"/*.csr "${CERT_DIR}"/*.cnf "${CERT_DIR}"/*.srl

# Set restrictive permissions on private keys
chmod 600 "${CERT_DIR}/ca.key" "${CERT_DIR}/server.key" "${CERT_DIR}/client.key"
chmod 644 "${CERT_DIR}/ca.crt" "${CERT_DIR}/server.crt" "${CERT_DIR}/client.crt"

echo ""
echo "==> Certificates generated:"
ls -la "${CERT_DIR}"
echo ""
echo "Files:"
echo "  CA:     ${CERT_DIR}/ca.crt  /  ${CERT_DIR}/ca.key"
echo "  Server: ${CERT_DIR}/server.crt  /  ${CERT_DIR}/server.key"
echo "  Client: ${CERT_DIR}/client.crt  /  ${CERT_DIR}/client.key"
echo ""
echo "Redis config snippet:"
echo "  tls-cert-file ${CERT_DIR}/server.crt"
echo "  tls-key-file ${CERT_DIR}/server.key"
echo "  tls-ca-cert-file ${CERT_DIR}/ca.crt"
echo "  tls-auth-clients yes"
echo "  tls-port 6380"

