#!/usr/bin/env bash
# =============================================================================
# Stop the host-native 5G lab and free RAM/CPU.
#
#     ./host-down.sh            # stop containers, keep networks/volumes
#     ./host-down.sh --all      # also remove networks and the Jenkins volume
#
# The evidence in results/ and the PKI in secrets/tls/ are never touched.
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

echo "[host-down] Scenario B"
docker compose -f project2/scenario-b/docker-compose.security.yaml down "$@" 2>/dev/null || true

echo "[host-down] Scenario A application"
docker compose -f project2/scenario-a/docker-compose.p2.yaml down 2>/dev/null || true

echo "[host-down] 5G core / RAN"
docker compose -f scenario-b/upstream/sa-deploy.yaml down 2>/dev/null || true
docker compose -f scenario-b/upstream/nr-gnb.yaml down 2>/dev/null || true
docker compose -f scenario-b/upstream/nr-ue.yaml down 2>/dev/null || true

echo "[host-down] done"
docker ps --format '{{.Names}}' | grep -E 'nr_|upf|smf|amf|nrf|ausf|udm|udr|pcf|bsf|nssf|scp|webui|mongo|scenario-b|juice|selenium|sb-' || echo "no lab containers running"
