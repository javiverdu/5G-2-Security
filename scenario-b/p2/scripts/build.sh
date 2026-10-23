#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1A: build telecom-lab-ueransim:3.3.0-p2
# (UE image with a persistent user-plane route, on top of docker_ueransim)
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # scenario-b/p2

docker image inspect docker_ueransim:latest >/dev/null 2>&1 \
    || { echo "docker_ueransim:latest not found — run scenario-b/scripts/fetch-upstream.sh first"; exit 1; }

docker build -t telecom-lab-ueransim:3.3.0-p2 "$HERE/ueransim"
echo "[build] telecom-lab-ueransim:3.3.0-p2 ready"
