#!/usr/bin/env bash
# =============================================================================
# Scenario B — tear everything down (UE, gNB, core) and optionally the volumes.
#
# Usage:  ./scripts/cleanup.sh [--volumes]
# =============================================================================
set -uo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
UP="$HERE/upstream"
[[ -d "$UP" ]] || { echo "nothing to clean (no upstream clone)"; exit 0; }
cd "$UP"

echo "[cleanup] UE + gNB"
docker compose -f nr-ue.yaml   down 2>/dev/null || true
docker compose -f nr-gnb.yaml  down 2>/dev/null || true

echo "[cleanup] core network"
if [[ "${1:-}" == "--volumes" ]]; then
    docker compose -f sa-deploy.yaml down -v 2>/dev/null || true
    docker network rm docker_open5gs_default 2>/dev/null || true
else
    docker compose -f sa-deploy.yaml down 2>/dev/null || true
fi

echo "[cleanup] done."
