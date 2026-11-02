#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1A: recreate the RAN (gNB + UE) with the pinned image
# telecom-lab-ueransim:3.3.0-p2 (UERANSIM v3.3.0 + persistent N6 route).
#
# Usage:  ./project2/scenario-a/scripts/upgrade-ran.sh
# Requires the base deployment (scenario-b/scripts/deploy.sh) to be up.
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
UP="$HERE/../../scenario-b/upstream"
IMG="telecom-lab-ueransim:3.3.0-p2"

[[ -d "$UP" ]] || { echo "missing $UP — run scenario-b/scripts/fetch-upstream.sh first"; exit 1; }
docker image inspect "$IMG" >/dev/null 2>&1 || "$HERE/scripts/build.sh"

echo "[upgrade-ran] gNB with $IMG"
cd "$UP"
docker compose -f nr-gnb.yaml -f "$HERE/docker-compose.ueransim.yaml" up -d --no-build nr_gnb

printf '[upgrade-ran] waiting for NG Setup'
for _ in $(seq 1 30); do
    grep -qiE 'ng[ -]?setup' <<<"$(docker logs nr_gnb 2>&1)" && { echo " ...ok"; break; }
    printf '.'; sleep 2
done

echo "[upgrade-ran] UE with $IMG"
docker compose -f nr-ue.yaml -f "$HERE/docker-compose.ueransim.yaml" up -d --no-build nr_ue

printf '[upgrade-ran] waiting for the PDU session'
for _ in $(seq 1 60); do
    grep -q '10\.45\.' <<<"$(docker exec nr_ue ip -4 addr show uesimtun0 2>/dev/null)" && { echo " ...ok"; break; }
    printf '.'; sleep 2
done

printf '[upgrade-ran] waiting for the N6 route (installed by the image)'
for _ in $(seq 1 20); do
    grep -q uesimtun0 <<<"$(docker exec nr_ue ip route get 10.20.6.20 2>/dev/null)" && { echo " ...ok"; break; }
    printf '.'; sleep 1
done

echo "[upgrade-ran] route toward N6:"
docker exec nr_ue ip route get 10.20.6.20 2>/dev/null || true
echo "[upgrade-ran] next: ./project2/scenario-a/scripts/verify-phase1a.sh"
