#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1A: build telecom-lab-ueransim:3.3.0-p2
# (UERANSIM v3.3.0 from source + a persistent user-plane route)
#
# Self-contained: it does not depend on docker_ueransim from Project 1. Only a
# working Docker engine and network access to github.com are required.
#
# Usage:  ./project2/scenario-a/scripts/build.sh
# =============================================================================
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
IMG="telecom-lab-ueransim:3.3.0-p2"

echo "[build] $IMG (UERANSIM v3.3.0)"
docker build -t "$IMG" "$HERE/ueransim"
echo "[build] $IMG ready"
