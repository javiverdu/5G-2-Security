#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 4: multi-point packet capture (user plane)
#
# Captures the same traffic at several points of the 5G path. tcpdump runs from
# the host inside each container's network namespace via nsenter, so no container
# image needs tcpdump installed (the images do not have it).
#
# Points:
#   P1 ue      uesimtun0        user data as the UE sends/receives it (10.45.0.x)
#   P2 gnb     core iface (N3)  GTP-U envelope toward the core      (udp 2152)
#   P3 upf     core iface (N3)  GTP-U envelope arriving at the UPF  (udp 2152)
#   P4 upf     N6 iface  (N6)   decapsulated user data (10.20.6.x)
#   P5 app     N6 iface  (N6)   delivered to the application
#
# Interface names inside a multi-network container are NOT guaranteed (eth0/eth1
# can swap), so they are detected by address, not by name.
#
# Usage:  sudo ./scripts/capture.sh <icmp|tcp-http|tcp-iperf|udp-iperf>
#
# Output: ../../captures/scenario-b/<label>/{P1-ue,...,P5-*.pcap}
# =============================================================================
set -uo pipefail

LABEL="${1:?usage: capture.sh <icmp|tcp-http|tcp-iperf|udp-iperf>}"
ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # repo root
OUT="$ROOT/captures/scenario-b/$LABEL"
set -a; . "$(cd "$(dirname "$0")/.." && pwd)/.env"; set +a

[[ $EUID -eq 0 ]] || { echo "run with sudo (nsenter needs CAP_SYS_ADMIN)"; exit 1; }
command -v tcpdump >/dev/null || { echo "tcpdump not installed on the host"; exit 1; }

# container PIDs
pid_ue=$(docker inspect -f '{{.State.Pid}}' nr_ue 2>/dev/null)
pid_gnb=$(docker inspect -f '{{.State.Pid}}' nr_gnb 2>/dev/null)
pid_upf=$(docker inspect -f '{{.State.Pid}}' upf 2>/dev/null)

# P5 is the application endpoint for THIS test: nginx for ping/HTTP, iperf3 for
# throughput. Capturing iperf3 traffic on nginx would always be empty.
case "$LABEL" in
    icmp|tcp-http)       P5_CT=sb-nginx;  P5_NAME=P5-nginx ;;
    tcp-iperf|udp-iperf) P5_CT=sb-iperf3; P5_NAME=P5-iperf3 ;;
    *) echo "unknown label: $LABEL" >&2; exit 2 ;;
esac
pid_p5=$(docker inspect -f '{{.State.Pid}}' "$P5_CT" 2>/dev/null)

for p in "$pid_ue" "$pid_gnb" "$pid_upf" "$pid_p5"; do
    [[ -n "$p" && "$p" != 0 ]] || { echo "a required container is not running"; exit 1; }
done

# Detect interfaces by address: core = 172.22.0.x, N6 = 10.20.6.x.
iface_with() { # <container> <ip-prefix-regex>
    docker exec "$1" ip -o -4 addr show 2>/dev/null \
        | awk -v p="$2" '$4 ~ p {print $2; exit}' | cut -d@ -f1
}
GNB_CORE_IF=$(iface_with nr_gnb '^172\.22\.')
UPF_CORE_IF=$(iface_with upf    '^172\.22\.')
UPF_DN_IF=$(iface_with upf      '^10\.20\.6\.')
P5_IF=$(iface_with "$P5_CT"     '^10\.20\.6\.'); [[ -n "$P5_IF" ]] || P5_IF=eth0

for v in GNB_CORE_IF UPF_CORE_IF UPF_DN_IF; do
    [[ -n "${!v}" ]] || { echo "could not detect $v (is N6 up? run scripts/enable-n6.sh)"; exit 1; }
done

mkdir -p "$OUT"
echo "[capture] label=$LABEL  out=$OUT"
echo "[capture] ifaces: gnb-core=$GNB_CORE_IF  upf-core=$UPF_CORE_IF  upf-n6=$UPF_DN_IF  app=$P5_IF"

PIDS=()
cap() { # <name> <pid-or-empty> <iface> <bpf>
    local name="$1" pid="$2" iface="$3" bpf="$4"
    if [[ -n "$pid" ]]; then
        nsenter -t "$pid" -n tcpdump -i "$iface" -w "$OUT/$name.pcap" -U -q $bpf &
    else
        tcpdump -i "$iface" -w "$OUT/$name.pcap" -U -q $bpf &
    fi
    PIDS+=($!)
}

cap P1-ue      "$pid_ue"  uesimtun0      "ip"
cap P2-gnb     "$pid_gnb" "$GNB_CORE_IF" "udp port 2152"
cap P3-upf     "$pid_upf" "$UPF_CORE_IF" "udp port 2152"
cap P4-upf     "$pid_upf" "$UPF_DN_IF"   "ip"
cap "$P5_NAME" "$pid_p5"  "$P5_IF"       "ip"

sleep 1

echo "[capture] generating traffic: $LABEL"
case "$LABEL" in
    icmp)
        docker exec nr_ue ping -c 5 -s 100 "$NGINX_IP" ;;
    tcp-http)
        docker exec nr_ue bash -c "exec 3<>/dev/tcp/$NGINX_IP/80; printf 'GET / HTTP/1.0\r\nHost: $NGINX_IP\r\n\r\n' >&3; cat <&3" >/dev/null ;;
    tcp-iperf)
        docker run --rm --network container:nr_ue networkstatic/iperf3:latest -c "$IPERF_IP" -b 5M -t 4 ;;
    udp-iperf)
        docker run --rm --network container:nr_ue networkstatic/iperf3:latest -c "$IPERF_IP" -u -b 1M -t 5 ;;
    *)
        echo "unknown label: $LABEL" >&2; exit 2 ;;
esac

sleep 1
kill -INT "${PIDS[@]}" 2>/dev/null || true
wait "${PIDS[@]}" 2>/dev/null || true

echo "[capture] frames per point:"
for f in "$OUT"/*.pcap; do
    printf '  %-16s %s\n' "$(basename "$f")" "$(tcpdump -nr "$f" 2>/dev/null | wc -l)"
done
