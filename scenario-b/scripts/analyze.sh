#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 4: tshark analysis of the multi-point captures
#
# Reads  captures/scenario-b/<label>/P*.pcap  and writes dissections to
#        results/scenario-b/
#
# Usage:  sudo ./scripts/analyze.sh
#
# Requires tshark on the host. The captures are root-owned (written by tcpdump
# via nsenter) and Ubuntu's AppArmor 'tshark' profile only allows reading
# user-tmp, so this must run as root and tshark is run unconfined (aa-exec).
# =============================================================================
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # repo root
CAPS="$ROOT/captures/scenario-b"
OUT="$ROOT/results/scenario-b"
mkdir -p "$OUT"

[[ $EUID -eq 0 ]] || { echo "run with sudo (pcaps are root-owned and AppArmor confines tshark)"; exit 1; }
command -v tshark >/dev/null || { echo "tshark not installed (sudo apt install tshark)"; exit 1; }
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi

# P5 is the application endpoint used for that capture (see scripts/capture.sh)
P5() { case "$1" in icmp|tcp-http) echo P5-nginx ;; *) echo P5-iperf3 ;; esac; }
POINTS() { echo "P1-ue P2-gnb P3-upf P4-upf $(P5 "$1")"; }
# flow filter for the user packet at the points where it travels un-encapsulated
FLOW() { case "$1" in
    icmp)      echo 'icmp' ;;
    tcp-http)  echo 'tcp.port==80' ;;
    tcp-iperf) echo 'tcp.port==5201' ;;
    udp-iperf) echo 'udp.port==5201' ;;
esac; }

LABELS="icmp tcp-http tcp-iperf udp-iperf"

# --- 1. Protocol hierarchy at every point -----------------------------------
for s in $LABELS; do
    for p in $(POINTS "$s"); do
        f="$CAPS/$s/$p.pcap"; [[ -f "$f" ]] || continue
        { echo "# Protocol hierarchy — $s / $p"; echo; TS -r "$f" -q -z io,phs; } \
            > "$OUT/$s-phs-$p.txt" 2>&1
    done
done

# --- 2. Cross-point packet counts -------------------------------------------
# At P1/P4/P5 the user packet is plain (flow filter); at P2/P3 it is inside the
# GTP-U envelope (udp 2152), so we count that.
{
    printf '%-11s %-14s %7s %7s\n' scenario point frames flow
    for s in $LABELS; do
        flt=$(FLOW "$s")
        for p in $(POINTS "$s"); do
            f="$CAPS/$s/$p.pcap"; [[ -f "$f" ]] || continue
            n_all=$(TS -r "$f" -T fields -e frame.number 2>/dev/null | grep -c .)
            case "$p" in
                P2-*|P3-*) q='udp.port==2152' ;;
                *)         q="$flt" ;;
            esac
            n_flt=$(TS -r "$f" -Y "$q" -T fields -e frame.number 2>/dev/null | grep -c .)
            printf '%-11s %-14s %7s %7s\n' "$s" "$p" "$n_all" "$n_flt"
        done
    done
} > "$OUT/cross-point-counts.txt" 2>&1

# --- 3. GTP-U envelope proof ------------------------------------------------
# The same first frame, decoded at every point: uesimtun0/plain, then
# "...udp:gtp:ip:<proto>" on N3, then plain again on N6.
{
    echo "# frame.protocols of the first frame at each point (icmp + tcp-http)"
    for s in icmp tcp-http; do
        echo; echo "## $s"
        for p in $(POINTS "$s"); do
            f="$CAPS/$s/$p.pcap"; [[ -f "$f" ]] || continue
            proto=$(TS -r "$f" -Y 'frame.number==1' -T fields -e frame.protocols 2>/dev/null)
            printf '%-14s %s\n' "$p" "${proto:-<no frames>}"
        done
    done
} > "$OUT/gtp-encapsulation-proof.txt" 2>&1

# --- 4. ICMP fields (size, TTL, seq, ident) at P1 and P5 --------------------
for p in P1-ue "$(P5 icmp)"; do
    f="$CAPS/icmp/$p.pcap"; [[ -f "$f" ]] || continue
    TS -r "$f" -Y icmp -T fields -E header=y -E separator='|' \
        -e frame.number -e frame.time_relative -e ip.src -e ip.dst \
        -e ip.ttl -e ip.len -e icmp.type -e icmp.code -e icmp.seq -e icmp.ident \
        > "$OUT/icmp-fields-$p.txt" 2>&1
done

# --- 5. TCP/HTTP: fields + application exchange (P1) ------------------------
if [[ -f "$CAPS/tcp-http/P1-ue.pcap" ]]; then
    TS -r "$CAPS/tcp-http/P1-ue.pcap" -T fields -E header=y -E separator='|' \
        -e frame.number -e frame.time_relative -e ip.src -e ip.dst \
        -e tcp.srcport -e tcp.dstport -e tcp.flags.str -e tcp.seq_raw -e tcp.ack_raw \
        -e tcp.len -e http.request.method -e http.request.uri \
        -e http.response.code -e http.response.phrase \
        > "$OUT/tcp-http-fields-P1.txt" 2>&1
    TS -r "$CAPS/tcp-http/P1-ue.pcap" -q -z follow,tcp,ascii,0 \
        > "$OUT/tcp-http-follow-stream0.txt" 2>&1
fi

# --- 6. TCP iperf3: conversations + retransmissions at P1, P4, P5 -----------
if [[ -f "$CAPS/tcp-iperf/P1-ue.pcap" ]]; then
    TS -r "$CAPS/tcp-iperf/P1-ue.pcap" -q -z conv,tcp > "$OUT/tcp-iperf-conversations.txt" 2>&1
    {
        echo "# TCP retransmissions (tcp-iperf)"
        for p in P1-ue P4-upf "$(P5 tcp-iperf)"; do
            f="$CAPS/tcp-iperf/$p.pcap"; [[ -f "$f" ]] || continue
            n=$(TS -r "$f" -Y 'tcp.analysis.retransmission or tcp.analysis.fast_retransmission' \
                  -T fields -e frame.number 2>/dev/null | grep -c .)
            printf '%-14s %s\n' "$p" "$n"
        done
    } > "$OUT/tcp-iperf-retransmissions.txt" 2>&1
fi

# --- 7. UDP iperf3: datagram fields + conversations -------------------------
if [[ -f "$CAPS/udp-iperf/P1-ue.pcap" ]]; then
    TS -r "$CAPS/udp-iperf/P1-ue.pcap" -q -z conv,udp > "$OUT/udp-iperf-conversations.txt" 2>&1
    TS -r "$CAPS/udp-iperf/P1-ue.pcap" -Y udp -T fields -E header=y -E separator='|' \
        -e frame.number -e frame.time_relative -e ip.src -e ip.dst \
        -e udp.srcport -e udp.dstport -e udp.length \
        > "$OUT/udp-iperf-datagrams-P1.txt" 2>&1
fi

# strip tshark's cosmetic "running as root" warning
sed -i '/Running as user .* and group .* This could be dangerous\./d' "$OUT"/*.txt 2>/dev/null || true
[[ -n "${SUDO_USER:-}" ]] && chown -R "$SUDO_USER":"$SUDO_USER" "$OUT" 2>/dev/null || true

echo "[analyze] results written to $OUT:"
ls -1 "$OUT"
