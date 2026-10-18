#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 5: apply/clear controlled impairments with tc + NetEm
#
# Impairments are applied to the USER-PLANE endpoints only, so no control-plane
# traffic (N2/N4/SBI) is affected:
#   * uplink   : nr_ue:uesimtun0        (what the UE sends)
#   * downlink : sb-nginx/sb-iperf3 eth0 (what the apps send back)
#
# tc runs from the host inside each container netns (nsenter); the container
# images are not assumed to ship iproute2.
#
# Usage:  sudo ./scripts/impair.sh <baseline|delay|loss|rate|show>
# =============================================================================
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
set -a; . "$HERE/.env"; set +a

[[ $EUID -eq 0 ]] || { echo "run with sudo (nsenter)"; exit 1; }
COND="${1:?usage: impair.sh <baseline|delay|loss|rate|show>}"

TARGETS=("nr_ue uesimtun0" "sb-nginx eth0" "sb-iperf3 eth0")

ns_tc() { # <container> <iface> <add|del> [netem args...]
    local c="$1" i="$2" op="$3"; shift 3
    local pid
    pid=$(docker inspect -f '{{.State.Pid}}' "$c" 2>/dev/null) || return 0
    [[ -n "$pid" && "$pid" != 0 ]] || return 0
    nsenter -t "$pid" -n tc qdisc "$op" dev "$i" root "$@" 2>/dev/null
}

clear_all() { local t; for t in "${TARGETS[@]}"; do ns_tc "${t% *}" "${t#* }" del; done; }
apply()     { local args=("$@") t; for t in "${TARGETS[@]}"; do ns_tc "${t% *}" "${t#* }" add netem "${args[@]}"; done; }

case "$COND" in
    baseline) clear_all; echo "[impair] baseline — no impairment" ;;
    delay)    clear_all; apply delay 50ms 10ms; echo "[impair] delay 50ms +/-10ms" ;;
    loss)     clear_all; apply loss 1%;         echo "[impair] 1% packet loss" ;;
    rate)     clear_all; apply rate 20mbit;     echo "[impair] 20 Mbit/s limit" ;;
    show)     ;;
    *) echo "unknown condition: $COND" >&2; exit 2 ;;
esac

echo "[impair] resulting qdisc state:"
for t in "${TARGETS[@]}"; do
    c=${t% *}; i=${t#* }
    pid=$(docker inspect -f '{{.State.Pid}}' "$c" 2>/dev/null) || continue
    [[ -n "$pid" && "$pid" != 0 ]] || continue
    echo "--- $c:$i ---"
    nsenter -t "$pid" -n tc qdisc show dev "$i" 2>/dev/null
done
