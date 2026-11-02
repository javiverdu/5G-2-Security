#!/usr/bin/env bash
# =============================================================================
# Project 2 — Phase 1A acceptance.
#
# Checks, in order:
#   1. the p2 image exists and reports UERANSIM v3.3.0
#   2. nr_gnb and nr_ue run it
#   3. the UE has a PDU session (uesimtun0 = 10.45.x)
#   4. traffic toward N6 resolves via uesimtun0
#   5. the route SURVIVES a container restart (the point of phase 1A)
#   6. (optional) N6 is reachable (requires enable-n6.sh)
#
# Usage:  ./project2/scenario-a/scripts/verify-phase1a.sh
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # project2/scenario-a
P2IMG="telecom-lab-ueransim:3.3.0-p2"

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0

step "1. p2 image"
if docker image inspect "$P2IMG" >/dev/null 2>&1; then
    ok "$P2IMG built"
    VER=$(docker run --rm --entrypoint /UERANSIM/build/nr-ue "$P2IMG" --version 2>/dev/null | tr -d '\r')
    if [[ "$VER" == *3.3.0* ]]; then
        ok "UERANSIM $VER"
    else
        fail "UERANSIM reports '${VER:-unknown}', expected 3.3.0"
    fi
else
    fail "$P2IMG missing (run ./project2/scenario-a/scripts/build.sh)"
fi

step "2. nr_gnb and nr_ue run the p2 image"
for c in nr_gnb nr_ue; do
    RUNNING_IMG=$(docker inspect -f '{{.Config.Image}}' "$c" 2>/dev/null || true)
    if [[ "$RUNNING_IMG" == "$P2IMG" ]]; then
        ok "$c uses $P2IMG"
    else
        fail "$c uses '${RUNNING_IMG:-none}' (run ./project2/scenario-a/scripts/upgrade-ran.sh)"
    fi
done

step "3. PDU session"
UADDR=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}')
if [[ "$UADDR" == 10.45.* ]]; then
    ok "uesimtun0 = $UADDR"
else
    fail "uesimtun0 has no 10.45.x address (got: ${UADDR:-none})"
fi

step "4. route toward N6 resolves via uesimtun0"
if grep -q uesimtun0 <<<"$(docker exec nr_ue ip route get 10.20.6.20 2>/dev/null)"; then
    ok "10.20.6.20 via uesimtun0"
else
    fail "10.20.6.20 does not resolve via uesimtun0"
fi

step "5. persistence: restart nr_ue and re-check"
docker restart nr_ue >/dev/null 2>&1 || fail "could not restart nr_ue"
printf '       waiting for re-registration'
for _ in $(seq 1 45); do
    REG=$(docker logs nr_ue 2>&1 | grep -iE 'registration.*(success|accept|complete)' | tail -1)
    UADDR=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}')
    [[ -n "$REG" && "$UADDR" == 10.45.* ]] && { echo " ...ok"; break; }
    printf '.'; sleep 2
done
if [[ "$UADDR" == 10.45.* ]] \
   && grep -q uesimtun0 <<<"$(docker exec nr_ue ip route get 10.20.6.20 2>/dev/null)"; then
    ok "route via uesimtun0 survived the restart (installed by the image)"
else
    fail "route not restored after restart"
fi

step "6. N6 reachability (optional — needs enable-n6.sh)"
if timeout 6 docker exec nr_ue ping -c 1 -W 2 10.20.6.20 >/dev/null 2>&1; then
    ok "UE -> 10.20.6.20 reachable"
else
    printf '\033[1;33m[SKIP]\033[0m N6 not reachable (run sudo ./scripts/enable-n6.sh)\n'
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "Phase 1A complete: the user-plane route is a property of the UE image."
else
    fail "$ERRORS check(s) failed."
    exit 1
fi
