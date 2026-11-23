#!/usr/bin/env bash
# =============================================================================
# Host-native start for the 5G lab (Scenario A + optional Scenario B).
#
# Day-to-day entry point. It starts the stack in the order the architecture
# requires and finishes with the 1E acceptance gate:
#
#     1. scenario-b/scripts/deploy.sh                core, gNB, UE, subscriber
#     2. scenario-b/scripts/enable-n6.sh             UPF on dn-net, no NAT (sudo)
#     3. project2/scenario-a/scripts/upgrade-ran.sh  UERANSIM 3.3.0 + narrow route
#     4. project2/scenario-a/scripts/up.sh           Django + Nginx TLS gateway
#     5. project2/scenario-a/scripts/verify-phase1.sh   1E gate
#
#     ./host-up.sh              # Scenario A only
#     ./host-up.sh --with-b     # Scenario A + Scenario B (no rebuild)
#
# It does NOT build images, generate the PKI or create the git-ignored `env`
# files: that is first-clone work (see "Run — first clone" in README.md). The
# prerequisite checks below fail fast with the exact command to run, instead of
# letting a later step die with a misleading error.
#
# Requires: docker enabled, user in the docker group (or run via newgrp docker),
# and sudo for the N6 step (nsenter).
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

WITH_B=0
[[ "${1:-}" == "--with-b" ]] && WITH_B=1

# --- prerequisites: first-clone artefacts ------------------------------------
need() {  # need <path> <hint>
    [[ -e "$1" ]] || {
        echo "[host-up] missing $1" >&2
        echo "[host-up] first clone? run: $2" >&2
        exit 1
    }
}

need scenario-b/.env \
     "cp -n scenario-b/env.example scenario-b/.env"
need scenario-b/upstream \
     "./scenario-b/scripts/fetch-upstream.sh   # after creating scenario-b/.env"
need project2/scenario-a/env \
     "cp -n project2/scenario-a/env.example project2/scenario-a/env"
need secrets/tls/server.crt \
     "./project2/scenario-a/scripts/gen-pki.sh"
docker image inspect telecom-lab-ueransim:3.3.0-p2 >/dev/null 2>&1 || {
    echo "[host-up] missing image telecom-lab-ueransim:3.3.0-p2" >&2
    echo "[host-up] first clone? run: ./project2/scenario-a/scripts/build.sh" >&2
    exit 1
}
if [[ "$WITH_B" == "1" ]]; then
    need project2/scenario-b/env \
         "cp -n project2/scenario-b/env.example project2/scenario-b/env"
fi

echo "[host-up] 1/4 core 5G + gNB + UE"
./scenario-b/scripts/deploy.sh

echo "[host-up] 2/4 N6 (needs sudo: nsenter)"
# 10.20.6.20 is claimed by two containers: the inherited N6 test endpoint
# sb-nginx and the Project 2 gateway scenario-b-nginx. Free the address before
# N6 so enable-n6.sh can recreate sb-nginx; up.sh removes it again in step 4.
# Both may legitimately be absent, so a failure here is tolerated.
docker rm -f sb-nginx scenario-b-nginx 2>/dev/null || true
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
