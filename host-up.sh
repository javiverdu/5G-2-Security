#!/usr/bin/env bash
# =============================================================================
# Host-native restart for the 5G lab (Scenario A + optional Scenario B).
#
# Replaces the old VirtualBox VM workflow. Run after a host reboot:
#     ./host-up.sh              # Scenario A only
#     ./host-up.sh --with-b     # Scenario A + Scenario B (no rebuild)
#
# Requires: docker enabled, user in the docker group (or run via newgrp docker),
# and sudo for the N6 step (nsenter).
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

WITH_B=0
[[ "${1:-}" == "--with-b" ]] && WITH_B=1

echo "[host-up] 1/4 core 5G + gNB + UE"
./scenario-b/scripts/deploy.sh

echo "[host-up] 2/4 N6 (needs sudo: nsenter)"
sudo ./scenario-b/scripts/enable-n6.sh

echo "[host-up] 3/4 Project 2 RAN (UERANSIM 3.3.0)"
./project2/scenario-a/scripts/upgrade-ran.sh

echo "[host-up] 4/4 Django + TLS gateway"
./project2/scenario-a/scripts/up.sh

if [[ "$WITH_B" == "1" ]]; then
    echo "[host-up] Scenario B (no rebuild)"
    docker compose -f project2/scenario-b/docker-compose.security.yaml up -d --no-build
    ./project2/scenario-b/scripts/jenkins-bootstrap.sh
fi

echo
echo "[host-up] verification:"
./project2/scenario-a/scripts/verify-phase1.sh
