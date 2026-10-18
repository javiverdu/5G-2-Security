#!/usr/bin/env bash
# =============================================================================
# Scenario B — control-plane capture: N2 (NGAP/SCTP 38412) and N4 (PFCP/UDP 8805)
#
# These messages occur only during registration and PDU-session setup, so the
# capture is taken while the UE re-registers (docker restart nr_ue). The script
# re-asserts the UE user-plane route afterwards.
#
# Proves, at packet level, that N2 (gNB<->AMF) and N4 (SMF<->UPF) work — not just
# that containers are "Up".
#
# Usage:  sudo ./scripts/capture-control.sh
# Output: captures/scenario-b/control/{N2-gnb,N2-amf,N4-upf}.pcap
# =============================================================================
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # repo root
OUT="$ROOT/captures/scenario-b/control"
set -a; . "$(cd "$(dirname "$0")/.." && pwd)/.env"; set +a

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }

iface_with() { # <container> <ip-prefix-regex>
    docker exec "$1" ip -o -4 addr show 2>/dev/null \
        | awk -v p="$2" '$4 ~ p {print $2; exit}' | cut -d@ -f1
}
GNB_CORE_IF=$(iface_with nr_gnb '^172\.22\.')
AMF_CORE_IF=$(iface_with amf    '^172\.22\.')
UPF_CORE_IF=$(iface_with upf    '^172\.22\.')
for v in GNB_CORE_IF AMF_CORE_IF UPF_CORE_IF; do
    [[ -n "${!v}" ]] || { echo "could not detect $v"; exit 1; }
done

mkdir -p "$OUT"
echo "[control] out=$OUT"
echo "[control] ifaces: gnb=$GNB_CORE_IF amf=$AMF_CORE_IF upf=$UPF_CORE_IF"

PIDS=()
cap() { # <name> <container> <iface> <bpf>
    local name="$1" c="$2" iface="$3" bpf="$4" pid
    pid=$(docker inspect -f '{{.State.Pid}}' "$c" 2>/dev/null)
    [[ -n "$pid" && "$pid" != 0 ]] || return 0
    nsenter -t "$pid" -n tcpdump -i "$iface" -w "$OUT/$name.pcap" -U -q $bpf &
    PIDS+=($!)
}
cap N2-gnb nr_gnb "$GNB_CORE_IF" "sctp port 38412"
cap N2-amf amf    "$AMF_CORE_IF" "sctp port 38412"
cap N4-upf upf    "$UPF_CORE_IF" "udp port 8805"

sleep 1
echo "[control] restarting the UE to trigger registration + PDU session"
docker restart nr_ue >/dev/null

printf '[control] waiting for registration'
for _ in $(seq 1 60); do
    docker logs nr_ue 2>&1 | grep -qiE 'registration.*(success|accept|complete)' && { echo " ...ok"; break; }
    printf '.'; sleep 2
done
sleep 1

kill -INT "${PIDS[@]}" 2>/dev/null || true
wait "${PIDS[@]}" 2>/dev/null || true

# the UE container restarted, so re-install its user-plane route
docker exec nr_ue ip route replace default dev uesimtun0 2>/dev/null || true
docker exec nr_ue ip route add 10.45.0.0/16 dev uesimtun0 2>/dev/null || true

echo "[control] frames per point:"
for f in "$OUT"/*.pcap; do
    printf '  %-16s %s\n' "$(basename "$f")" "$(tcpdump -nr "$f" 2>/dev/null | wc -l)"
done
