#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 5: recompute TCP retransmission counts from existing
# captures (no re-measurement) and add iperf3's sender counter as a cross-check.
#
# Then regenerate the table/plot with:  python3 ./scripts/plot.py
#
# Usage:  sudo ./scripts/recount-retrans.sh
# =============================================================================
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SUMMARY="$ROOT/results/scenario-b/summary.csv"
FILTER='tcp.analysis.retransmission or tcp.analysis.fast_retransmission'

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
command -v tshark >/dev/null || { echo "tshark not installed"; exit 1; }
[[ -f "$SUMMARY" ]] || { echo "missing $SUMMARY"; exit 1; }
# run tshark directly (aa-exec ... sh -c "tshark ..." would re-confine it)
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi

tmp=$(mktemp)
while IFS=, read -r cond metric run value unit; do
    [[ "$metric" == "tcp_retransmissions_sender" ]] && continue   # regenerated below
    if [[ "$metric" == "tcp_retransmissions" && "$run" == "total" ]]; then
        pcap="$ROOT/results/scenario-b/$cond/retrans.pcap"
        if [[ -f "$pcap" ]]; then
            TS -r "$pcap" -Y "$FILTER" -T fields -e frame.number > "$tmp.frames" 2>/dev/null || true
            n=$(grep -c . "$tmp.frames" 2>/dev/null || true)
            printf '%s,%s,%s,%s,%s\n' "$cond" "$metric" "$run" "${n:-0}" "$unit" >> "$tmp"
            src="$ROOT/results/scenario-b/$cond/tcp-retrans-source.txt"
            r=$(awk '/[[:space:]]sender[[:space:]]*$/{print $(NF-1); exit}' "$src" 2>/dev/null)
            printf '%s,tcp_retransmissions_sender,total,%s,count\n' "$cond" "${r:-NA}" >> "$tmp"
            printf '[recount] %-9s tshark=%-6s iperf3=%s\n' "$cond" "${n:-0}" "${r:-?}"
            continue
        fi
        echo "[recount] WARN: $pcap missing; keeping previous value" >&2
    fi
    printf '%s,%s,%s,%s,%s\n' "$cond" "$metric" "$run" "$value" "$unit" >> "$tmp"
done < "$SUMMARY"

mv "$tmp" "$SUMMARY"
rm -f "$tmp.frames"
[[ -n "${SUDO_USER:-}" ]] && chown "$SUDO_USER:$SUDO_USER" "$SUMMARY" 2>/dev/null || true
echo "[recount] updated $SUMMARY — now run: python3 ./scripts/plot.py"
