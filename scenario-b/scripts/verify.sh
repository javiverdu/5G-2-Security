#!/usr/bin/env bash
# =============================================================================
# Scenario B — verify the 5G end-to-end path, milestone by milestone.
#
# Checks, in order of dependency:
#   1. containers up
#   2. gNB did the NG Setup with the AMF            (N2 / control plane)
#   3. UE registered and established a PDU session  (N2 + N4)
#   4. uesimtun0 has an address from the UE pool    (user plane exists)
#   5. UE can reach the tunnel gateway 10.45.0.1
#   6. (optional) UE can reach the application on N6 (milestone 6)
#   7. (optional) iperf3 throughput endpoint on N6
#
# Usage:  ./scripts/verify.sh
# =============================================================================
set -uo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
UP="$HERE/upstream"
set -a; . "$HERE/.env" 2>/dev/null || true; set +a

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m----]\033[0m %s\n' "$*"; }
ERRORS=0

# HTTP GET from the UE container. The UERANSIM image has no curl/wget, but it
# has bash, so use bash's /dev/tcp to speak HTTP/1.0.
ue_http_code() { # <ip>
    timeout 10 docker exec nr_ue timeout 6 bash -c "
        exec 3<>/dev/tcp/$1/80 2>/dev/null || exit 1
        printf 'GET / HTTP/1.0\r\nHost: $1\r\n\r\n' >&3
        head -n1 <&3 | tr -d '\r' | awk '{print \$2}'
    " 2>/dev/null
}

step "1. Containers up"
for c in mongo nrf amf smf upf ausf udm udr pcf nr_gnb nr_ue; do
    if [[ "$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null)" == "running" ]]; then
        ok "$c running"
    else
        fail "$c not running"
    fi
done

step "2. N2 — gNB NG Setup with the AMF"
NG=$(docker logs nr_gnb 2>&1 | grep -iE 'ng[ -]?setup' | tail -1)
if [[ -n "$NG" ]]; then
    ok "gNB established N2 with the AMF: $(echo "$NG" | sed 's/^ *//' | cut -c1-70)"
else
    fail "no NG Setup in nr_gnb logs (check N2: SCTP 38412 to AMF)"
fi

step "3. Registration + PDU session (UE logs)"
REG=$(docker logs nr_ue 2>&1 | grep -iE 'registration.*(success|accept|complete)|RM-REGISTERED|registered' | tail -1)
if [[ -n "$REG" ]]; then
    ok "UE registration seen: $(echo "$REG" | sed 's/^ *//' | cut -c1-80)"
else
    fail "no registration in nr_ue logs (check subscriber K/OPc and PLMN)"
fi
PDU=$(docker logs nr_ue 2>&1 | grep -iE 'pdu session' | tail -1)
if [[ -n "$PDU" ]]; then
    ok "PDU session established: $(echo "$PDU" | sed 's/^ *//' | cut -c1-70)"
else
    fail "no PDU session in nr_ue logs"
fi

step "4. User plane — uesimtun0 address"
UADDR=$(docker exec nr_ue ip -4 -brief addr show uesimtun0 2>/dev/null | awk '{print $3}')
if [[ "$UADDR" == 10.45.* ]]; then
    ok "uesimtun0 = $UADDR"
else
    fail "uesimtun0 has no 10.45.x address (got: ${UADDR:-none})"
fi

step "5. User-plane route + tunnel gateway"
if grep -q uesimtun0 <<<"$(docker exec nr_ue ip route get 10.45.0.1 2>/dev/null)"; then
    ok "UE routes 10.45.0.1 via uesimtun0"
else
    fail "UE has no route to the UE pool via uesimtun0 (re-run deploy.sh or add it manually)"
fi
if docker exec nr_ue ping -c 3 -W 2 10.45.0.1 >/dev/null 2>&1; then
    ok "UE -> 10.45.0.1 (through the 5G tunnel)"
else
    fail "UE cannot reach 10.45.0.1"
fi

step "6. Application over N6 (nginx, no NAT)"
CODE=$(ue_http_code "$NGINX_IP")
if [[ "$CODE" == "200" ]]; then
    ok "UE -> nginx ${NGINX_IP} : HTTP 200 (end-to-end over N6)"
    SRC=$(docker logs --tail 20 sb-nginx 2>&1 | grep -oE '10\.45\.[0-9]+\.[0-9]+' | tail -1 || true)
    if [[ -n "${SRC:-}" ]]; then
        ok "nginx sees the UE as $SRC (no NAT)"
    else
        printf '\033[1;33m[WARN]\033[0m nginx did not log a 10.45.x client (NAT may still be on)\n'
    fi
else
    printf '\033[1;33m[SKIP]\033[0m N6 app not reachable (HTTP code: %s). Run scripts/enable-n6.sh\n' "${CODE:-none}"
fi

step "7. Throughput endpoint (iperf3 on N6)"
P7_STATUS=$(docker inspect -f '{{.State.Status}}' sb-iperf3 2>/dev/null || true)
if [[ "$P7_STATUS" != "running" ]]; then
    printf '\033[1;33m[SKIP]\033[0m iperf3 endpoint not running (run scripts/enable-n6.sh)\n'
elif ! timeout 6 docker exec nr_ue ping -c 1 -W 2 "$IPERF_IP" >/dev/null 2>&1; then
    printf '\033[1;33m[SKIP]\033[0m iperf3 endpoint not reachable (run scripts/enable-n6.sh)\n'
else
    OUT=$(timeout 15 docker run --rm --network container:nr_ue \
        networkstatic/iperf3:latest -c "$IPERF_IP" -t 3 --connect-timeout 3000 2>&1 || true)
    if grep -q 'receiver' <<<"$OUT"; then
        ok "iperf3 UE -> $IPERF_IP : $(grep receiver <<<"$OUT" | tail -1 | sed 's/^ *//')"
    else
        printf '\033[1;33m[SKIP]\033[0m iperf3 test did not complete\n'
    fi
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "5G control + user path is operational (UE registered, session up)."
else
    fail "$ERRORS check(s) failed — fix the core before touching the application."
    exit 1
fi
