#!/usr/bin/env bash
# =============================================================================
# Scenario A: end-to-end verification
# Checks every hop of the path ue -> access -> core -> host -> datanet
# Usage:  sudo ./scripts/deploy/verify.sh
# =============================================================================
set -uo pipefail

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; ERRORS=$((ERRORS+1)); }
step() { printf '\033[1;34m-----]\033[0m %s\n' "$*"; }
ERRORS=0

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

step "Namespaces exist"
for ns in ue access core; do
    ip netns list | awk '{print $1}' | grep -qx "$ns" && ok "namespace $ns" || fail "namespace $ns missing"
done

step "Link-layer reachability (hop by hop from ue)"
ip netns exec ue ping -c1 -W1 10.0.1.1  &>/dev/null && ok "ue -> access (10.0.1.1)"  || fail "ue -> access"
ip netns exec ue ping -c1 -W1 10.0.2.2  &>/dev/null && ok "ue -> core (10.0.2.2)"    || fail "ue -> core"
ip netns exec ue ping -c1 -W1 10.0.3.2  &>/dev/null && ok "ue -> host (10.0.3.2)"    || fail "ue -> host"

step "Data Network reachability"
ip netns exec ue ping -c1 -W1 10.0.4.10 &>/dev/null && ok "ue -> nginx-app (10.0.4.10)" || fail "ue -> nginx-app"
ip netns exec ue ping -c1 -W1 10.0.4.20 &>/dev/null && ok "ue -> iperf3-srv (10.0.4.20)" || fail "ue -> iperf3-srv"

step "Application test: HTTP via nginx"
HTTP_CODE=$(ip netns exec ue curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://10.0.4.10/ || echo "000")
[[ "$HTTP_CODE" == "200" ]] && ok "curl http://10.0.4.10 -> HTTP $HTTP_CODE" || fail "curl returned HTTP $HTTP_CODE"

step "Measurement endpoint: iperf3 TCP (2 s)"
if ip netns exec ue iperf3 -c 10.0.4.20 -t 2 &>/dev/null; then
    ok "iperf3 TCP test completed"
else
    fail "iperf3 TCP test"
fi

echo
if [[ $ERRORS -eq 0 ]]; then
    ok "All checks passed — end-to-end path is operational."
else
    fail "$ERRORS check(s) failed. Review routing/forwarding and container status."
    exit 1
fi
