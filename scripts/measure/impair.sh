#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 3: apply/clear controlled impairments with tc + NetEm
#
# Impairments are applied to BOTH egress interfaces of the access router
# (eth0 = downlink toward UE, eth1 = uplink toward core), so that both
# directions of the UE <-> Data Network path are affected.
#
# Usage:  sudo ./scripts/measure/impair.sh <baseline|delay|loss|rate|show>
#   baseline : remove all impairments
#   delay    : netem delay 50 ms +/- 10 ms
#   loss     : netem loss 1%
#   rate     : netem rate 20 Mbit/s
# =============================================================================
set -uo pipefail

NS="access"
IFACES=(eth0 eth1)
COND="${1:?usage: impair.sh <baseline|delay|loss|rate|show>}"

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

clear_all() {
    for d in "${IFACES[@]}"; do
        ip netns exec "$NS" tc qdisc del dev "$d" root 2>/dev/null || true
    done
}

apply() { # <netem args...>
    for d in "${IFACES[@]}"; do
        ip netns exec "$NS" tc qdisc add dev "$d" root netem "$@"
    done
}

case "$COND" in
    baseline) clear_all; echo "[impair] $NS: no impairment (baseline)" ;;
    delay)    clear_all; apply delay 50ms 10ms; echo "[impair] $NS: delay 50ms +/-10ms on ${IFACES[*]}" ;;
    loss)     clear_all; apply loss 1%;        echo "[impair] $NS: 1% packet loss on ${IFACES[*]}" ;;
    rate)     clear_all; apply rate 20mbit;    echo "[impair] $NS: 20 Mbit/s limit on ${IFACES[*]}" ;;
    show)     for d in "${IFACES[@]}"; do echo "--- $NS:$d ---"; ip netns exec "$NS" tc qdisc show dev "$d"; done; exit 0 ;;
    *) echo "unknown condition: $COND" >&2; exit 2 ;;
esac

echo "[impair] resulting qdisc state:"
for d in "${IFACES[@]}"; do
    echo "--- $NS:$d ---"
    ip netns exec "$NS" tc qdisc show dev "$d"
done
