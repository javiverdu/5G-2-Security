#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 2: multi-point packet capture
#
# Captures the same traffic at six points along the end-to-end path while a
# traffic command is executed from the UE namespace:
#
#   P1 ue:eth0            (generated / received)
#   P2 access:eth0        (arrived at access from UE)
#   P3 access:eth1        (forwarded by access toward core)
#   P4 core:eth1          (forwarded by core toward the Data Network)
#   P5 host:veth-hn       (arrived at the Data Network boundary)
#   P6 <container>:eth0   (delivered to / answered by the target service)
#
# Usage:  sudo ./scripts/observe/capture.sh <label> <target-container> '<command>'
#   e.g.  sudo ./scripts/observe/capture.sh icmp nginx-app 'ping -c 5 -s 100 10.0.4.10'
# =============================================================================
set -uo pipefail

LABEL="${1:?usage: capture.sh <label> <target-container> <command-in-ue>}"
TARGET="${2:?target container name required}"
TRAFFIC="${3:?traffic command required}"

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT="$ROOT/captures/step2/$LABEL"
FILTER="ip"
mkdir -p "$OUT"

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }

PIDS=()
start_cap() { # <name> <command prefix that runs tcpdump in the right netns>
    local name="$1"; shift
    "$@" -w "$OUT/$name.pcap" -U -q "$FILTER" &
    PIDS+=($!)
}

start_cap P1-ue        ip netns exec ue     tcpdump -i eth0
start_cap P2-access-e0 ip netns exec access tcpdump -i eth0
start_cap P3-access-e1 ip netns exec access tcpdump -i eth1
start_cap P4-core-e1   ip netns exec core   tcpdump -i eth1
start_cap P5-host-hn   tcpdump -i veth-hn

CPID=$(docker inspect -f '{{.State.Pid}}' "$TARGET")
nsenter -t "$CPID" -n tcpdump -i eth0 -w "$OUT/P6-$TARGET.pcap" -U -q "$FILTER" &
PIDS+=($!)

sleep 1
echo "[capture] running: $TRAFFIC"
ip netns exec ue bash -c "$TRAFFIC"
sleep 1

kill -INT "${PIDS[@]}" 2>/dev/null || true
wait "${PIDS[@]}" 2>/dev/null || true

chown -R x0riso:x0riso "$ROOT/captures"
echo "[capture] files in $OUT:"
ls -1 "$OUT"
