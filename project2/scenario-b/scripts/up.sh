#!/usr/bin/env bash
# =============================================================================
# Project 2 — Scenario B: bring up the security-testing environment.
#
#   security-net 10.20.10.0/24
#   juice-shop 10.20.10.20:3000   selenium 10.20.10.30:4444
#   jenkins    10.20.10.40:8080
#
# Requires the Scenario A deployment (1E) to be up; Preflight verifies it.
#
# Usage:  ./project2/scenario-b/scripts/up.sh
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-b
COMPOSE="$HERE/docker-compose.security.yaml"

[[ -f "$HERE/env" ]] || { echo "[up] missing $HERE/env (copy env.example)"; exit 1; }

echo "[up] building the Scenario B images"
docker compose -f "$COMPOSE" build

echo "[up] building the capture job image (no compose service)"
docker build -t telecom-lab-capture:1.0 "$HERE/capture"

echo "[up] building the correlation job image (no compose service)"
docker build -t telecom-lab-correlation:1.0 "$HERE/correlation"

echo "[up] starting juice-shop, selenium and jenkins"
docker compose -f "$COMPOSE" up -d

echo "[up] waiting for Jenkins health"
for _ in $(seq 1 60); do
    state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
        scenario-b-jenkins 2>/dev/null || true)
    [[ "$state" == "healthy" ]] && break
    sleep 3
done
[[ "${state:-}" == "healthy" ]] || echo "[up] WARN: Jenkins not healthy yet ($state)"

echo "[up] creating the pipeline job"
"$HERE/scripts/jenkins-bootstrap.sh"

echo "[up] status:"
docker compose -f "$COMPOSE" ps
