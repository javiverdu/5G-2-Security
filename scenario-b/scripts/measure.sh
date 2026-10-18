#!/usr/bin/env bash
# =============================================================================
# Scenario B — page 5: full measurement set for one network condition.
#
# Metrics, all measured from the UE (10.45.0.2):
#   - ICMP RTT + loss            (ping x20, 3 runs)
#   - HTTP response time         (GET via bash /dev/tcp, 10 requests, 3 runs)
#   - TCP throughput             (iperf3, 3 runs)
#   - UDP throughput/loss/jitter (iperf3 -u -b 10M, 3 runs)
#   - TCP retransmissions        (rate-capped transfer + capture at uesimtun0)
#
# Usage:  sudo ./scripts/measure.sh <label>
# Results: results/scenario-b/<label>/ and rows in results/scenario-b/summary.csv
# =============================================================================
set -uo pipefail
export LC_ALL=C
HERE=$(cd "$(dirname "$0")/.." && pwd)          # scenario-b
ROOT=$(cd "$(dirname "$0")/../.." && pwd)       # repo root
set -a; . "$HERE/.env"; set +a

LABEL="${1:?usage: measure.sh <label>}"
OUT="$ROOT/results/scenario-b/$LABEL"
SUMMARY="$ROOT/results/scenario-b/summary.csv"
mkdir -p "$OUT"
[[ $EUID -eq 0 ]] || { echo "run with sudo (nsenter + tshark)"; exit 1; }

pid_ue=$(docker inspect -f '{{.State.Pid}}' nr_ue 2>/dev/null)
[[ -n "$pid_ue" && "$pid_ue" != 0 ]] || { echo "nr_ue not running"; exit 1; }
[[ -f "$SUMMARY" ]] || echo "condition,metric,run,value,unit" > "$SUMMARY"
# replace previous rows for this condition
tmp=$(mktemp); awk -F, -v c="$LABEL" 'NR==1 || $1!=c' "$SUMMARY" > "$tmp" && mv "$tmp" "$SUMMARY"

iperf() { docker run --rm --network container:nr_ue networkstatic/iperf3:latest "$@"; }
# IMPORTANT: run tshark directly through aa-exec. `aa-exec ... sh -c "tshark ..."`
# re-applies the tshark AppArmor profile on the sh->tshark exec and stays confined.
if command -v aa-exec >/dev/null 2>&1; then
    TS() { aa-exec -p unconfined -- tshark "$@"; }
else
    TS() { tshark "$@"; }
fi
http_ms() { # one GET, print milliseconds (or empty)
    timeout 10 docker exec nr_ue timeout 8 bash -c '
        s=$(date +%s%N)
        exec 3<>/dev/tcp/'"$NGINX_IP"'/80 || exit 1
        printf "GET / HTTP/1.0\r\nHost: %s\r\n\r\n" "'"$NGINX_IP"'" >&3
        cat <&3 >/dev/null
        e=$(date +%s%N)
        echo $(( (e - s) / 1000000 ))
    ' 2>/dev/null
}

echo "[measure] condition=$LABEL"

# --- ICMP RTT / loss
for run in 1 2 3; do
    out=$(docker exec nr_ue ping -c 20 -i 0.2 -W 2 "$NGINX_IP" 2>/dev/null)
    echo "$out" > "$OUT/ping-run$run.txt"
    loss=$(grep -oE '[0-9]+% packet loss' <<<"$out" | grep -oE '^[0-9]+')
    avg=$(awk -F'/' '/rtt|round-trip/ {print $5}' <<<"$out")
    echo "$LABEL,icmp_loss,run$run,${loss:-0},percent" >> "$SUMMARY"
    echo "$LABEL,icmp_rtt_avg,run$run,${avg:-0},ms" >> "$SUMMARY"
done

# --- HTTP response time (10 requests)
for run in 1 2 3; do
    : > "$OUT/http-run$run.txt"
    for _ in $(seq 1 10); do http_ms >> "$OUT/http-run$run.txt"; echo >> "$OUT/http-run$run.txt"; done
    avg=$(awk 'NF{s+=$1;n++} END{if(n) printf "%.2f", s/n; else print "NA"}' "$OUT/http-run$run.txt")
    echo "$LABEL,http_time_avg,run$run,$avg,ms" >> "$SUMMARY"
done

# --- TCP throughput
for run in 1 2 3; do
    if iperf -c "$IPERF_IP" -t 3 -J > "$OUT/tcp-run$run.json" 2>/dev/null \
       && grep -q sum_received "$OUT/tcp-run$run.json"; then
        bps=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["end"]["sum_received"]["bits_per_second"])' "$OUT/tcp-run$run.json")
        echo "$LABEL,tcp_throughput,run$run,$bps,bit/s" >> "$SUMMARY"
    else
        echo "$LABEL,tcp_throughput,run$run,NA,failed" >> "$SUMMARY"
    fi
done

# --- UDP throughput / loss / jitter
for run in 1 2 3; do
    if iperf -c "$IPERF_IP" -u -b 10M -t 3 -J > "$OUT/udp-run$run.json" 2>/dev/null \
       && grep -q '"sum"' "$OUT/udp-run$run.json"; then
        python3 - "$OUT/udp-run$run.json" "$LABEL" "$run" "$SUMMARY" <<'PY'
import json, sys
path, label, run, summary = sys.argv[1:5]
s = json.load(open(path))["end"]["sum"]
with open(summary, "a") as f:
    f.write(f"{label},udp_throughput,{run},{s['bits_per_second']},bit/s\n")
    f.write(f"{label},udp_loss,{run},{s['lost_percent']},percent\n")
    f.write(f"{label},udp_jitter,{run},{s.get('jitter_ms', 0)},ms\n")
PY
    else
        echo "$LABEL,udp_throughput,$run,NA,failed" >> "$SUMMARY"
    fi
done

# --- TCP retransmissions (rate-capped transfer + capture at uesimtun0)
nsenter -t "$pid_ue" -n timeout 8 tcpdump -i uesimtun0 -w "$OUT/retrans.pcap" -U -q tcp port 5201 &
cap=$!
sleep 1
iperf -c "$IPERF_IP" -b 20M -t 5 > "$OUT/tcp-retrans-source.txt" 2>&1
wait "$cap" 2>/dev/null || true
if [[ -f "$OUT/retrans.pcap" ]]; then
    TS -r "$OUT/retrans.pcap" \
        -Y 'tcp.analysis.retransmission or tcp.analysis.fast_retransmission' \
        -T fields -e frame.number > "$OUT/retrans-frames.txt" 2> "$OUT/retrans-tshark.err" || true
    n=$(grep -c . "$OUT/retrans-frames.txt" 2>/dev/null || true)
    echo "$LABEL,tcp_retransmissions,total,${n:-0},count" >> "$SUMMARY"
    # cross-check: iperf3's own sender retransmit counter
    src=$(awk '/[[:space:]]sender[[:space:]]*$/{print $(NF-1); exit}' "$OUT/tcp-retrans-source.txt" 2>/dev/null)
    echo "$LABEL,tcp_retransmissions_sender,total,${src:-NA},count" >> "$SUMMARY"
fi

echo "[measure] done: $OUT"
