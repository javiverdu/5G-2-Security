#!/usr/bin/env bash
# =============================================================================
# Project 2 — Scenario A: bring up the application layer and the TLS gateway.
#
#   django (app-net .20)  +  scenario-b-nginx (dn-net .20, app-net .10)
#
# Requires the Project 1 base deployment and N6 (dn-net) already up, and the
# lab PKI already generated (`scripts/gen-pki.sh`).
#
# The Project 1 N6 test container (sb-nginx) also uses 10.20.6.20; it is
# removed here so the two never run at the same time. This is irreversible for
# that container, but it is a test endpoint and `enable-n6.sh` can recreate it.
#
# Usage:  ./project2/scenario-a/scripts/up.sh
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
ROOT=$(cd "$HERE/../.." && pwd)
COMPOSE="$HERE/docker-compose.p2.yaml"

[[ -f "$HERE/env" ]] || { echo "[up] missing $HERE/env (copy env.example)"; exit 1; }
[[ -f "$ROOT/secrets/tls/server.crt" ]] || { echo "[up] missing PKI: run ./project2/scenario-a/scripts/gen-pki.sh"; exit 1; }
docker network inspect dn-net >/dev/null 2>&1 \
    || { echo "[up] dn-net missing: run scenario-b/scripts/enable-n6.sh first"; exit 1; }

if docker inspect sb-nginx >/dev/null 2>&1; then
    echo "[up] removing the Project 1 N6 test container sb-nginx (10.20.6.20)"
    docker rm -f sb-nginx >/dev/null
fi

echo "[up] building and starting django + scenario-b-nginx"
docker compose -f "$COMPOSE" up -d --build

echo "[up] status:"
docker compose -f "$COMPOSE" ps
echo "[up] next: ./project2/scenario-a/scripts/verify-phase1c.sh"
