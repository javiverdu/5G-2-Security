#!/usr/bin/env bash
# =============================================================================
# Project 2 — Scenario A: create the lab PKI.
#
#   secrets/tls/ca.key      root CA private key (NEVER mounted into a container)
#   secrets/tls/ca.crt      root CA certificate (public, trusted by the clients)
#   secrets/tls/server.key  Nginx private key (mounted read-only)
#   secrets/tls/server.crt  Nginx certificate (SAN: 10.20.6.20, telecom-lab.local,
#                           localhost)
#
# `secrets/tls/` is git-ignored. Re-running the script is refused unless
# --force, so an accidental second CA does not silently invalidate the UE trust
# store.
#
# Usage:  ./project2/scenario-a/scripts/gen-pki.sh [--force]
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
ROOT=$(cd "$HERE/../.." && pwd)
OUT="$ROOT/secrets/tls"
DAYS_CA=3650
DAYS_SERVER=365

if [[ "${1:-}" != "--force" && -f "$OUT/ca.key" ]]; then
    echo "[pki] $OUT/ca.key already exists; use --force to replace the whole PKI"
    exit 1
fi

mkdir -p "$OUT"
umask 077

echo "[pki] root CA"
openssl req -x509 -new -nodes -newkey rsa:4096 \
    -keyout "$OUT/ca.key" -out "$OUT/ca.crt" \
    -days "$DAYS_CA" -config "$HERE/pki/ca.cnf" -extensions v3_ca \
    >/dev/null 2>&1

echo "[pki] server key and CSR"
openssl req -new -nodes -newkey rsa:2048 \
    -keyout "$OUT/server.key" -out "$OUT/server.csr" \
    -subj "/O=Telecom Lab/CN=telecom-lab.local" \
    >/dev/null 2>&1

echo "[pki] signing the server certificate"
openssl x509 -req -in "$OUT/server.csr" \
    -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
    -out "$OUT/server.crt" -days "$DAYS_SERVER" \
    -extfile "$HERE/pki/server.ext" -extensions server_cert \
    >/dev/null 2>&1

chmod 600 "$OUT/ca.key" "$OUT/server.key"
chmod 644 "$OUT/ca.crt" "$OUT/server.crt"

echo "[pki] done:"
openssl x509 -in "$OUT/server.crt" -noout \
    -subject -issuer -dates -ext subjectAltName | sed 's/^/       /'
