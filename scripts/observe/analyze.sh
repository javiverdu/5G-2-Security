#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 2: tshark analysis of the multi-point captures
# Reads  captures/step2/<scenario>/P*.pcap  and writes dissections to
#       results/step2/
# Usage:  sudo ./scripts/observe/analyze.sh
# =============================================================================
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CAPS="$ROOT/captures/step2"
OUT="$ROOT/results/step2"
mkdir -p "$OUT"

# Ubuntu's AppArmor 'tshark' profile restricts file reads to user-tmp, which
# blocks dissection of captures stored under the repository. Run tshark
# unconfined (fall back to plain tshark if aa-exec is unavailable).
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi

P6() { case "$1" in icmp|tcp-http) echo "P6-nginx-app" ;; *) echo "P6-iperf3-srv" ;; esac; }
FLOW() { case "$1" in
    icmp)      echo 'icmp' ;;
    tcp-http)  echo 'tcp.port==80' ;;
    tcp-iperf) echo 'tcp.port==5201' ;;
    udp-iperf) echo 'udp.port==5201' ;;
esac; }

# 1. Protocol hierarchy at the UE for every scenario
for s in icmp tcp-http tcp-iperf udp-iperf; do
    {
        echo "# Protocol hierarchy at P1 (ue:eth0) — scenario: $s"
        echo
        TS -r "$CAPS/$s/P1-ue.pcap" -q -z io,phs
    } > "$OUT/$s-protocol-hierarchy.txt" 2>&1
done

# 2. Cross-point packet counts: generated -> forwarded -> delivered
{
    printf '%-11s %-16s %7s\n' scenario point packets
    for s in icmp tcp-http tcp-iperf udp-iperf; do
        f=$(FLOW "$s")
        for p in P1-ue P2-access-e0 P3-access-e1 P4-core-e1 P5-host-hn "$(P6 "$s")"; do
            n=$(TS -r "$CAPS/$s/$p.pcap" -Y "$f" -T fields -e frame.number 2>/dev/null | grep -c .)
            printf '%-11s %-16s %7s\n' "$s" "$p" "$n"
        done
    done
} > "$OUT/cross-point-packet-counts.txt" 2>&1

# 3A. ICMP detailed fields at P1 and P6
for p in P1-ue P6-nginx-app; do
    {
        echo "# ICMP fields ($p)"
        TS -r "$CAPS/icmp/$p.pcap" -Y icmp -T fields -E header=y -E separator='|' \
            -e frame.number -e frame.time_relative -e ip.src -e ip.dst -e ip.ttl \
            -e ip.len -e icmp.type -e icmp.code -e icmp.seq -e icmp.ident
    } > "$OUT/icmp-fields-$p.txt" 2>&1
done

# 3B. TCP HTTP packet fields + application exchange (P1)
TS -r "$CAPS/tcp-http/P1-ue.pcap" -T fields -E header=y -E separator='|' \
    -e frame.number -e frame.time_relative -e ip.src -e ip.dst \
    -e tcp.srcport -e tcp.dstport -e tcp.flags.str -e tcp.seq_raw -e tcp.ack_raw \
    -e tcp.len -e http.request.method -e http.request.uri \
    -e http.response.code -e http.response.phrase \
    > "$OUT/tcp-http-fields-P1.txt" 2>&1

TS -r "$CAPS/tcp-http/P1-ue.pcap" -q -z follow,tcp,ascii,0 \
    > "$OUT/tcp-http-follow-stream0.txt" 2>&1

# 3C. TCP iperf3: flow summary, connection setup/teardown, retransmissions (P1)
TS -r "$CAPS/tcp-iperf/P1-ue.pcap" -q -z conv,tcp \
    > "$OUT/tcp-iperf-conversations.txt" 2>&1

TS -r "$CAPS/tcp-iperf/P1-ue.pcap" \
    -Y 'tcp.flags.syn==1 or tcp.flags.fin==1' -T fields -E header=y -E separator='|' \
    -e frame.number -e frame.time_relative -e ip.src -e tcp.srcport \
    -e ip.dst -e tcp.dstport -e tcp.flags.str -e tcp.seq_raw -e tcp.ack_raw \
    > "$OUT/tcp-iperf-handshake-teardown.txt" 2>&1

{
    echo "# TCP retransmissions observed at P1, P4 and P6 (iperf3 TCP)"
    for p in P1-ue P4-core-e1 P6-iperf3-srv; do
        n=$(TS -r "$CAPS/tcp-iperf/$p.pcap" -Y tcp.analysis.retransmission \
              -T fields -e frame.number 2>/dev/null | grep -c .)
        printf '%-16s %s\n' "$p" "$n"
    done
} > "$OUT/tcp-iperf-retransmissions.txt" 2>&1

# 3D. UDP iperf3: flow summary + datagram fields sample (P1)
TS -r "$CAPS/udp-iperf/P1-ue.pcap" -q -z conv,udp \
    > "$OUT/udp-iperf-conversations.txt" 2>&1

TS -r "$CAPS/udp-iperf/P1-ue.pcap" -Y udp -T fields -E header=y -E separator='|' \
    -e frame.number -e frame.time_relative -e ip.src -e ip.dst \
    -e udp.srcport -e udp.dstport -e udp.length \
    > "$OUT/udp-iperf-datagrams-P1.txt" 2>&1

# strip tshark's cosmetic "running as root" warning from the outputs
sed -i '/Running as user .* and group .* This could be dangerous\./d' "$OUT"/*.txt 2>/dev/null || true

chown -R x0riso:x0riso "$OUT" "$CAPS" 2>/dev/null || true
echo "[analyze] results written to $OUT:"
ls -1 "$OUT"
