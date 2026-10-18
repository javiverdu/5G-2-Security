#!/usr/bin/env bash
# =============================================================================
# Scenario A — Step 3: recompute TCP retransmission counts from existing captures
#
# Reads results/step3/<condition>/retrans.pcap (no re-measurement) and updates
# the tcp_retransmissions rows of results/step3/summary.csv, counting BOTH
# plain and fast retransmissions, and adding the iperf3 sender counter as a
# cross-check (tcp_retransmissions_sender).
#
# After running this, regenerate the table/plots with:
#   python3 ./scripts/measure/plot.py
#
# Usage:  sudo ./scripts/measure/recount-retrans.sh
# =============================================================================
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SUMMARY="$ROOT/results/step3/summary.csv"
FILTER='tcp.analysis.retransmission or tcp.analysis.fast_retransmission'

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }
command -v tshark >/dev/null || { echo "tshark not found."; exit 1; }
[[ -f $SUMMARY ]] || { echo "missing $SUMMARY"; exit 1; }

# Ubuntu's AppArmor 'tshark' profile blocks reading repository files; run it
# unconfined when aa-exec is available.
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi

tmp=$(mktemp)
while IFS=, read -r cond metric run value unit; do
    # Drop the old cross-check rows; they are regenerated below.
    [[ "$metric" == "tcp_retransmissions_sender" ]] && continue

    if [[ "$metric" == "tcp_retransmissions" && "$run" == "total" ]]; then
        pcap="$ROOT/results/step3/$cond/retrans.pcap"
        if [[ -f $pcap ]]; then
            n=$(TS -r "$pcap" -Y "$FILTER" -T fields -e frame.number 2>/dev/null | grep -c .)
            printf '%s,%s,%s,%s,%s\n' "$cond" "$metric" "$run" "$n" "$unit" >> "$tmp"
            src="$ROOT/results/step3/$cond/tcp-retrans-source.txt"
            if [[ -f $src ]]; then
                r=$(awk '/[[:space:]]sender[[:space:]]*$/{print $(NF-1); exit}' "$src")
                printf '%s,tcp_retransmissions_sender,total,%s,count\n' "$cond" "${r:-NA}" >> "$tmp"
            fi
            printf '[recount] %-9s tshark=%-4s iperf3=%s\n' "$cond" "$n" "${r:-?}"
            continue
        fi
        echo "[recount] WARN: $pcap missing; keeping previous value" >&2
    fi
    printf '%s,%s,%s,%s,%s\n' "$cond" "$metric" "$run" "$value" "$unit" >> "$tmp"
done < "$SUMMARY"

mv "$tmp" "$SUMMARY"
[[ -n "${SUDO_USER:-}" ]] && chown "$SUDO_USER:$SUDO_USER" "$SUMMARY" 2>/dev/null || true
echo "[recount] updated $SUMMARY — now run: python3 ./scripts/measure/plot.py"