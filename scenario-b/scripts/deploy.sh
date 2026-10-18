#!/usr/bin/env bash
# =============================================================================
# Scenario B — bring up the 5G SA core, the gNB and the UE, and provision the
# subscriber.
#
# Order matters: the subscriber must exist before the UE tries to register.
#
# Usage:  ./scripts/deploy.sh
# =============================================================================
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
UP="$HERE/upstream"

[[ -d "$UP" ]] || { echo "run scripts/fetch-upstream.sh first"; exit 1; }

# Load our parameters (same values that were copied into upstream/.env).
set -a; . "$HERE/.env"; set +a

cd "$UP"

echo "[deploy] 1/4 core network (5GC)"
docker compose -f sa-deploy.yaml up -d --no-build

echo "[deploy] 2/4 waiting for webui/mongo and provisioning the subscriber"
for _ in $(seq 1 60); do
    docker exec webui true 2>/dev/null && break
    sleep 2
done
# add_ue_with_apn <imsi> <k> <opc> <apn>
docker exec webui misc/db/open5gs-dbctl \
    add_ue_with_apn "$UE1_IMSI" "$UE1_KI" "$UE1_OPC" internet \
    && echo "[deploy] subscriber $UE1_IMSI provisioned" \
    || echo "[deploy] WARN: provisioning returned non-zero (maybe already exists)"

echo "[deploy] 3/4 gNB"
docker compose -f nr-gnb.yaml up -d --no-build

echo "[deploy] waiting for the gNB NG Setup with the AMF (N2)"
for _ in $(seq 1 30); do
    # NB: do NOT use `docker logs | grep -q` here: grep -q exits on first match,
    # docker logs gets SIGPIPE and, with `set -o pipefail`, the pipeline fails
    # even on a match. Capture first, then grep the captured text.
    grep -qiE 'ng[ -]?setup' <<<"$(docker logs nr_gnb 2>&1)" && break
    sleep 2
done

echo "[deploy] 4/4 UE"
docker compose -f nr-ue.yaml up -d --no-build

echo "[deploy] waiting for the UE PDU session (uesimtun0 gets a 10.45.x address)"
for _ in $(seq 1 60); do
    grep -q '10\.45\.' <<<"$(docker exec nr_ue ip -4 addr show uesimtun0 2>/dev/null)" && break
    sleep 2
done

# UERANSIM creates the TUN with the session IP but does not install a route for
# the session. Without this, user traffic to the UE pool (and to N6) leaves via
# the management interface and is lost. Send it through the tunnel; the
# management subnet keeps its own connected route.
docker exec nr_ue ip route replace default dev uesimtun0 2>/dev/null \
    || docker exec nr_ue ip route add default dev uesimtun0 2>/dev/null || true
docker exec nr_ue ip route add 10.45.0.0/16 dev uesimtun0 2>/dev/null || true

echo
echo "[deploy] container status:"
docker compose -f sa-deploy.yaml ps
docker compose -f nr-gnb.yaml ps
docker compose -f nr-ue.yaml ps

echo
echo "[deploy] next: ./scripts/verify.sh"
