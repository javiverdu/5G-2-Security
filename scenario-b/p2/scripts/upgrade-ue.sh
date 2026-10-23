#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1A: recreate nr_ue with the p2 image (persistent route).
#
# Usage:  ./p2/scripts/upgrade-ue.sh     (after deploy.sh + enable-n6.sh)
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # scenario-b/p2
UP="$HERE/../upstream"

[[ -d "$UP" ]] || { echo "run scenario-b/scripts/fetch-upstream.sh first"; exit 1; }
docker image inspect telecom-lab-ueransim:3.3.0-p2 >/dev/null 2>&1 \
    || "$HERE/scripts/build.sh"

echo "[upgrade-ue] recreating nr_ue with telecom-lab-ueransim:3.3.0-p2"
cd "$UP"
docker compose -f nr-ue.yaml -f "$HERE/docker-compose.ueransim.yaml" up -d --no-build

echo "[upgrade-ue] waiting for the PDU session (uesimtun0 gets a 10.45.x address)"
for _ in $(seq 1 60); do
    grep -q '10\.45\.' <<<"$(docker exec nr_ue ip -4 addr show uesimtun0 2>/dev/null)" && break
    sleep 2
done

echo "[upgrade-ue] route toward N6 (installed by the image itself):"
docker exec nr_ue ip route get 10.20.6.20 2>/dev/null || true
echo "[upgrade-ue] next: ./p2/scripts/verify-phase1a.sh"
